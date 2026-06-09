from django.core.management.base import BaseCommand
from django.db import transaction

from aggregator.models import ContentItem, NLPResult
from aggregator.services.ollama_translate import (
    translate_to_english,
    translate_to_tamil,
    summarize_in_english,
    summarize_in_tamil,
)


def has_tamil(text: str) -> bool:
    if not text:
        return False

    for char in text:
        if "\u0B80" <= char <= "\u0BFF":
            return True

    return False


def clean_text(text: str, max_chars: int = 3000) -> str:
    if not text:
        return ""

    text = " ".join(text.split())
    return text[:max_chars]


class Command(BaseCommand):
    help = "Use Ollama to fill missing English/Tamil titles and summaries."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50)
        parser.add_argument("--summaries", action="store_true")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        limit = options["limit"]
        do_summaries = options["summaries"]
        dry_run = options["dry_run"]

        items = (
            ContentItem.objects
            .select_related("source")
            .order_by("-published_at", "-created_at")[:limit]
        )

        updated_items = 0
        updated_nlp = 0

        for item in items:
            changed = False

            title_ta = clean_text(item.title_ta, 800)
            title_en = clean_text(item.title_en, 800)

            body_ta = clean_text(item.body_ta, 3000)
            body_en = clean_text(item.body_en, 3000)

            self.stdout.write(f"\nProcessing item {item.id}: {item.source.name}")

            try:
                if title_ta and not title_en:
                    self.stdout.write("  Translating title Tamil → English")
                    item.title_en = translate_to_english(title_ta)
                    changed = True

                if title_en and not title_ta:
                    self.stdout.write("  Translating title English → Tamil")
                    item.title_ta = translate_to_tamil(title_en)
                    changed = True

                if body_ta and not body_en:
                    self.stdout.write("  Translating body Tamil → English")
                    item.body_en = translate_to_english(body_ta)
                    changed = True

                if body_en and not body_ta:
                    self.stdout.write("  Translating body English → Tamil")
                    item.body_ta = translate_to_tamil(body_en)
                    changed = True

                if changed and not dry_run:
                    with transaction.atomic():
                        item.save(update_fields=["title_ta", "title_en", "body_ta", "body_en"])

                    updated_items += 1

                if do_summaries:
                    nlp, _ = NLPResult.objects.get_or_create(content_item=item)

                    nlp_changed = False

                    source_text_en = clean_text(item.body_en or item.title_en, 3000)
                    source_text_ta = clean_text(item.body_ta or item.title_ta, 3000)

                    if not nlp.summary_en and source_text_en:
                        self.stdout.write("  Creating English summary")
                        nlp.summary_en = summarize_in_english(source_text_en)
                        nlp_changed = True

                    if not nlp.summary_ta and source_text_ta:
                        self.stdout.write("  Creating Tamil summary")
                        nlp.summary_ta = summarize_in_tamil(source_text_ta)
                        nlp_changed = True

                    if nlp.summary_ta and not nlp.summary_en:
                        self.stdout.write("  Translating summary Tamil → English")
                        nlp.summary_en = translate_to_english(nlp.summary_ta)
                        nlp_changed = True

                    if nlp.summary_en and not nlp.summary_ta:
                        self.stdout.write("  Translating summary English → Tamil")
                        nlp.summary_ta = translate_to_tamil(nlp.summary_en)
                        nlp_changed = True

                    if nlp_changed and not dry_run:
                        with transaction.atomic():
                            nlp.save(update_fields=["summary_ta", "summary_en"])

                        updated_nlp += 1

            except Exception as exc:
                self.stderr.write(f"  ERROR item {item.id}: {exc}")

        self.stdout.write(self.style.SUCCESS(
            f"\nDone. Updated content items: {updated_items}. Updated NLP summaries: {updated_nlp}."
        ))