from pathlib import Path
import yaml
from django.conf import settings
from django.core.management.base import BaseCommand
from aggregator.models import Source


class Command(BaseCommand):
    help = 'Seed sources from sources.yaml'

    def add_arguments(self, parser):
        parser.add_argument('--file', default='sources.yaml')

    def handle(self, *args, **options):
        path = Path(settings.BASE_DIR) / options['file']
        if not path.exists():
            self.stderr.write(self.style.ERROR(f'File not found: {path}'))
            return

        data = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
        rows = []
        rows.extend(data.get('news_sites', []))
        rows.extend(data.get('youtube_channels', []))
        rows.extend(data.get('x_queries', []))

        created = 0
        updated = 0
        for row in rows:
            name = row['name']
            defaults = {
                'source_type': row.get('type', 'news_site'),
                'url': row.get('url', '') or '',
                'rss_url': row.get('rss_url', '') or '',
                'youtube_channel_id': row.get('youtube_channel_id', '') or '',
                'x_handle': row.get('x_handle', '') or '',
                'x_query': row.get('x_query', '') or '',
                'crawl_method': row.get('crawl_method', 'rss'),
                'language': row.get('language', 'ta'),
                'is_active': row.get('is_active', True),
            }
            _, was_created = Source.objects.update_or_create(name=name, defaults=defaults)
            created += int(was_created)
            updated += int(not was_created)

        self.stdout.write(self.style.SUCCESS(f'Seeded sources. Created={created}, Updated={updated}'))
