import hashlib
import re

import feedparser
from django.core.management.base import BaseCommand
from django.utils.dateparse import parse_datetime
from django.utils import timezone

from aggregator.models import ContentItem, RawItem, Source


def make_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def extract_video_id(url: str) -> str:
    if not url:
        return ""

    patterns = [
        r"v=([^&]+)",
        r"youtu\.be/([^?&]+)",
        r"/shorts/([^?&]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    return ""


def parse_date(value):
    if not value:
        return None

    dt = parse_datetime(value)

    if dt is None:
        return None

    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone=timezone.utc)

    return dt


class Command(BaseCommand):
    help = "Crawl YouTube Tamil news channels using public YouTube RSS feeds. No API key required."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=10)
        parser.add_argument("--source", type=str, default="")

    def handle(self, *args, **options):
        limit = options["limit"]
        source_name = options["source"].strip()

        sources = Source.objects.filter(
            source_type="youtube",
            is_active=True,
        ).exclude(youtube_channel_id__isnull=True).exclude(youtube_channel_id="")

        if source_name:
            sources = sources.filter(name__icontains=source_name)

        created_count = 0
        updated_count = 0

        for source in sources:
            self.stdout.write(f"\nCrawling YouTube RSS: {source.name}")

            feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={source.youtube_channel_id}"
            feed = feedparser.parse(feed_url)

            if not feed.entries:
                self.stderr.write(f"  No entries found for {source.name}")
                continue

            for entry in feed.entries[:limit]:
                title = (entry.get("title") or "").strip()
                url = entry.get("link") or ""
                video_id = extract_video_id(url)
                published_at = parse_date(entry.get("published"))

                if not title or not video_id:
                    continue

                thumbnail_url = f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg"

                metrics = {
                    "video_id": video_id,
                    "thumbnail_url": thumbnail_url,
                    "view_count": 0,
                    "like_count": 0,
                    "comment_count": 0,
                    "crawl_method": "youtube_rss",
                }

                content_hash = make_hash(video_id + title)

                raw_item, raw_created = RawItem.objects.update_or_create(
                    source=source,
                    external_id=video_id,
                    defaults={
                        "url": url,
                        "title": title,
                        "description": "",
                        "raw_text": title,
                        "raw_json": dict(entry),
                        "published_at": published_at,
                        "content_hash": content_hash,
                        "status": "fetched",
                    },
                )

                content_item, content_created = ContentItem.objects.update_or_create(
                    raw_item=raw_item,
                    defaults={
                        "source": source,
                        "content_type": "youtube_video",
                        "title_ta": title,
                        "body_ta": "",
                        "url": url,
                        "published_at": published_at,
                        "metrics": metrics,
                    },
                )

                if content_created:
                    created_count += 1
                    self.stdout.write(f"  Created: {title[:90]}")
                else:
                    updated_count += 1
                    self.stdout.write(f"  Updated: {title[:90]}")

        self.stdout.write(self.style.SUCCESS(
            f"\nDone. Created: {created_count}. Updated: {updated_count}."
        ))