import csv
import hashlib
from datetime import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone

from aggregator.models import ContentItem, JobListing, RawItem, Source


def make_hash(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def parse_date(value):
    if not value:
        return None

    for fmt in ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"]:
        try:
            dt = datetime.strptime(value, fmt)
            return timezone.make_aware(dt)
        except ValueError:
            pass

    return None


def parse_int(value):
    if not value:
        return None

    cleaned = (
        str(value)
        .replace(",", "")
        .replace("₹", "")
        .replace("INR", "")
        .strip()
    )

    try:
        return int(float(cleaned))
    except ValueError:
        return None


class Command(BaseCommand):
    help = "Import Tamil Nadu jobs from a CSV file."

    def add_arguments(self, parser):
        parser.add_argument("csv_path", type=str)

    def handle(self, *args, **options):
        csv_path = options["csv_path"]

        source, _ = Source.objects.update_or_create(
            name="Imported Jobs",
            defaults={
                "source_type": "jobs",
                "crawl_method": "job_csv",
                "language": "en",
                "is_active": True,
            },
        )

        created_count = 0
        updated_count = 0

        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)

            for row in reader:
                role = (row.get("role") or row.get("title") or "").strip()
                company = (row.get("company") or "").strip()
                location = (row.get("location") or "").strip()
                district = (row.get("district") or "").strip()
                salary_text = (row.get("salary_text") or row.get("salary") or "").strip()
                salary_min = parse_int(row.get("salary_min"))
                salary_max = parse_int(row.get("salary_max"))
                category = (row.get("category") or "").strip()
                skills_raw = (row.get("skills") or "").strip()
                url = (row.get("url") or row.get("apply_url") or "").strip()
                description = (row.get("description") or "").strip()
                posted_at = parse_date(row.get("posted_at") or row.get("date"))

                if not role:
                    continue

                external_id = make_hash(f"{role}|{company}|{location}|{url}")

                raw_item, _ = RawItem.objects.update_or_create(
                    source=source,
                    external_id=external_id,
                    defaults={
                        "url": url,
                        "title": role,
                        "description": description,
                        "raw_text": description,
                        "raw_json": row,
                        "published_at": posted_at,
                        "content_hash": external_id,
                        "status": "fetched",
                    },
                )

                content_item, content_created = ContentItem.objects.update_or_create(
                    raw_item=raw_item,
                    defaults={
                        "source": source,
                        "content_type": "job_post",
                        "title_en": role,
                        "body_en": description,
                        "url": url,
                        "published_at": posted_at,
                        "metrics": {
                            "company": company,
                            "location": location,
                            "district": district,
                            "salary_text": salary_text,
                        },
                    },
                )

                skills = [
                    skill.strip()
                    for skill in skills_raw.split(",")
                    if skill.strip()
                ]

                job, job_created = JobListing.objects.update_or_create(
                    content_item=content_item,
                    defaults={
                        "company": company,
                        "role": role,
                        "location": location,
                        "district": district,
                        "salary_text": salary_text,
                        "salary_min": salary_min,
                        "salary_max": salary_max,
                        "category": category,
                        "skills": skills,
                        "apply_url": url,
                        "posted_at": posted_at,
                        "is_active": True,
                    },
                )

                if job_created:
                    created_count += 1
                else:
                    updated_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"Imported jobs. Created: {created_count}. Updated: {updated_count}."
        ))