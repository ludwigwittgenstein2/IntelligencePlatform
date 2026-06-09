import feedparser
from django.db import IntegrityError
from django.utils import timezone

from aggregator.models import ContentItem, RawItem, Source
from .utils import clean_text, html_to_text, parse_datetime, sha256_text


def crawl_rss_source(source: Source, limit: int = 30):
    if not source.rss_url:
        return {'created': 0, 'skipped': 0, 'error': 'missing rss_url'}

    feed = feedparser.parse(source.rss_url)
    created = 0
    skipped = 0

    for entry in feed.entries[:limit]:
        link = entry.get('link', '')
        title = clean_text(entry.get('title', ''))
        summary_html = entry.get('summary', '') or entry.get('description', '')
        summary = html_to_text(summary_html)
        published = parse_datetime(entry.get('published') or entry.get('updated'))
        external_id = entry.get('id') or link or sha256_text(title + summary)
        content_hash = sha256_text(source.name + external_id + title)

        try:
            raw, raw_created = RawItem.objects.get_or_create(
                source=source,
                external_id=external_id,
                defaults={
                    'url': link,
                    'title': title,
                    'description': summary,
                    'raw_text': summary,
                    'raw_html': summary_html,
                    'raw_json': dict(entry),
                    'published_at': published,
                    'fetched_at': timezone.now(),
                    'content_hash': content_hash,
                    'status': 'normalized',
                }
            )
        except IntegrityError:
            skipped += 1
            continue

        if not raw_created:
            skipped += 1
            continue

        ContentItem.objects.create(
            raw_item=raw,
            source=source,
            content_type=ContentItem.ContentType.ARTICLE,
            title_ta=title,
            body_ta=summary,
            url=link,
            published_at=published,
            metrics={},
        )
        created += 1

    return {'created': created, 'skipped': skipped, 'feed_title': feed.feed.get('title', '')}
