import os
import requests
from django.core.management.base import BaseCommand
from django.utils import timezone

from aggregator.models import ContentItem, RawItem, Source
from aggregator.services.utils import clean_text, parse_datetime, safe_int, sha256_text


class Command(BaseCommand):
    help = 'Crawl X/Twitter recent search queries. Requires X_BEARER_TOKEN.'

    def add_arguments(self, parser):
        parser.add_argument('--max-results', type=int, default=25)

    def handle(self, *args, **options):
        token = os.getenv('X_BEARER_TOKEN', '')
        if not token:
            self.stderr.write(self.style.ERROR('Missing X_BEARER_TOKEN in .env'))
            return

        base_url = os.getenv('X_API_BASE_URL', 'https://api.x.com/2').rstrip('/')
        endpoint = f'{base_url}/tweets/search/recent'
        headers = {'Authorization': f'Bearer {token}'}

        sources = Source.objects.filter(is_active=True, crawl_method=Source.CrawlMethod.X_API)
        if not sources.exists():
            self.stdout.write(self.style.WARNING('No active X sources found. Run seed_sources first.'))
            return

        for source in sources:
            if not source.x_query:
                self.stdout.write(f'{source.name}: skipped, missing x_query')
                continue

            params = {
                'query': source.x_query,
                'max_results': min(max(options['max_results'], 10), 100),
                'tweet.fields': 'created_at,public_metrics,lang,author_id',
                'expansions': 'author_id',
                'user.fields': 'username,name',
            }
            response = requests.get(endpoint, headers=headers, params=params, timeout=30)
            if response.status_code >= 400:
                self.stderr.write(self.style.ERROR(f'{source.name}: {response.status_code} {response.text[:500]}'))
                continue

            data = response.json()
            users = {u['id']: u for u in data.get('includes', {}).get('users', [])}
            created = 0
            skipped = 0

            for tweet in data.get('data', []):
                tweet_id = tweet.get('id', '')
                text = clean_text(tweet.get('text', ''))
                user = users.get(tweet.get('author_id'), {})
                username = user.get('username', '')
                url = f'https://x.com/{username}/status/{tweet_id}' if username else ''
                published = parse_datetime(tweet.get('created_at'))
                metrics = tweet.get('public_metrics', {}) or {}
                external_id = tweet_id
                content_hash = sha256_text(source.name + external_id + text)

                raw, raw_created = RawItem.objects.get_or_create(
                    source=source,
                    external_id=external_id,
                    defaults={
                        'url': url,
                        'title': text[:250],
                        'description': text,
                        'raw_text': text,
                        'raw_json': tweet,
                        'published_at': published,
                        'fetched_at': timezone.now(),
                        'content_hash': content_hash,
                        'status': 'normalized',
                    }
                )
                if not raw_created:
                    skipped += 1
                    continue

                ContentItem.objects.create(
                    raw_item=raw,
                    source=source,
                    content_type=ContentItem.ContentType.TWEET,
                    title_ta=text[:250],
                    body_ta=text,
                    url=url,
                    author=username,
                    published_at=published,
                    metrics={
                        'retweet_count': safe_int(metrics.get('retweet_count')),
                        'reply_count': safe_int(metrics.get('reply_count')),
                        'like_count': safe_int(metrics.get('like_count')),
                        'quote_count': safe_int(metrics.get('quote_count')),
                    },
                )
                created += 1

            self.stdout.write(f'{source.name}: Created={created}, Skipped={skipped}')
