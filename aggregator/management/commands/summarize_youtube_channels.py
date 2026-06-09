# aggregator/management/commands/summarize_youtube_channels.py
"""
Build one ChannelDigest per YouTube channel from its recent video transcripts.

Calls an OpenAI-compatible endpoint (Ollama or vLLM), so the model is swappable
by changing --model / --url only:
  - local dev (Mac):  --model qwen2.5:3b-instruct        (fast, weak Tamil)
  - quality:          --model hf.co/Mungert/sarvam-m-GGUF:Q4_K_M  (Ollama)
  - production (GPU):  --url http://gpu-box:8000/v1/chat/completions --model sarvamai/sarvam-m

Reasoning models (Sarvam-M, deepseek-r1) emit <think>...</think> before the
answer; that block is stripped before JSON parsing.
"""

import re
import json
import requests

from datetime import timedelta
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone
from aggregator.models import Source, ContentItem, ChannelDigest


# --- input quality guard (same idea as fetch_transcripts) -------------------
def is_degenerate(text):
    if not text or len(text) < 200:
        return True
    words = text.split()
    if len(words) < 20:
        return True
    return len(set(words)) / len(words) < 0.30


PROMPT = """You are analyzing recent videos from ONE Tamil news/commentary YouTube channel.
Below are titles and transcript excerpts from that channel.

Respond with ONLY valid JSON, no markdown fences, no commentary:
{{
  "summary_en": "3-4 sentences in English: what this channel covered this period",
  "summary_ta": "the same summary written in Tamil",
  "main_topics": ["short topic labels, max 6"],
  "key_issues": ["specific issues/events discussed, max 6"],
  "stance": "their stance toward the Tamil Nadu state government / ruling party: supportive | critical | neutral | mixed",
  "stance_detail": "one sentence explaining the stance",
  "sentiment": "overall tone: positive | negative | neutral | mixed"
}}

CHANNEL: {channel}

CONTENT:
{content}"""


def extract_json(raw):
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # last resort: grab the first balanced-looking {...} block
        m = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if m:
            return json.loads(m.group(0))
        raise


class Command(BaseCommand):
    help = "Summarize recent YouTube videos into one digest per channel."

    def add_arguments(self, p):
        p.add_argument("--url", default="http://localhost:11434/v1/chat/completions",
                       help="OpenAI-compatible chat endpoint")
        p.add_argument("--model", default="qwen2.5:3b-instruct",
                       help="model name/tag served at --url")
        p.add_argument("--days", type=int, default=7,
                       help="look back this many days for videos")
        p.add_argument("--max-videos", type=int, default=15,
                       help="max videos per channel to feed the model")
        p.add_argument("--min-videos", type=int, default=1,
                       help="skip channels with fewer usable videos than this")
        p.add_argument("--per-video-chars", type=int, default=1500)
        p.add_argument("--total-chars", type=int, default=10000)
        p.add_argument("--only", default=None,
                       help="limit to one channel by exact Source.name")

    def _call_llm(self, url, model, prompt):
        r = requests.post(url, json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }, timeout=300)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    def handle(self, *args, **opts):
        since = timezone.now() - timedelta(days=opts["days"])

        channels = Source.objects.filter(
            source_type=Source.SourceType.YOUTUBE, is_active=True)
        if opts["only"]:
            channels = channels.filter(name=opts["only"])

        for ch in channels:
            items = (ContentItem.objects
                     .filter(source=ch)
                     .filter(Q(published_at__gte=since)
                             | Q(published_at__isnull=True, created_at__gte=since))
                     .order_by("-published_at", "-created_at")[:opts["max_videos"]])

            blocks, used = [], 0
            for it in items:
                # prefer the English translation for general models; fall back
                # to Tamil. Skip videos whose transcript is missing/degenerate.
                body = it.body_en or it.body_ta or ""
                if is_degenerate(body):
                    continue
                title = it.title_en or it.title_ta or "(untitled)"
                snippet = body[:opts["per_video_chars"]]
                blocks.append(f"- {title}\n{snippet}")
                used += 1

            if used < opts["min_videos"]:
                self.stdout.write(f"skip  {ch.name}: {used} usable video(s)")
                continue

            content = "\n\n".join(blocks)[:opts["total_chars"]]
            prompt = PROMPT.format(channel=ch.name, content=content)

            try:
                raw = self._call_llm(opts["url"], opts["model"], prompt)
                data = extract_json(raw)
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"fail  {ch.name}: {e}"))
                continue

            ChannelDigest.objects.update_or_create(
                source=ch,
                defaults={
                    "summary_en": data.get("summary_en", ""),
                    "summary_ta": data.get("summary_ta", ""),
                    "main_topics": data.get("main_topics", []) or [],
                    "key_issues": data.get("key_issues", []) or [],
                    "stance": (data.get("stance") or "").lower().strip(),
                    "stance_detail": data.get("stance_detail", ""),
                    "sentiment": (data.get("sentiment") or "").lower().strip(),
                    "video_count": used,
                    "generated_at": timezone.now(),
                },
            )
            self.stdout.write(self.style.SUCCESS(f"\u2713 {ch.name} ({used} videos)"))