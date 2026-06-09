from django.core.management.base import BaseCommand

from aggregator.models import Source


# Keyed on `name` because Source.name is unique=True (url is NOT unique).
# extract_mode tells the crawler which strategy to use — see models_patches.py.
JOB_SOURCES = [
    {
        "name": "TNPSC Notifications",
        "url": "https://www.tnpsc.gov.in/english/notification.aspx",
        "extract_mode": Source.ExtractMode.LISTING_PDF,
        "notes": "Notifications are PDFs; applications happen on tnpscexams.in. Parse PDF for post/qualification/deadline.",
    },
    {
        "name": "Tamil Nadu Medical Services Recruitment Board (MRB)",
        "url": "https://www.mrb.tn.gov.in/notifications.html",   # verified real listing page
        "extract_mode": Source.ExtractMode.LISTING_PDF,
        "notes": "Follow each notification link; details live in PDFs.",
    },
    {
        "name": "Tamil Nadu Teachers Recruitment Board (TRB)",
        "url": "https://www.trb.tn.gov.in/",
        "extract_mode": Source.ExtractMode.LISTING_PDF,
        "notes": "Homepage links to notification PDFs. Confirm the notifications path before trusting output.",
    },
    {
        "name": "TN Uniformed Services Recruitment Board (TNUSRB)",
        "url": "https://www.tnusrbonline.org/",
        "extract_mode": Source.ExtractMode.LISTING_PDF,
        "notes": "Police recruitment — very large aspirant audience.",
    },
    {
        "name": "National Career Service - Tamil Nadu",
        "url": "https://www.ncs.gov.in/",
        "extract_mode": Source.ExtractMode.SPA_API,
        "notes": "JS SPA. Plain HTML is an empty shell — use the NCS JSON API or headless browser.",
    },
    {
        "name": "Apprenticeship India",
        "url": "https://www.apprenticeshipindia.gov.in/",
        "extract_mode": Source.ExtractMode.SPA_API,
        "notes": "JS SPA. Same constraint as NCS.",
    },
]


class Command(BaseCommand):
    help = "Seed public Tamil Nadu job sources (verified URLs, keyed on unique name)."

    def handle(self, *args, **options):
        created = updated = 0
        for item in JOB_SOURCES:
            source, was_created = Source.objects.update_or_create(
                name=item["name"],                       # unique field -> safe key
                defaults={
                    "source_type": Source.SourceType.JOBS,
                    "crawl_method": Source.CrawlMethod.JOB_HTML,
                    "url": item["url"],
                    "language": "en",
                    "is_active": True,
                    "extract_mode": item["extract_mode"],
                    "notes": item["notes"],
                },
            )
            verb = "Created" if was_created else "Updated"
            style = self.style.SUCCESS if was_created else self.style.WARNING
            self.stdout.write(style(f"{verb}: {source.name}  [{item['extract_mode']}]"))
            created += was_created
            updated += not was_created

        self.stdout.write(self.style.SUCCESS(f"Done. Created: {created}. Updated: {updated}."))
        self.stdout.write(self.style.NOTICE(
            "spa_api sources return empty if crawled as plain HTML; "
            "listing_pdf sources need a PDF-parsing step. Don't ship either as naive JOB_HTML."
        ))