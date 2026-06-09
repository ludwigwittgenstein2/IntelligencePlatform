import hashlib
import re
from datetime import date, datetime, timedelta
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from aggregator.classifiers import classify_recruiting_body, classify_qualification
from aggregator.models import ContentItem, JobListing, RawItem, Source


TN_DISTRICTS = [
    "Ariyalur", "Chengalpattu", "Chennai", "Coimbatore", "Cuddalore",
    "Dharmapuri", "Dindigul", "Erode", "Kallakurichi", "Kanchipuram",
    "Kanniyakumari", "Karur", "Krishnagiri", "Madurai", "Mayiladuthurai",
    "Nagapattinam", "Namakkal", "Nilgiris", "Perambalur", "Pudukkottai",
    "Ramanathapuram", "Ranipet", "Salem", "Sivaganga", "Tenkasi",
    "Thanjavur", "Theni", "Thoothukudi", "Tiruchirappalli", "Tirunelveli",
    "Tirupathur", "Tiruppur", "Tiruvallur", "Tiruvannamalai", "Tiruvarur",
    "Vellore", "Viluppuram", "Virudhunagar",
]

BAD_TITLE_PHRASES = [
    "rti",
    "resources",
    "general resources",
    "reports & documents",
    "employment exchange",
    "career center handbook",
    "list of model career centers",
    "model career center",
    "job bulletin",
    "create job fairs",
    "job fairs and events",
    "career center login",
    "other",
    "notification no. notification date post name",
    "notification no notification date post name",
    "home",
    "about us",
    "contact us",
    "privacy policy",
    "terms",
    "sitemap",
    "login",
    "register",
]

# FIX 1: removed the over-generic "post" / "posts" (and "staff") -- they matched
# nav furniture like "Post New Jobs", which is exactly how the NCS menu links
# leaked in. Government rows still pass via "notification" / "recruitment".
REAL_JOB_WORDS = [
    "recruitment",
    "notification",
    "vacancy",
    "vacancies",
    "apply",
    "application",
    "exam",
    "examination",
    "engineer",
    "assistant",
    "officer",
    "nurse",
    "doctor",
    "teacher",
    "lecturer",
    "professor",
    "technician",
    "operator",
    "apprentice",
    "trainee",
    "fitter",
    "welder",
    "developer",
    "manager",
    "clerk",
    "பணி",
    "வேலை",
    "வேலைவாய்ப்பு",
    "அறிவிப்பு",
    "விண்ணப்ப",
]

CATEGORY_KEYWORDS = {
    "IT": [
        "software", "developer", "python", "java", "django", "data analyst",
        "data scientist", "cloud", "network", "ai", "machine learning",
    ],
    "Healthcare": [
        "nurse", "doctor", "medical", "hospital", "pharmacist", "lab technician",
        "health", "mrb", "surgeon", "assistant surgeon",
    ],
    "Teaching": [
        "teacher", "professor", "lecturer", "school", "college", "faculty",
        "trb", "tet", "pg assistant", "graduate teacher",
    ],
    "Government": [
        "tnpsc", "mrb", "trb", "government", "public service",
        "combined civil services", "group i", "group ii", "group iv",
        "notification", "recruitment",
    ],
    "Manufacturing": [
        "fitter", "welder", "operator", "maintenance", "production",
        "mechanic", "electrical", "cnc", "factory", "technician",
    ],
    "Sales": [
        "sales", "marketing", "business development", "telecaller",
        "customer support",
    ],
    "Apprenticeship": [
        "apprentice", "apprenticeship", "trainee", "naps",
    ],
}

SALARY_RANGE_RE = re.compile(
    r"(?:₹|rs\.?|inr)\s*([0-9][0-9,]*)\s*(?:-|–|to)\s*(?:₹|rs\.?|inr)?\s*([0-9][0-9,]*)",
    re.IGNORECASE,
)

SALARY_SINGLE_RE = re.compile(
    r"(?:₹|rs\.?|inr)\s*([0-9][0-9,]*)",
    re.IGNORECASE,
)

DATE_RE = re.compile(
    r"(\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{4}[./-]\d{1,2}[./-]\d{1,2})"
)


def make_hash(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:64]


def clean_text(text):
    if not text:
        return ""

    return re.sub(r"\s+", " ", str(text)).strip()


def make_json_safe(value):
    """
    Convert Python objects into JSON-safe values.
    Django JSONField cannot directly store datetime/date objects.
    """

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, dict):
        return {
            str(key): make_json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [make_json_safe(item) for item in value]

    if isinstance(value, tuple):
        return [make_json_safe(item) for item in value]

    return value


def parse_int(value):
    if not value:
        return None

    cleaned = (
        str(value)
        .replace(",", "")
        .replace("₹", "")
        .replace("Rs.", "")
        .replace("Rs", "")
        .replace("INR", "")
        .strip()
    )

    try:
        return int(float(cleaned))
    except ValueError:
        return None


def contains_bad_phrase(text):
    text_lower = clean_text(text).lower()

    for phrase in BAD_TITLE_PHRASES:
        if phrase in text_lower:
            return True

    return False


def has_real_job_signal(text):
    text_lower = clean_text(text).lower()
    return any(word.lower() in text_lower for word in REAL_JOB_WORDS)


def detect_district(text):
    text_lower = clean_text(text).lower()

    for district in TN_DISTRICTS:
        if district.lower() in text_lower:
            return district

    if "tamil nadu" in text_lower or "tnpsc" in text_lower:
        return "Tamil Nadu"

    return ""


def detect_category(text, source_name=""):
    combined = f"{source_name} {text}".lower()

    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in combined:
                return category

    return ""


def detect_job_type(category, source_name, text):
    combined = f"{source_name} {text}".lower()

    if category == "Government":
        return JobListing.JobType.GOVERNMENT

    if category == "Apprenticeship":
        return JobListing.JobType.APPRENTICESHIP

    if "intern" in combined:
        return JobListing.JobType.INTERNSHIP

    if "contract" in combined:
        return JobListing.JobType.CONTRACT

    if "part time" in combined or "part-time" in combined:
        return JobListing.JobType.PART_TIME

    if "private" in combined:
        return JobListing.JobType.PRIVATE

    return JobListing.JobType.UNKNOWN


def parse_salary(text):
    text = clean_text(text)

    match = SALARY_RANGE_RE.search(text)
    if match:
        salary_min = parse_int(match.group(1))
        salary_max = parse_int(match.group(2))

        return {
            "salary_text": clean_text(match.group(0)),
            "salary_min": salary_min,
            "salary_max": salary_max,
        }

    match = SALARY_SINGLE_RE.search(text)
    if match:
        salary = parse_int(match.group(1))

        return {
            "salary_text": clean_text(match.group(0)),
            "salary_min": salary,
            "salary_max": salary,
        }

    return {
        "salary_text": "",
        "salary_min": None,
        "salary_max": None,
    }


def extract_dates(text):
    dates = []

    for match in DATE_RE.findall(text or ""):
        try:
            parsed = date_parser.parse(match, dayfirst=True, fuzzy=True)

            if parsed.year >= 2020:
                dates.append(parsed)
        except Exception:
            continue

    return dates


def parse_date_value(value):
    value = clean_text(value)

    if not value:
        return None

    try:
        parsed = date_parser.parse(value, dayfirst=True, fuzzy=True)

        if parsed.year < 2020:
            return None

        if timezone.is_naive(parsed):
            return timezone.make_aware(parsed)

        return parsed
    except Exception:
        return None


def choose_posted_at(text):
    dates = extract_dates(text)

    if dates:
        parsed = min(dates)

        if timezone.is_naive(parsed):
            return timezone.make_aware(parsed)

        return parsed

    return timezone.now()


def choose_deadline(text):
    dates = extract_dates(text)

    if not dates:
        return None

    today = date.today()
    future_dates = [d.date() for d in dates if d.date() >= today]

    if future_dates:
        return max(future_dates)

    return None


def fetch_html(url, timeout=60):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 TamilNaduJobsIQ/1.0 "
            "public jobs aggregator"
        )
    }

    response = requests.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.text


def validate_url(url):
    if not url:
        return False, JobListing.LinkStatus.BROKEN

    headers = {
        "User-Agent": "Mozilla/5.0 TamilNaduJobsIQ/1.0"
    }

    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=15,
            stream=True,
            allow_redirects=True,
        )

        if response.status_code < 400:
            return True, JobListing.LinkStatus.VALID

        if response.status_code in [401, 403, 429]:
            return False, JobListing.LinkStatus.BLOCKED

        return False, JobListing.LinkStatus.BROKEN

    except Exception:
        return False, JobListing.LinkStatus.BROKEN


def clean_role(title):
    title = clean_text(title)

    replacements = [
        "Recruitment to the post of",
        "Notification for the post of",
        "Applications are invited for",
        "Direct recruitment to the post of",
    ]

    for phrase in replacements:
        title = title.replace(phrase, "")

    title = clean_text(title)

    if len(title) > 255:
        title = title[:252] + "..."

    return title


def is_valid_candidate(candidate):
    title = clean_text(candidate.get("title", ""))
    description = clean_text(candidate.get("description", ""))
    url = clean_text(candidate.get("url", ""))

    combined = f"{title} {description}"

    if not title:
        return False

    if len(title) < 4:
        return False

    if contains_bad_phrase(title):
        return False

    if contains_bad_phrase(description) and not has_real_job_signal(description):
        return False

    if "notification date post name application date" in combined.lower():
        return False

    if not url:
        return False

    if not has_real_job_signal(combined):
        return False

    return True


def extract_tnpsc_candidates(source, soup):
    candidates = []

    for table in soup.find_all("table"):
        rows = table.find_all("tr")

        if not rows:
            continue

        header_cells = [
            clean_text(cell.get_text(" ", strip=True))
            for cell in rows[0].find_all(["th", "td"])
        ]

        header_lower = [h.lower() for h in header_cells]

        looks_like_tnpsc_table = (
            any("post name" in h for h in header_lower)
            or any("notification" in h for h in header_lower)
            or any("application" in h for h in header_lower)
        )

        if not looks_like_tnpsc_table:
            continue

        for row in rows[1:]:
            cells = [
                clean_text(cell.get_text(" ", strip=True))
                for cell in row.find_all(["td"])
            ]

            if len(cells) < 2:
                continue

            row_text = clean_text(" ".join(cells))

            if not row_text:
                continue

            if contains_bad_phrase(row_text):
                continue

            link = row.find("a", href=True)
            url = urljoin(source.url, link["href"]) if link else source.url

            post_name = ""

            for idx, header in enumerate(header_lower):
                if idx < len(cells) and "post name" in header:
                    post_name = cells[idx]
                    break

            if not post_name:
                meaningful_cells = [
                    cell for cell in cells
                    if len(cell) > 5 and not re.fullmatch(r"[\d./-]+", cell)
                ]
                post_name = max(meaningful_cells, key=len) if meaningful_cells else row_text[:180]

            if not post_name:
                continue

            notification_no = ""
            notification_date = ""
            application_date = ""
            payment_last_date = ""
            exam_date = ""

            for idx, header in enumerate(header_lower):
                if idx >= len(cells):
                    continue

                value = cells[idx]

                if "notification no" in header:
                    notification_no = value
                elif "notification date" in header:
                    notification_date = value
                elif "application" in header:
                    application_date = value
                elif "payment" in header:
                    payment_last_date = value
                elif "examination" in header or "exam" in header:
                    exam_date = value

            description_parts = [
                f"Post: {post_name}",
                f"Notification No: {notification_no}" if notification_no else "",
                f"Notification Date: {notification_date}" if notification_date else "",
                f"Application Date: {application_date}" if application_date else "",
                f"Payment Last Date: {payment_last_date}" if payment_last_date else "",
                f"Examination Date: {exam_date}" if exam_date else "",
            ]

            description = clean_text(" | ".join([p for p in description_parts if p]))

            posted_at = parse_date_value(notification_date)
            deadline_dt = parse_date_value(payment_last_date)

            # FIX 3: drop stale notifications instead of restamping them "today".
            # If a notification date was present but failed to parse (i.e. it was
            # pre-2020, which parse_date_value rejects -> None), the row is an
            # archived listing -- skip it. Also drop anything parsed to over a
            # year old. This is what stops the 2019 TNPSC rows from showing up
            # with a fake fresh posted_at.
            if notification_date and posted_at is None:
                continue
            if posted_at and posted_at < timezone.now() - timedelta(days=365):
                continue

            candidates.append({
                "title": post_name,
                "description": description or row_text,
                "url": url,
                "posted_at": posted_at,
                "deadline": deadline_dt.date() if deadline_dt else None,
                "category": "Government",
                "district": "Tamil Nadu",
                "company": "TNPSC",
            })

    return candidates


def _href_looks_useful(href):
    """A link only counts as a job link if its href points at a notification,
    application, vacancy page, or a PDF -- not a nav/menu target."""
    href_lower = (href or "").lower()
    return (
        href_lower.endswith(".pdf")
        or "notification" in href_lower
        or "recruit" in href_lower
        or "apply" in href_lower
        or "vacancy" in href_lower
    )


def extract_generic_candidates(source, soup):
    candidates = []

    for row in soup.find_all("tr"):
        row_text = clean_text(row.get_text(" ", strip=True))

        if not row_text:
            continue

        if contains_bad_phrase(row_text):
            continue

        if not has_real_job_signal(row_text):
            continue

        link = row.find("a", href=True)

        # FIX 2: the row loop now applies the same href gate the link loop
        # already used. Previously any <tr> with a job-ish word slipped through
        # with no link check -- that is how NCS rows like "Find Candidates"
        # (href=/jobseeker-list) became fake listings. No useful link -> skip.
        if not link or not _href_looks_useful(link.get("href", "")):
            continue

        url = urljoin(source.url, link["href"])

        candidates.append({
            "title": row_text[:180],
            "description": row_text,
            "url": url,
        })

    for link in soup.find_all("a", href=True):
        title = clean_text(link.get_text(" ", strip=True))
        href = link.get("href", "")
        url = urljoin(source.url, href)

        parent_text = clean_text(link.parent.get_text(" ", strip=True)) if link.parent else title
        combined = clean_text(f"{title} {parent_text} {href}")

        if not title:
            continue

        if contains_bad_phrase(title) or contains_bad_phrase(combined):
            continue

        if not has_real_job_signal(combined):
            continue

        if not _href_looks_useful(href):
            continue

        candidates.append({
            "title": title[:180],
            "description": combined,
            "url": url,
        })

    return candidates


def extract_candidates_for_source(source, html):
    soup = BeautifulSoup(html, "html.parser")
    source_name = source.name.lower()

    if "tnpsc" in source_name:
        candidates = extract_tnpsc_candidates(source, soup)
    else:
        candidates = extract_generic_candidates(source, soup)

    seen = set()
    unique = []

    for candidate in candidates:
        candidate["title"] = clean_role(candidate.get("title", ""))
        candidate["description"] = clean_text(candidate.get("description", ""))
        candidate["url"] = clean_text(candidate.get("url", ""))

        if not is_valid_candidate(candidate):
            continue

        key = make_hash(f"{candidate['title']}|{candidate['url']}")

        if key in seen:
            continue

        seen.add(key)
        unique.append(candidate)

    return unique


def upsert_job(source, candidate, validate_links=False):
    title = clean_role(candidate.get("title", ""))
    description = clean_text(candidate.get("description", ""))
    url = clean_text(candidate.get("url")) or source.url

    if not is_valid_candidate({
        "title": title,
        "description": description,
        "url": url,
    }):
        return None, False

    if validate_links:
        link_is_valid, link_status = validate_url(url)

        if not link_is_valid:
            return None, False
    else:
        link_is_valid = False
        link_status = JobListing.LinkStatus.UNCHECKED

    combined_text = clean_text(f"{title} {description}")

    external_id = make_hash(f"{source.name}|{url}|{title}")
    content_hash = make_hash(combined_text)

    salary = parse_salary(combined_text)

    district = candidate.get("district") or detect_district(combined_text)
    category = candidate.get("category") or detect_category(combined_text, source.name)
    company = candidate.get("company") or source.name

    posted_at = candidate.get("posted_at") or choose_posted_at(combined_text)
    deadline = candidate.get("deadline") or choose_deadline(combined_text)

    job_type = detect_job_type(category, source.name, combined_text)
    recruiting_body = classify_recruiting_body(source.name, combined_text)
    qualification_level = classify_qualification(combined_text)

    raw_item, _ = RawItem.objects.update_or_create(
        source=source,
        external_id=external_id,
        defaults={
            "url": url,
            "title": title,
            "description": description,
            "raw_text": description,
            "raw_html": "",
            "raw_json": make_json_safe(candidate),
            "published_at": posted_at,
            "content_hash": content_hash,
            "status": "fetched",
        },
    )

    content_item, _ = ContentItem.objects.update_or_create(
        raw_item=raw_item,
        defaults={
            "source": source,
            "content_type": ContentItem.ContentType.JOB_POST,
            "primary_topic": ContentItem.NewsTopic.JOBS_EMPLOYMENT,
            "secondary_topics": [],
            "title_en": title,
            "body_en": description,
            "url": url,
            "published_at": posted_at,
            "metrics": {
                "district": district,
                "salary_text": salary["salary_text"],
                "salary_min": salary["salary_min"],
                "salary_max": salary["salary_max"],
                "category": category,
                "deadline": deadline.isoformat() if deadline else "",
                "link_validated": link_is_valid,
                "link_status": link_status,
                "job_quality": "validated" if link_is_valid else "unchecked",
                "recruiting_body": recruiting_body,
                "qualification_level": qualification_level,
            },
        },
    )

    job, created = JobListing.objects.update_or_create(
        content_item=content_item,
        defaults={
            "company": company,
            "role": title,

            "recruiting_body": recruiting_body,
            "qualification_level": qualification_level,
            "qualification_text": "",

            "location": district or "Tamil Nadu",
            "district": district or "Tamil Nadu",
            "state": "Tamil Nadu",

            "salary_text": salary["salary_text"],
            "salary_min": salary["salary_min"],
            "salary_max": salary["salary_max"],
            "currency": "INR",
            "pay_period": JobListing.PayPeriod.UNKNOWN,

            "job_type": job_type,
            "work_mode": JobListing.WorkMode.UNKNOWN,

            "experience": "",
            "education": "",
            "skills": [],
            "category": category,

            "apply_url": url,

            "link_status": link_status,
            "last_validated_at": timezone.now() if validate_links else None,

            "posted_at": posted_at,
            "deadline": deadline,
            "is_active": True,
        },
    )

    return job, created


def deactivate_bad_existing_jobs():
    bad_query = Q()

    for phrase in BAD_TITLE_PHRASES:
        bad_query |= Q(role__icontains=phrase)

    if not bad_query:
        return 0

    bad_jobs = JobListing.objects.filter(bad_query)
    bad_count = bad_jobs.count()
    bad_jobs.update(is_active=False)

    return bad_count


class Command(BaseCommand):
    help = "Sync readable, validated Tamil Nadu jobs from public job/recruitment sources."

    def add_arguments(self, parser):
        parser.add_argument("--limit-per-source", dest="limit_per_source", type=int, default=50)
        parser.add_argument("--source", dest="source", type=str, default="")
        parser.add_argument("--deactivate-old-days", dest="deactivate_old_days", type=int, default=180)
        parser.add_argument("--validate-links", action="store_true")

    def handle(self, *args, **options):
        limit_per_source = options["limit_per_source"]
        source_name = options["source"].strip()
        deactivate_old_days = options["deactivate_old_days"]
        validate_links = options["validate_links"]

        sources = Source.objects.filter(
            source_type=Source.SourceType.JOBS,
            is_active=True,
        ).order_by("name")

        if source_name:
            sources = sources.filter(name__icontains=source_name)

        if not sources.exists():
            self.stdout.write(self.style.WARNING(
                "No active job sources found. Run: python manage.py seed_job_sources"
            ))
            return

        total_created = 0
        total_updated = 0
        total_seen = 0
        total_skipped = 0

        bad_existing_count = deactivate_bad_existing_jobs()

        for source in sources:
            if not source.url:
                continue

            self.stdout.write(self.style.WARNING(f"Syncing: {source.name}"))

            try:
                html = fetch_html(source.url, timeout=60)
                candidates = extract_candidates_for_source(source, html)
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"Failed: {source.name} - {exc}"))
                continue

            candidates = candidates[:limit_per_source]

            self.stdout.write(f"Readable candidates found: {len(candidates)}")

            source_created = 0
            source_updated = 0
            source_skipped = 0

            for candidate in candidates:
                job, created = upsert_job(
                    source,
                    candidate,
                    validate_links=validate_links,
                )

                if not job:
                    source_skipped += 1
                    total_skipped += 1
                    continue

                total_seen += 1

                if created:
                    source_created += 1
                    total_created += 1
                else:
                    source_updated += 1
                    total_updated += 1

            self.stdout.write(self.style.SUCCESS(
                f"{source.name}: created {source_created}, updated {source_updated}, skipped {source_skipped}"
            ))

        cutoff = timezone.now() - timedelta(days=deactivate_old_days)

        old_jobs = JobListing.objects.filter(
            is_active=True,
            posted_at__lt=cutoff,
            deadline__isnull=True,
        )

        old_count = old_jobs.count()
        old_jobs.update(is_active=False)

        expired_jobs = JobListing.objects.filter(
            is_active=True,
            deadline__isnull=False,
            deadline__lt=date.today(),
        )

        expired_count = expired_jobs.count()
        expired_jobs.update(is_active=False)

        self.stdout.write(self.style.SUCCESS(
            f"Done. Seen: {total_seen}. Created: {total_created}. "
            f"Updated: {total_updated}. Skipped: {total_skipped}. "
            f"Bad existing deactivated: {bad_existing_count}. "
            f"Old deactivated: {old_count}. Expired: {expired_count}."
        ))