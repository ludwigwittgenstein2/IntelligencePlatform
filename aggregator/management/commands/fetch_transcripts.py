# aggregator/management/commands/fetch_transcripts.py
"""
Fetch transcripts for YouTube ContentItems.

Strategy: captions first (free, instant), Whisper as a fallback only when
captions are missing or degenerate.

Quality is judged by lexical diversity (unique words / total words), NOT by
punctuation -- Tamil auto-captions are usually punctuation-free, so a
punctuation heuristic wrongly rejects good captions. The diversity check is
language-neutral and also catches Whisper's repetition-loop hallucination
("foo foo foo foo ..."), which scores near zero.

Runs unchanged on macOS (CPU) and a CUDA GPU box -- device is detected at
runtime. No torch dependency: CUDA is checked via ctranslate2.

Use --source "<channel name>" to transcribe one channel's videos instead of
processing the whole YouTube queue by recency.
"""

import os
import time
import tempfile

from django.core.management.base import BaseCommand
from aggregator.models import ContentItem, Source


# --- tuning knobs -----------------------------------------------------------
MIN_TEXT_LEN = 200          # shorter than this counts as no usable transcript
MIN_WORDS = 20              # too few words to judge -> treat as unusable
MIN_UNIQUE_RATIO = 0.30     # unique_words/total_words below this = degenerate
GOOD_TRANSCRIPT_LEN = 300   # existing body_ta longer than this is left alone


def is_degenerate(text):
    if not text or len(text) < MIN_TEXT_LEN:
        return True
    words = text.split()
    if len(words) < MIN_WORDS:
        return True
    return len(set(words)) / len(words) < MIN_UNIQUE_RATIO


# --- caption fetch (handles youtube-transcript-api 0.x and 1.x) -------------
def fetch_captions(video_id, langs=("ta", "en")):
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        try:                                   # 1.x instance API
            fetched = YouTubeTranscriptApi().fetch(video_id, languages=list(langs))
            return " ".join(s.text for s in fetched)
        except AttributeError:                 # 0.x classmethod API
            data = YouTubeTranscriptApi.get_transcript(video_id, languages=list(langs))
            return " ".join(s["text"] for s in data)
    except Exception:
        return ""


# --- whisper fallback -------------------------------------------------------
_WHISPER = None

WHISPER_OPTS = dict(
    beam_size=5,
    vad_filter=True,                  # skip non-speech that triggers loops
    condition_on_previous_text=False, # stop a bad segment poisoning the next
    no_repeat_ngram_size=3,           # block "foo foo foo" repetition
    repetition_penalty=1.1,
)


def _detect_device():
    """Return (device, compute_type) without requiring torch."""
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda", "float16"
    except Exception:
        pass
    return "cpu", "int8"


def get_whisper(model_size="large-v3"):
    global _WHISPER
    if _WHISPER is None:
        from faster_whisper import WhisperModel
        device, compute = _detect_device()
        _WHISPER = WhisperModel(model_size, device=device, compute_type=compute)
    return _WHISPER


def whisper_transcribe(video_id, model_size="large-v3", cookies=None):
    import yt_dlp

    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "audio")
        opts = {
            "format": "bestaudio/best",
            "outtmpl": out + ".%(ext)s",
            "quiet": True,
            "no_warnings": True,
            "postprocessors": [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}
            ],
        }
        if cookies:
            opts["cookiefile"] = cookies

        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={video_id}"])

        audio = out + ".mp3"
        model = get_whisper(model_size)

        seg_ta, _ = model.transcribe(audio, language="ta", **WHISPER_OPTS)
        ta = " ".join(s.text for s in seg_ta)

        seg_en, _ = model.transcribe(audio, task="translate", **WHISPER_OPTS)
        en = " ".join(s.text for s in seg_en)

        return ta.strip(), en.strip()


# --- command ----------------------------------------------------------------
class Command(BaseCommand):
    help = "Fetch YouTube transcripts (captions first, Whisper fallback)."

    def add_arguments(self, p):
        p.add_argument("--force", action="store_true",
                       help="re-transcribe even if text already exists")
        p.add_argument("--limit", type=int, default=50,
                       help="max items to process this run")
        p.add_argument("--source", default=None,
                       help="limit to one channel by exact Source.name")
        p.add_argument("--whisper-model", default="large-v3",
                       help="faster-whisper size: tiny|base|small|medium|large-v3")
        p.add_argument("--prefer-whisper", action="store_true",
                       help="skip captions entirely and always use Whisper")
        p.add_argument("--cookies", default=None,
                       help="path to a cookies.txt file (helps with rate-limiting)")
        p.add_argument("--sleep", type=float, default=2.0,
                       help="seconds to wait between Whisper downloads")

    def _record(self, item, method, fields):
        metrics = item.metrics or {}
        metrics["transcript_source"] = method
        item.metrics = metrics
        item.save(update_fields=fields + ["metrics"])

    def handle(self, *args, **opts):
        qs = (ContentItem.objects
              .filter(source__source_type=Source.SourceType.YOUTUBE)
              .order_by("-published_at"))

        if opts["source"]:
            qs = qs.filter(source__name=opts["source"])

        done = 0
        for item in qs:
            if done >= opts["limit"]:
                break

            already_good = (item.body_ta and len(item.body_ta) > GOOD_TRANSCRIPT_LEN)
            if already_good and not opts["force"]:
                continue

            video_id = (item.metrics or {}).get("video_id")
            if not video_id:
                continue

            # 1) captions, unless told to skip them
            if not opts["prefer_whisper"]:
                caption = fetch_captions(video_id)
                if caption and not is_degenerate(caption):
                    item.body_ta = caption
                    self._record(item, "caption", ["body_ta"])
                    self.stdout.write(f"caption  \u2713 {item.id}")
                    done += 1
                    continue

            # 2) Whisper fallback
            try:
                ta, en = whisper_transcribe(
                    video_id,
                    model_size=opts["whisper_model"],
                    cookies=opts["cookies"],
                )
            except Exception as e:
                self.stderr.write(f"fail {item.id}: {e}")
                continue

            if is_degenerate(ta):
                self.stderr.write(
                    self.style.WARNING(
                        f"skip {item.id}: whisper output degenerate "
                        f"(model={opts['whisper_model']}; try a larger model "
                        f"or run on GPU)"
                    )
                )
                continue

            item.body_ta, item.body_en = ta, en
            self._record(item, f"whisper:{opts['whisper_model']}",
                         ["body_ta", "body_en"])
            self.stdout.write(f"whisper  \u2713 {item.id}")
            done += 1
            time.sleep(opts["sleep"])     # be polite to YouTube

        self.stdout.write(self.style.SUCCESS(f"done: {done} item(s)"))