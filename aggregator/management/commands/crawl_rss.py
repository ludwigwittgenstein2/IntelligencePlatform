from django.core.management.base import BaseCommand
from aggregator.models import Source
from aggregator.services.rss import crawl_rss_source


class Command(BaseCommand):
    help = 'Crawl RSS sources and store raw + normalized content items'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=30)

    def handle(self, *args, **options):
        sources = Source.objects.filter(is_active=True, crawl_method=Source.CrawlMethod.RSS)
        if not sources.exists():
            self.stdout.write(self.style.WARNING('No active RSS sources found. Run seed_sources first.'))
            return

        total_created = 0
        total_skipped = 0
        for source in sources:
            result = crawl_rss_source(source, limit=options['limit'])
            total_created += result.get('created', 0)
            total_skipped += result.get('skipped', 0)
            self.stdout.write(f'{source.name}: {result}')

        self.stdout.write(self.style.SUCCESS(f'RSS crawl complete. Created={total_created}, Skipped={total_skipped}'))
