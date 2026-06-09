from collections import Counter, defaultdict
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from aggregator.models import ContentItem, DailyReport


BAD_TEXT_PATTERNS = [
    "i’m ready to translate",
    "i'm ready to translate",
    "please provide the tamil content",
    "could you please provide",
    "as an ai",
    "i cannot",
    "translation pending",
    "summary pending",
]


def is_bad_text(text):
    if not text:
        return True

    cleaned = str(text).strip()

    if cleaned in [".", "-", "…", ""]:
        return True

    if len(cleaned) < 8:
        return True

    lower = cleaned.lower()

    for pattern in BAD_TEXT_PATTERNS:
        if pattern in lower:
            return True

    return False


def clean_label(value):
    if not value:
        return ""

    return str(value).replace("_", " ").replace("&", "and").strip()


def safe_title(item, lang="en"):
    if lang == "ta":
        if not is_bad_text(item.title_ta):
            return item.title_ta
        return ""

    if not is_bad_text(item.title_en):
        return item.title_en

    return ""


def safe_summary(nlp, lang="en"):
    if not nlp:
        return ""

    if lang == "ta":
        if not is_bad_text(nlp.summary_ta):
            return nlp.summary_ta
        return ""

    if not is_bad_text(nlp.summary_en):
        return nlp.summary_en

    return ""


def get_metric(item, key, default=0):
    try:
        return int((item.metrics or {}).get(key, default) or default)
    except Exception:
        return default


def item_score(item):
    nlp = getattr(item, "nlp", None)

    news_score = nlp.news_relevance_score if nlp else 0
    intensity = nlp.intensity_score if nlp else 0

    views = get_metric(item, "view_count", 0)
    comments = get_metric(item, "comment_count", 0)

    youtube_bonus = 0
    if item.source.source_type == "youtube":
        youtube_bonus = min(1.5, views / 100000) + min(0.75, comments / 5000)

    recency_bonus = 0
    if item.published_at:
        hours_old = max(
            1,
            (timezone.now() - item.published_at).total_seconds() / 3600,
        )
        recency_bonus = min(1.0, 24 / hours_old)

    return news_score + intensity + youtube_bonus + (0.25 * recency_bonus)


def top_counter_text(counter, limit=5):
    if not counter:
        return "none"

    return ", ".join(
        f"{clean_label(name)} ({count})"
        for name, count in counter.most_common(limit)
    )


def make_theme_sentences(topic_counter, topic_examples):
    sentences = []

    for topic, count in topic_counter.most_common(5):
        examples = topic_examples.get(topic, [])
        readable_topic = clean_label(topic)

        if examples:
            example_text = "; ".join(examples[:2])
            sentences.append(
                f"{readable_topic.title()} appeared in {count} items, including: {example_text}."
            )
        else:
            sentences.append(
                f"{readable_topic.title()} appeared in {count} items."
            )

    return sentences


def make_tamil_theme_sentences(topic_counter, topic_examples_ta):
    sentences = []

    for topic, count in topic_counter.most_common(5):
        examples = topic_examples_ta.get(topic, [])
        readable_topic = clean_label(topic)

        if examples:
            example_text = "; ".join(examples[:2])
            sentences.append(
                f"{readable_topic} தொடர்பான செய்திகள் {count} இடங்களில் வந்துள்ளன. உதாரணங்கள்: {example_text}."
            )
        else:
            sentences.append(
                f"{readable_topic} தொடர்பான செய்திகள் {count} இடங்களில் வந்துள்ளன."
            )

    return sentences


class Command(BaseCommand):
    help = "Build a clear Tamil Nadu News Intelligence report for a given period."

    # Window length (in hours) for each report period.
    PERIOD_HOURS = {
        "daily": 24,
        "weekly": 24 * 7,
        "monthly": 24 * 30,
        "annual": 24 * 365,
    }

    # Human-readable window label used in the summary text.
    PERIOD_LABEL = {
        "daily": "24 hours",
        "weekly": "7 days",
        "monthly": "30 days",
        "annual": "year",
    }

    def add_arguments(self, parser):
        parser.add_argument(
            "--period",
            default="daily",
            choices=["daily", "weekly", "monthly", "annual"],
            help="which report window to build",
        )
        parser.add_argument(
            "--hours",
            type=int,
            default=None,
            help="override the window length; defaults to the period's span",
        )
        parser.add_argument("--top", type=int, default=10)

    def handle(self, *args, **options):
        period = options["period"]
        hours = options["hours"] or self.PERIOD_HOURS[period]
        top_n = options["top"]

        window_label = self.PERIOD_LABEL.get(period, f"{hours} hours")

        now = timezone.now()
        since = now - timedelta(hours=hours)
        report_date = now.date()

        items = list(
            ContentItem.objects
            .select_related("source", "nlp")
            .filter(published_at__gte=since)
            .order_by("-published_at", "-created_at")
        )

        if not items:
            DailyReport.objects.update_or_create(
                report_date=report_date,
                period=period,
                defaults={
                    "summary_en": "No Tamil Nadu news items were available for the selected reporting window.",
                    "summary_ta": "தேர்ந்தெடுக்கப்பட்ட காலப்பகுதியில் தமிழ்நாடு செய்திகள் எதுவும் கிடைக்கவில்லை.",
                    "top_stories": [],
                    "source_coverage": {
                        "total_items": 0,
                        "news_site_items": 0,
                        "youtube_items": 0,
                        "x_items": 0,
                    },
                    "party_mentions": {},
                    "topic_mentions": {},
                    "district_mentions": {},
                },
            )

            self.stdout.write(self.style.WARNING(
                f"No items found for {period} window. Empty report created."
            ))
            return

        topic_counter = Counter()
        party_counter = Counter()
        people_counter = Counter()
        district_counter = Counter()
        source_counter = Counter()
        source_type_counter = Counter()
        sentiment_counter = Counter()

        topic_examples_en = defaultdict(list)
        topic_examples_ta = defaultdict(list)

        youtube_items = []
        news_site_items = []
        x_items = []

        for item in items:
            source_counter.update([item.source.name])
            source_type_counter.update([item.source.source_type])

            if item.source.source_type == "youtube":
                youtube_items.append(item)
            elif item.source.source_type == "news_site":
                news_site_items.append(item)
            elif item.source.source_type == "x":
                x_items.append(item)

            nlp = getattr(item, "nlp", None)

            if not nlp:
                continue

            topic_counter.update(nlp.topics or [])
            party_counter.update(nlp.parties or [])
            people_counter.update(nlp.people or [])
            district_counter.update(nlp.districts or [])

            if nlp.sentiment:
                sentiment_counter.update([nlp.sentiment])

            for topic in nlp.topics or []:
                title_en = safe_title(item, "en")
                title_ta = safe_title(item, "ta")

                if title_en and len(topic_examples_en[topic]) < 3:
                    topic_examples_en[topic].append(title_en)

                if title_ta and len(topic_examples_ta[topic]) < 3:
                    topic_examples_ta[topic].append(title_ta)

        ranked_items = sorted(items, key=item_score, reverse=True)

        top_stories = []

        for item in ranked_items:
            if len(top_stories) >= top_n:
                break

            nlp = getattr(item, "nlp", None)

            title_en = safe_title(item, "en")
            title_ta = safe_title(item, "ta")

            # Do not include garbage stories in Top Developments.
            if not title_en and not title_ta:
                continue

            summary_en = safe_summary(nlp, "en")
            summary_ta = safe_summary(nlp, "ta")

            top_stories.append({
                "id": item.id,
                "source": item.source.name,
                "source_type": item.source.source_type,
                "content_type": item.content_type,
                "title_en": title_en,
                "title_ta": title_ta,
                "summary_en": summary_en,
                "summary_ta": summary_ta,
                "url": item.url,
                "published_at": item.published_at.isoformat() if item.published_at else None,
                "topics": nlp.topics if nlp else [],
                "people": nlp.people if nlp else [],
                "parties": nlp.parties if nlp else [],
                "districts": nlp.districts if nlp else [],
                "sentiment": nlp.sentiment if nlp else "",
                "emotion": nlp.emotion if nlp else "",
                "intensity_score": nlp.intensity_score if nlp else 0,
                "news_relevance_score": nlp.news_relevance_score if nlp else 0,
                "view_count": get_metric(item, "view_count", 0),
                "comment_count": get_metric(item, "comment_count", 0),
            })

        top_youtube = sorted(
            youtube_items,
            key=lambda item: (
                get_metric(item, "view_count", 0),
                get_metric(item, "comment_count", 0),
                item.published_at or timezone.now(),
            ),
            reverse=True,
        )[:8]

        youtube_highlights = []

        for item in top_youtube:
            title_en = safe_title(item, "en")
            title_ta = safe_title(item, "ta")

            if not title_en and not title_ta:
                continue

            youtube_highlights.append({
                "source": item.source.name,
                "title_en": title_en,
                "title_ta": title_ta,
                "url": item.url,
                "view_count": get_metric(item, "view_count", 0),
                "comment_count": get_metric(item, "comment_count", 0),
                "video_id": (item.metrics or {}).get("video_id", ""),
                "thumbnail_url": (item.metrics or {}).get("thumbnail_url", ""),
            })

        theme_sentences_en = make_theme_sentences(topic_counter, topic_examples_en)
        theme_sentences_ta = make_tamil_theme_sentences(topic_counter, topic_examples_ta)

        top_sources_text = top_counter_text(source_counter, 5)
        top_parties_text = top_counter_text(party_counter, 6)
        top_people_text = top_counter_text(people_counter, 6)
        top_topics_text = top_counter_text(topic_counter, 5)

        youtube_sentence_en = (
            f"YouTube contributed {len(youtube_items)} tracked videos, which means video commentary is a major part of the Tamil Nadu news signal in this window."
            if youtube_items
            else "No YouTube videos were tracked in this reporting window."
        )

        youtube_sentence_ta = (
            f"யூடியூப் வழியாக {len(youtube_items)} வீடியோக்கள் கண்காணிக்கப்பட்டன. எனவே வீடியோ செய்தி மற்றும் கருத்துரைகள் இந்த காலப்பகுதியின் செய்திச் சூழலில் முக்கிய பங்கு வகிக்கின்றன."
            if youtube_items
            else "இந்த அறிக்கை காலப்பகுதியில் யூடியூப் வீடியோக்கள் கண்காணிக்கப்படவில்லை."
        )

        summary_en_parts = [
            f"Executive overview: Over the past {window_label}, the system analyzed {len(items)} Tamil Nadu news items, including {len(news_site_items)} news-site items and {len(youtube_items)} YouTube videos.",
            f"Main issue clusters: {top_topics_text}.",
            f"Political and organizational signal: the most repeated parties or organizations were {top_parties_text}.",
            f"People signal: the most visible individuals or public figures were {top_people_text}.",
            f"Source signal: coverage was led by {top_sources_text}.",
            youtube_sentence_en,
        ]

        if theme_sentences_en:
            summary_en_parts.append("Issue details: " + " ".join(theme_sentences_en[:4]))

        if top_stories:
            story_titles = [
                story["title_en"]
                for story in top_stories[:3]
                if story.get("title_en")
            ]
            if story_titles:
                summary_en_parts.append(
                    "Top developments to review: " + " | ".join(story_titles) + "."
                )

        summary_en_parts.append(
            "What to watch next: whether TVK-related coverage continues to dominate, whether DMK/AIADMK responses increase, and whether education or health stories move from isolated reports into broader political debate."
        )

        summary_en = "\n\n".join(summary_en_parts)

        summary_ta_parts = [
            f"சுருக்கம்: கடந்த {window_label} காலப்பகுதியில் {len(items)} தமிழ்நாடு செய்திகள் பகுப்பாய்வு செய்யப்பட்டன. இதில் {len(news_site_items)} செய்தித் தள செய்திகள் மற்றும் {len(youtube_items)} யூடியூப் வீடியோக்கள் உள்ளன.",
            f"முக்கிய தலைப்புகள்: {top_topics_text}.",
            f"அரசியல்/அமைப்பு சிக்னல்: அதிகம் குறிப்பிடப்பட்ட கட்சிகள் அல்லது அமைப்புகள் {top_parties_text}.",
            f"நபர்கள் குறித்த சிக்னல்: அதிகம் குறிப்பிடப்பட்டவர்கள் {top_people_text}.",
            f"மூலங்கள்: செய்தி பரப்பில் முன்னிலையில் இருந்தவை {top_sources_text}.",
            youtube_sentence_ta,
        ]

        if theme_sentences_ta:
            summary_ta_parts.append("விவரங்கள்: " + " ".join(theme_sentences_ta[:4]))

        summary_ta_parts.append(
            "அடுத்து கவனிக்க வேண்டியது: TVK தொடர்பான செய்தி அலை தொடருமா, DMK/AIADMK பதில்கள் அதிகரிக்குமா, கல்வி அல்லது சுகாதார செய்திகள் பெரிய அரசியல் விவாதமாக மாறுமா என்பதே முக்கியம்."
        )

        summary_ta = "\n\n".join(summary_ta_parts)

        source_coverage = {
            "total_items": len(items),
            "news_site_items": len(news_site_items),
            "youtube_items": len(youtube_items),
            "x_items": len(x_items),
            "source_counts": dict(source_counter.most_common(30)),
            "source_type_counts": dict(source_type_counter),
            "sentiment_counts": dict(sentiment_counter),
            "youtube_highlights": youtube_highlights,
            "people_mentions": dict(people_counter.most_common(20)),
        }

        DailyReport.objects.update_or_create(
            report_date=report_date,
            period=period,
            defaults={
                "summary_en": summary_en,
                "summary_ta": summary_ta,
                "top_stories": top_stories,
                "source_coverage": source_coverage,
                "party_mentions": dict(party_counter.most_common(20)),
                "topic_mentions": dict(topic_counter.most_common(20)),
                "district_mentions": dict(district_counter.most_common(20)),
            },
        )

        self.stdout.write(self.style.SUCCESS(
            f"Built {period} report for {report_date}. "
            f"Window: {window_label}. Items: {len(items)}. "
            f"News sites: {len(news_site_items)}. "
            f"YouTube: {len(youtube_items)}. Top stories: {len(top_stories)}."
        ))