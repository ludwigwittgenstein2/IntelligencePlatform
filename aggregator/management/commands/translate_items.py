from django.core.management.base import BaseCommand

from aggregator.models import ContentItem
from aggregator.services.translation import translate_text, translation_status


class Command(BaseCommand):
    help = 'Fill Tamil-English translation fields for content items when a translation provider is configured'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=100)
        parser.add_argument('--overwrite', action='store_true')
        parser.add_argument('--body-chars', type=int, default=4000)

    def handle(self, *args, **options):
        status = translation_status()
        if not status['configured']:
            self.stdout.write(self.style.WARNING(
                'No translation provider configured. Set TRANSLATION_PROVIDER=libretranslate or openai_compatible in .env.'
            ))
            return

        qs = ContentItem.objects.select_related('source').order_by('-published_at', '-created_at')
        if not options['overwrite']:
            qs = qs.filter(title_en='')
        qs = qs[:options['limit']]

        updated = 0
        skipped = 0
        for item in qs:
            title_en = item.title_en
            body_en = item.body_en

            if options['overwrite'] or not title_en:
                title_en = translate_text(item.title_ta, source='ta', target='en')
            if options['overwrite'] or not body_en:
                body_en = translate_text((item.body_ta or '')[:options['body_chars']], source='ta', target='en')

            if title_en or body_en:
                item.title_en = title_en or item.title_en
                item.body_en = body_en or item.body_en
                item.save(update_fields=['title_en', 'body_en'])
                updated += 1
            else:
                skipped += 1

        self.stdout.write(self.style.SUCCESS(
            f'Translation complete. Updated={updated}, Skipped={skipped}, Provider={status["provider"]}'
        ))
