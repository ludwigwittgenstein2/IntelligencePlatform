from django.core.management.base import BaseCommand
from aggregator.models import ContentItem, NLPResult
from aggregator.services.nlp import analyze_content_item


class Command(BaseCommand):
    help = 'Run Tamil Nadu news intelligence NLP baseline over content items'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=200)
        parser.add_argument('--overwrite', action='store_true')

    def handle(self, *args, **options):
        qs = ContentItem.objects.select_related('source').order_by('-published_at', '-created_at')
        if not options['overwrite']:
            qs = qs.filter(nlp__isnull=True)
        qs = qs[:options['limit']]

        created = 0
        updated = 0
        for item in qs:
            analysis = analyze_content_item(item)
            _, was_created = NLPResult.objects.update_or_create(
                content_item=item,
                defaults=analysis,
            )
            created += int(was_created)
            updated += int(not was_created)

        self.stdout.write(self.style.SUCCESS(f'NLP complete. Created={created}, Updated={updated}'))
