from django.core.management.base import BaseCommand

from aggregator.models import Source


X_SOURCES = [
    {
        "name": "X - RedPix",
        "url": "https://x.com/redpixnews",
        "x_handle": "redpixnews",
        "x_query": "from:redpixnews -is:retweet",
    },
    {
        "name": "X - Savukku Media",
        "url": "https://x.com/Savukkumedia",
        "x_handle": "Savukkumedia",
        "x_query": "from:Savukkumedia -is:retweet",
    },
    {
        "name": "X - Savukku Shankar",
        "url": "https://x.com/SavukkuOfficial",
        "x_handle": "SavukkuOfficial",
        "x_query": "from:SavukkuOfficial -is:retweet",
    },
    {
        "name": "X - Maridhas",
        "url": "https://x.com/MaridhasAnswers",
        "x_handle": "MaridhasAnswers",
        "x_query": "from:MaridhasAnswers -is:retweet",
    },
    {
        "name": "X - Tamil Nadu Political Commentary",
        "url": "https://x.com/search?q=Tamil%20Nadu%20politics",
        "x_handle": "",
        "x_query": '(TamilNadu OR "Tamil Nadu" OR தமிழ்நாடு OR DMK OR AIADMK OR TVK OR BJP OR திமுக OR அதிமுக OR தவெக OR முதல்வர் OR சட்டசபை) lang:ta -is:retweet',
    },
]


class Command(BaseCommand):
    help = "Seed X/Twitter sources for NewsIQ."

    def handle(self, *args, **options):
        created_count = 0
        updated_count = 0

        for item in X_SOURCES:
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
                    "language": "ta",
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
                    f"{action}: {source.name} | query={source.x_query}"
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Created: {created_count}. Updated: {updated_count}."
            )
        )