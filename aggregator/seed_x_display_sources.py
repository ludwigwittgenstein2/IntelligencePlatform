from django.core.management.base import BaseCommand

from aggregator.models import Source


X_DISPLAY_SOURCES = [
    {
        "name": "X - RedPix",
        "url": "https://x.com/redpixnews",
        "x_handle": "redpixnews",
        "x_query": "",
        "language": "ta",
    },
    {
        "name": "X - Savukku Media",
        "url": "https://x.com/Savukkumedia",
        "x_handle": "Savukkumedia",
        "x_query": "",
        "language": "ta",
    },
    {
        "name": "X - Savukku Shankar",
        "url": "https://x.com/SavukkuOfficial",
        "x_handle": "SavukkuOfficial",
        "x_query": "",
        "language": "ta",
    },
    {
        "name": "X - Maridhas",
        "url": "https://x.com/MaridhasAnswers",
        "x_handle": "MaridhasAnswers",
        "x_query": "",
        "language": "ta",
    },
]


class Command(BaseCommand):
    help = "Seed free X/Twitter display sources for NewsIQ."

    def handle(self, *args, **options):
        created_count = 0
        updated_count = 0

        for item in X_DISPLAY_SOURCES:
            source, created = Source.objects.update_or_create(
                name=item["name"],
                defaults={
                    "source_type": Source.SourceType.X,
                    "crawl_method": Source.CrawlMethod.X_API,

                    "url": item["url"],
                    "rss_url": "",

                    "youtube_channel_id": "",

                    "x_handle": item["x_handle"],
                    "x_query": item["x_query"],

                    "language": item["language"],
                    "is_active": True,
                },
            )

            if created:
                created_count += 1
                action = "Created"
            else:
                updated_count += 1
                action = "Updated"

            self.stdout.write(
                self.style.SUCCESS(
                    f"{action}: {source.name} | @{source.x_handle}"
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Created: {created_count}. Updated: {updated_count}."
            )
        )