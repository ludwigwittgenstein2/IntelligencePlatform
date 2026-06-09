"""
Crawl recent Tamil Nadu jobs from the National Career Service (NCS) JSON API.

Why this exists: the NCS website is a JavaScript app, so the HTML scraper in
sync_public_jobs can't read it. But the page loads its jobs from a public JSON
endpoint (no auth), which we call directly here. This returns thousands of live
postings; we keep only the ones actually located in Tamil Nadu and map them onto
JobListing so the existing /jobs/ page displays them unchanged.

Endpoint (confirmed working from a normal machine):
    POST https://betacloud.ncs.gov.in/api/v1/job-posts/search?page=N&size=50
    body: {"sortBy": "RELEVANCE", "jobLocations": "Tamil Nadu"}

NOTE: the endpoint screens out non-browser clients, so it may return HTTP 403
from a bare server/cron environment. It works from a real desktop (residential
IP + browser-like headers). If you later move this to a server and hit 403,
you'll need to supply the exact browser headers/cookies from DevTools.
"""

import hashlib
from datetime import date, datetime

import requests

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from aggregator.classifiers import classify_recruiting_body, classify_qualification
from aggregator.models import ContentItem, JobListing, RawItem, Source


API_URL = "https://betacloud.ncs.gov.in/api/v1/job-posts/search"

# NCS doesn't expose a clean per-job public detail URL we can rely on, so the
# apply link points at the TN job-listing page (always valid). If you find the
# real detail-page pattern via DevTools (click a job, watch the URL), swap it in
# here using {job_id}.
APPLY_URL_TEMPLATE = "https://www.ncs.gov.in/"
LISTING_URL = "https://betacloud.ncs.gov.in/job-listing?jobLocations=Tamil%20Nadu"

REQUEST_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Origin": "https://betacloud.ncs.gov.in",
    "Referer": LISTING_URL,
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/148.0.0.0 Safari/537.36"
    ),
}

TN_DISTRICTS = {
    "ariyalur", "chengalpattu", "chennai", "coimbatore", "cuddalore",
    "dharmapuri", "dindigul", "erode", "kallakurichi", "kanchipuram",
    "kanniyakumari", "kanyakumari", "karur", "krishnagiri", "madurai",
    "mayiladuthurai", "nagapattinam", "namakkal", "nilgiris", "perambalur",
    "pudukkottai", "ramanathapuram", "ranipet", "salem", "sivaganga",
    "tenkasi", "thanjavur", "theni", "thoothukudi", "tuticorin",
    "tiruchirappalli", "trichy", "tirunelveli", "tirupathur", "tiruppur",
    "tirupur", "tiruvallur", "tiruvannamalai", "tiruvarur", "vellore",
    "viluppuram", "villupuram", "virudhunagar",
}

# NCS jobType -> your JobListing.JobType
JOB_TYPE_MAP = {
    "FULL_TIME": JobListing.JobType.FULL_TIME,
    "PART_TIME": JobListing.JobType.PART_TIME,
    "CONTRACT": JobListing.JobType.CONTRACT,
    "INTERNSHIP": JobListing.JobType.INTERNSHIP,
    "APPRENTICESHIP": JobListing.JobType.APPRENTICESHIP,
}


def make_hash(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:64]


def to_int(value):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def parse_iso(value):
    """Parse an ISO timestamp into an aware datetime, or None."""
    if not value:
        return None
    dt = parse_datetime(value)
    if dt is None:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_default_timezone())
    return dt


def tn_location(job):
    """
    Return the matched Tamil Nadu district/city if this job is located in TN,
    else None. A job counts as TN if any of its jobLocations has state ==
    'Tamil Nadu' or a city matching a known TN district.
    """
    for loc in (job.get("jobLocations") or []):
        state = (loc.get("state") or "").strip().lower()
        city = (loc.get("city") or "").strip().lower()
        if state == "tamil nadu":
            return loc.get("city") or "Tamil Nadu"
        if city in TN_DISTRICTS:
            return loc.get("city")
    return None


def build_salary_text(job):
    if job.get("hideSalaryRange"):
        return ""
    lo = to_int(job.get("minSalary"))
    hi = to_int(job.get("maxSalary"))
    if lo and hi:
        return f"{lo:,} - {hi:,} / year"
    if lo:
        return f"{lo:,} / year"
    return ""


def build_experience_text(job):
    lo = job.get("minExperience")
    hi = job.get("maxExperience")
    if lo is None and hi is None:
        return ""
    return f"{lo or 0}-{hi or 0} yrs"


def build_education_text(job):
    prefs = job.get("educationPreferences") or []
    if prefs:
        return (prefs[0].get("educationType") or "").strip()
    return ""


class Command(BaseCommand):
    help = "Crawl recent Tamil Nadu jobs from the NCS public JSON API."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit", type=int, default=200,
            help="max number of jobs to FETCH/scan from the API (not kept)",
        )
        parser.add_argument(
            "--page-size", type=int, default=50,
            help="results per API page (max 50)",
        )
        parser.add_argument(
            "--max-pages", type=int, default=20,
            help="safety cap on how many pages to walk",
        )
        parser.add_argument(
            "--loose", action="store_true",
            help="also keep all-India / empty-location jobs (more volume, less TN-specific)",
        )
        parser.add_argument(
            "--include-expired", action="store_true",
            help="keep jobs whose expiry date has already passed",
        )

    def _get_source(self):
        source, _ = Source.objects.get_or_create(
            name="National Career Service - Tamil Nadu Jobs",
            defaults={
                "source_type": Source.SourceType.JOBS,
                "crawl_method": Source.CrawlMethod.JOB_API,
                "url": LISTING_URL,
                "language": "en",
                "is_active": True,
            },
        )
        return source

    def _fetch_page(self, page, size):
        body = {"sortBy": "RELEVANCE", "jobLocations": "Tamil Nadu"}
        resp = requests.post(
            API_URL,
            params={"page": page, "size": size},
            json=body,
            headers=REQUEST_HEADERS,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def _upsert(self, source, job, district):
        job_id = job.get("id")
        external_id = f"ncs|{job_id}"

        title = (job.get("jobTitle") or "").strip()[:255]
        description = (job.get("jobDescription") or "").strip()
        company = (job.get("organizationName") or "").strip() or "NCS Employer"
        url = APPLY_URL_TEMPLATE.format(job_id=job_id) if "{job_id}" in APPLY_URL_TEMPLATE else LISTING_URL

        combined = f"{title} {description} {job.get('functionalArea', '')}"

        posted_at = parse_iso(job.get("publishedAt")) or timezone.now()
        expired = parse_iso(job.get("expiredAt"))
        deadline = expired.date() if expired else None

        salary_text = build_salary_text(job)
        salary_min = to_int(job.get("minSalary"))
        salary_max = to_int(job.get("maxSalary"))

        ncs_type = (job.get("jobType") or "").strip().upper()
        job_type = JOB_TYPE_MAP.get(ncs_type, JobListing.JobType.UNKNOWN)
        if job.get("isGovernmentJob"):
            job_type = JobListing.JobType.GOVERNMENT

        recruiting_body = classify_recruiting_body(source.name, combined)
        qualification_level = classify_qualification(combined)

        skills = [s for s in (job.get("requiredSkills") or []) if s]
        district = district or "Tamil Nadu"

        content_hash = make_hash(combined)

        raw_item, _ = RawItem.objects.update_or_create(
            source=source,
            external_id=external_id,
            defaults={
                "url": url,
                "title": title,
                "description": description,
                "raw_text": description,
                "raw_html": "",
                "raw_json": job,             # NCS JSON is already JSON-safe
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
                    "salary_text": salary_text,
                    "salary_min": salary_min,
                    "salary_max": salary_max,
                    "category": job.get("functionalArea") or "",
                    "deadline": deadline.isoformat() if deadline else "",
                    "link_status": JobListing.LinkStatus.UNCHECKED,
                    "recruiting_body": recruiting_body,
                    "qualification_level": qualification_level,
                    "ncs_job_id": job_id,
                    "vacancies": job.get("noOfVacancies"),
                },
            },
        )

        job_obj, created = JobListing.objects.update_or_create(
            content_item=content_item,
            defaults={
                "company": company,
                "role": title,

                "recruiting_body": recruiting_body,
                "qualification_level": qualification_level,
                "qualification_text": build_education_text(job),

                "location": district,
                "district": district,
                "state": "Tamil Nadu",

                "salary_text": salary_text,
                "salary_min": salary_min,
                "salary_max": salary_max,
                "currency": "INR",
                "pay_period": JobListing.PayPeriod.YEARLY if salary_text else JobListing.PayPeriod.UNKNOWN,

                "job_type": job_type,
                "work_mode": JobListing.WorkMode.UNKNOWN,

                "experience": build_experience_text(job),
                "education": build_education_text(job),
                "skills": skills,
                "category": job.get("functionalArea") or "",

                "apply_url": url,

                "link_status": JobListing.LinkStatus.UNCHECKED,
                "last_validated_at": None,

                "posted_at": posted_at,
                "deadline": deadline,
                "is_active": True,
            },
        )

        return created

    def handle(self, *args, **opts):
        limit = opts["limit"]
        page_size = min(opts["page_size"], 50)
        max_pages = opts["max_pages"]
        loose = opts["loose"]
        include_expired = opts["include_expired"]

        source = self._get_source()
        today = date.today()

        fetched = 0
        kept = 0
        created = 0
        updated = 0
        dropped_location = 0
        dropped_expired = 0

        page = 0
        while page < max_pages and fetched < limit:
            try:
                payload = self._fetch_page(page, page_size)
            except Exception as exc:
                self.stderr.write(self.style.ERROR(
                    f"API request failed on page {page}: {exc}\n"
                    f"(If this is HTTP 403, the endpoint is blocking this machine "
                    f"-- it works from a normal browser/desktop session.)"
                ))
                break

            data = payload.get("data") or {}
            content = data.get("content") or []
            if not content:
                break

            for job in content:
                fetched += 1

                district = tn_location(job)
                if district is None:
                    # not located in TN
                    if not loose:
                        dropped_location += 1
                        continue
                    district = "Tamil Nadu"

                expired = parse_iso(job.get("expiredAt"))
                if expired and expired.date() < today and not include_expired:
                    dropped_expired += 1
                    continue

                was_created = self._upsert(source, job, district)
                kept += 1
                if was_created:
                    created += 1
                else:
                    updated += 1

            self.stdout.write(
                f"page {page}: scanned {len(content)} "
                f"(kept so far: {kept})"
            )

            if data.get("last"):
                break
            page += 1

        self.stdout.write(self.style.SUCCESS(
            f"\nDone. Fetched/scanned: {fetched}. Kept: {kept} "
            f"(created {created}, updated {updated}). "
            f"Dropped non-TN: {dropped_location}. Dropped expired: {dropped_expired}."
        ))
        if kept == 0:
            self.stdout.write(self.style.WARNING(
                "Kept 0 jobs. Most NCS postings have no real location, so strict "
                "TN filtering drops them. Try --loose to include all-India jobs, "
                "or raise --limit / --max-pages to scan deeper."
            ))