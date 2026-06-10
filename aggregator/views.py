from collections import Counter
from datetime import timedelta

from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.core.management import call_command
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from .models import (
    AlertEvent,
    AlertRule,
    ContentItem,
    DailyReport,
    JobListing,
    NLPResult,
    Source,
)


# =====================================================================
# WHAT CHANGED vs the previous views.py (only three things):
#
# 1. Job search is now done IN THE DATABASE.
#    The old code pulled up to 1000 rows into memory and filtered them in
#    Python with _job_matches_query(). That does not scale. Replaced with
#    _job_search_q(), which builds a single DB query (and still matches
#    choice labels like "Police" -> recruiting_body="tnusrb").
#
# 2. Crawls / report builds can no longer be triggered by anonymous GETs.
#    /jobs/?sync=1, /reports/?generate=1, /reports/?force=1, and the
#    auto-bootstrap sync now only run for logged-in STAFF users. A random
#    visitor or a crawler hitting those URLs no longer kicks off the
#    pipeline. As the operator you are staff, so your buttons still work.
#    For unattended updates, run the management commands from cron:
#        python manage.py sync_public_jobs --limit_per_source 50
#        python manage.py build_daily_report --period daily --top 20
#
# 3. Alert creation is hardened.
#    New rules are saved as is_verified=False and capture phone + the
#    logged-in user. Email/WhatsApp delivery stays blocked until the
#    contact is verified, which closes the "register anyone's address"
#    abuse vector. (The verification flow itself is a later step.)
# =====================================================================


PERIOD_CONFIG = {
    "daily": {
        "label_en": "Daily",
        "label_ta": "தினசரி",
        "hours": 24,
    },
    "weekly": {
        "label_en": "Weekly",
        "label_ta": "வாராந்திர",
        "hours": 24 * 7,
    },
    "monthly": {
        "label_en": "Monthly",
        "label_ta": "மாதாந்திர",
        "hours": 24 * 30,
    },
    "annual": {
        "label_en": "Annual",
        "label_ta": "வருடாந்திர",
        "hours": 24 * 365,
    },
}


def _is_staff(request):
    """True only for authenticated staff users. Gatekeeper for any action
    that triggers a crawl or a report build."""
    user = getattr(request, "user", None)
    return bool(user and user.is_authenticated and user.is_staff)


def _safe_int(value, default=50, max_value=200):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default

    return min(max(parsed, 1), max_value)


def _safe_nlp(item):
    try:
        return item.nlp
    except ObjectDoesNotExist:
        return None


def _serialize_item(item):
    nlp = _safe_nlp(item)

    return {
        "id": item.id,
        "source": item.source.name,
        "source_type": item.source.source_type,
        "content_type": item.content_type,

        "primary_topic": item.primary_topic,
        "primary_topic_display": item.get_primary_topic_display(),
        "secondary_topics": item.secondary_topics or [],

        "title_ta": item.title_ta,
        "title_en": item.title_en,
        "body_ta": item.body_ta,
        "body_en": item.body_en,

        "url": item.url,
        "published_at": item.published_at.isoformat() if item.published_at else None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "metrics": item.metrics or {},

        "summary_ta": nlp.summary_ta if nlp else "",
        "summary_en": nlp.summary_en if nlp else "",

        "topics": nlp.topics if nlp else [],
        "people": nlp.people if nlp else [],
        "parties": nlp.parties if nlp else [],
        "districts": nlp.districts if nlp else [],

        "sentiment": nlp.sentiment if nlp else "",
        "emotion": nlp.emotion if nlp else "",
        "intensity_score": nlp.intensity_score if nlp else 0,
        "news_relevance_score": nlp.news_relevance_score if nlp else 0,
        "political_relevance_score": nlp.political_relevance_score if nlp else 0,
    }


def _serialize_job(job):
    item = job.content_item

    return {
        "id": job.id,
        "content_item_id": item.id,

        "source": item.source.name,
        "source_type": item.source.source_type,

        "title_en": item.title_en,
        "title_ta": item.title_ta,

        "company": job.company,
        "role": job.role,

        "recruiting_body": job.recruiting_body,
        "recruiting_body_display": job.get_recruiting_body_display(),

        "qualification_level": job.qualification_level,
        "qualification_level_display": job.get_qualification_level_display(),
        "qualification_text": job.qualification_text,

        "location": job.location,
        "district": job.district,
        "state": job.state,

        "salary_text": job.salary_text,
        "salary_min": job.salary_min,
        "salary_max": job.salary_max,
        "currency": job.currency,
        "pay_period": job.pay_period,
        "pay_period_display": job.get_pay_period_display(),

        "job_type": job.job_type,
        "job_type_display": job.get_job_type_display(),

        "work_mode": job.work_mode,
        "work_mode_display": job.get_work_mode_display(),

        "experience": job.experience,
        "education": job.education,
        "skills": job.skills,
        "category": job.category,

        "apply_url": job.apply_url or item.url,

        "link_status": job.link_status,
        "link_status_display": job.get_link_status_display(),
        "last_validated_at": job.last_validated_at.isoformat() if job.last_validated_at else None,

        "posted_at": job.posted_at.isoformat() if job.posted_at else None,
        "deadline": job.deadline.isoformat() if job.deadline else None,

        "description_en": item.body_en,
        "description_ta": item.body_ta,
    }


def _serialize_alert_event(event):
    item = event.content_item

    return {
        "id": event.id,
        "rule_id": event.rule_id,
        "rule_name": event.rule.name,
        "status": event.status,
        "matched_keywords": event.matched_keywords or [],
        "snippet": event.snippet,
        "matched_at": event.matched_at.isoformat() if event.matched_at else None,
        "notified_at": event.notified_at.isoformat() if event.notified_at else None,
        "read_at": event.read_at.isoformat() if event.read_at else None,
        "item": _serialize_item(item),
    }


def _recent_items_queryset():
    return (
        ContentItem.objects
        .select_related("source", "nlp")
        .order_by("-published_at", "-created_at")
    )


def _items_since(hours):
    since = timezone.now() - timedelta(hours=hours)

    return (
        ContentItem.objects
        .select_related("source", "nlp")
        .filter(
            Q(published_at__gte=since)
            | Q(published_at__isnull=True, created_at__gte=since)
        )
        .order_by("-published_at", "-created_at")
    )


def _nlp_since(hours):
    since = timezone.now() - timedelta(hours=hours)

    return (
        NLPResult.objects
        .select_related("content_item", "content_item__source")
        .filter(
            Q(content_item__published_at__gte=since)
            | Q(
                content_item__published_at__isnull=True,
                content_item__created_at__gte=since,
            )
        )
    )


def _count_source_types(items):
    counts = Counter()

    for item in items:
        counts.update([item.source.source_type])

    return {
        "news_site_count": counts.get("news_site", 0),
        "youtube_count": counts.get("youtube", 0),
        "x_count": counts.get("x", 0),
        "jobs_item_count": counts.get("jobs", 0),

        "government_count": counts.get("government", 0),
        "assembly_count": counts.get("assembly", 0),
        "party_count": counts.get("party", 0),
        "commentary_count": counts.get("commentary", 0),
    }


def _topic_display_map():
    return dict(ContentItem.NewsTopic.choices)


def _build_counter_context(hours=24):
    nlp_items = _nlp_since(hours)

    topic_counter = Counter()
    primary_topic_counter = Counter()
    party_counter = Counter()
    people_counter = Counter()
    district_counter = Counter()
    source_counter = Counter()
    source_type_counter = Counter()
    sentiment_counter = Counter()
    emotion_counter = Counter()

    topic_labels = _topic_display_map()

    for nlp in nlp_items:
        item = nlp.content_item

        topic_counter.update(nlp.topics or [])

        if item.primary_topic:
            primary_topic_counter.update([
                topic_labels.get(item.primary_topic, item.primary_topic)
            ])

        party_counter.update(nlp.parties or [])
        people_counter.update(nlp.people or [])
        district_counter.update(nlp.districts or [])

        if item.source:
            source_counter.update([item.source.name])
            source_type_counter.update([item.source.source_type])

        if nlp.sentiment:
            sentiment_counter.update([nlp.sentiment])

        if nlp.emotion:
            emotion_counter.update([nlp.emotion])

    return {
        "topic_counts": topic_counter.most_common(12),
        "primary_topic_counts": primary_topic_counter.most_common(12),
        "party_counts": party_counter.most_common(12),
        "people_counts": people_counter.most_common(12),
        "district_counts": district_counter.most_common(12),
        "source_counts": source_counter.most_common(12),
        "source_type_counts": source_type_counter.most_common(12),
        "sentiment_counts": sentiment_counter.most_common(10),
        "emotion_counts": emotion_counter.most_common(10),
    }


def _auto_sync_jobs_if_needed(force=False):
    """
    Sync jobs from public sources when:
    - a staff user opens /jobs/?sync=1
    - there are no active jobs
    - latest active job update is older than 12 hours

    NOTE: callers gate this behind _is_staff(request). Anonymous visitors
    never reach it, so a public GET cannot trigger a crawl.
    """

    lock_key = "job_sync_running"

    latest_job = (
        JobListing.objects
        .filter(is_active=True)
        .order_by("-updated_at")
        .first()
    )

    active_jobs_count = JobListing.objects.filter(is_active=True).count()
    stale_cutoff = timezone.now() - timedelta(hours=12)

    latest_job_is_stale = (
        latest_job is None
        or latest_job.updated_at is None
        or latest_job.updated_at < stale_cutoff
    )

    should_sync = force or active_jobs_count == 0 or latest_job_is_stale

    if not should_sync:
        return {
            "sync_ran": False,
            "sync_error": "",
            "sync_reason": "fresh",
        }

    if cache.get(lock_key):
        return {
            "sync_ran": False,
            "sync_error": "",
            "sync_reason": "already_running",
        }

    cache.set(lock_key, True, timeout=10 * 60)

    try:
        # Pass the option in its CLI string form ("--limit-per-source") so it
        # always matches the command's actual signature regardless of how the
        # argument's dest is configured. Passing limit_per_source=50 as a kwarg
        # can fail with "unrecognized arguments" on some argparse setups.
        call_command(
            "sync_public_jobs",
            "--limit-per-source", "50",
            verbosity=0,
        )

        return {
            "sync_ran": True,
            "sync_error": "",
            "sync_reason": "forced" if force else "stale_or_empty",
        }

    except Exception as exc:
        return {
            "sync_ran": False,
            "sync_error": str(exc),
            "sync_reason": "failed",
        }

    finally:
        cache.delete(lock_key)


def _values_matching(query, choices):
    """Return the stored values of a choices field whose value OR human label
    contains the query — lets a DB search match 'Police' to 'tnusrb', etc."""
    q = query.lower()
    return [
        value
        for value, label in choices
        if q in str(value).lower() or q in str(label).lower()
    ]


def _job_search_q(query):
    """Build a single DB Q() for a free-text job search. Replaces the old
    in-memory _job_matches_query that pulled 1000 rows first."""
    if not query:
        return Q()

    q = query

    condition = (
        Q(role__icontains=q)
        | Q(company__icontains=q)
        | Q(qualification_text__icontains=q)
        | Q(location__icontains=q)
        | Q(district__icontains=q)
        | Q(state__icontains=q)
        | Q(salary_text__icontains=q)
        | Q(experience__icontains=q)
        | Q(education__icontains=q)
        | Q(category__icontains=q)
        | Q(content_item__title_en__icontains=q)
        | Q(content_item__title_ta__icontains=q)
        | Q(content_item__body_en__icontains=q)
        | Q(content_item__body_ta__icontains=q)
    )

    # Match choice labels/values too (e.g. typing a recruiting body name).
    body_values = _values_matching(q, JobListing.RecruitingBody.choices)
    if body_values:
        condition |= Q(recruiting_body__in=body_values)

    qual_values = _values_matching(q, JobListing.QualificationLevel.choices)
    if qual_values:
        condition |= Q(qualification_level__in=qual_values)

    type_values = _values_matching(q, JobListing.JobType.choices)
    if type_values:
        condition |= Q(job_type__in=type_values)

    mode_values = _values_matching(q, JobListing.WorkMode.choices)
    if mode_values:
        condition |= Q(work_mode__in=mode_values)

    period_values = _values_matching(q, JobListing.PayPeriod.choices)
    if period_values:
        condition |= Q(pay_period__in=period_values)

    link_values = _values_matching(q, JobListing.LinkStatus.choices)
    if link_values:
        condition |= Q(link_status__in=link_values)

    return condition


def _job_counter_context(jobs_list):
    district_counter = Counter()
    category_counter = Counter()
    company_counter = Counter()
    recruiting_body_counter = Counter()
    qualification_counter = Counter()
    link_status_counter = Counter()
    job_type_counter = Counter()

    salary_known_count = 0

    for job in jobs_list:
        if job.district:
            district_counter.update([job.district])

        if job.category:
            category_counter.update([job.category])

        if job.company:
            company_counter.update([job.company])

        if job.recruiting_body:
            recruiting_body_counter.update([job.get_recruiting_body_display()])

        if job.qualification_level:
            qualification_counter.update([job.get_qualification_level_display()])

        if job.link_status:
            link_status_counter.update([job.get_link_status_display()])

        if job.job_type:
            job_type_counter.update([job.get_job_type_display()])

        if job.salary_text or job.salary_min or job.salary_max:
            salary_known_count += 1

    return {
        "salary_known_count": salary_known_count,
        "district_counts": district_counter.most_common(20),
        "category_counts": category_counter.most_common(20),
        "company_counts": company_counter.most_common(20),
        "recruiting_body_counts": recruiting_body_counter.most_common(20),
        "qualification_counts": qualification_counter.most_common(20),
        "link_status_counts": link_status_counter.most_common(20),
        "job_type_counts": job_type_counter.most_common(20),
    }


def _news_source_type_choices():
    excluded = {Source.SourceType.JOBS}

    return [
        (value, label)
        for value, label in Source.SourceType.choices
        if value not in excluded
    ]


# ---------------------------------------------------------------------
# REPORT HELPERS
# ---------------------------------------------------------------------

def _latest_report_for_period(period):
    if period not in PERIOD_CONFIG:
        period = "daily"

    return (
        DailyReport.objects
        .filter(period=period)
        .order_by("-report_date", "-updated_at")
        .first()
    )


def _build_report_for_period(period, top=20, force=False):
    if period not in PERIOD_CONFIG:
        period = "daily"

    lock_key = f"report_build_running_{period}"

    if cache.get(lock_key):
        return {
            "built": False,
            "error": "",
            "reason": "already_running",
        }

    latest_report = _latest_report_for_period(period)

    if latest_report and not force:
        return {
            "built": False,
            "error": "",
            "reason": "already_exists",
        }

    cache.set(lock_key, True, timeout=10 * 60)

    try:
        call_command(
            "build_daily_report",
            period=period,
            top=top,
            verbosity=0,
        )

        return {
            "built": True,
            "error": "",
            "reason": "built",
        }

    except Exception as exc:
        return {
            "built": False,
            "error": str(exc),
            "reason": "failed",
        }

    finally:
        cache.delete(lock_key)


def _get_report_with_optional_build(request, period):
    """
    Behavior:
    - Anyone: see the latest existing report.
    - STAFF only: ?generate=1 / ?force=1 rebuild, and a missing report is
      built once on demand. Anonymous users never trigger a build — they
      just see the latest report or the empty state.
    """

    if period not in PERIOD_CONFIG:
        period = "daily"

    is_staff = _is_staff(request)

    force_build = (request.GET.get("force") == "1") and is_staff
    generate = (request.GET.get("generate") == "1") and is_staff

    latest_report = _latest_report_for_period(period)

    should_build = is_staff and (force_build or generate or latest_report is None)

    build_status = {
        "built": False,
        "error": "",
        "reason": "not_requested",
    }

    if should_build:
        build_status = _build_report_for_period(
            period=period,
            top=20,
            force=force_build or generate,
        )

        latest_report = _latest_report_for_period(period)

    return latest_report, build_status


# ---------------------------------------------------------------------
# PAGE VIEWS
# ---------------------------------------------------------------------

def dashboard(request):
    source_type = request.GET.get("source_type", "").strip()

    primary_topic = (
        request.GET.get("primary_topic", "").strip()
        or request.GET.get("topic", "").strip()
    )

    query = request.GET.get("q", "").strip()

    base_queryset = _recent_items_queryset()
    all_recent_items = list(base_queryset[:250])

    filtered_queryset = base_queryset.exclude(
        content_type=ContentItem.ContentType.JOB_POST
    )

    if source_type:
        filtered_queryset = filtered_queryset.filter(source__source_type=source_type)

    if primary_topic:
        filtered_queryset = filtered_queryset.filter(primary_topic=primary_topic)

    if query:
        filtered_queryset = filtered_queryset.filter(
            Q(title_ta__icontains=query)
            | Q(title_en__icontains=query)
            | Q(body_ta__icontains=query)
            | Q(body_en__icontains=query)
            | Q(nlp__summary_ta__icontains=query)
            | Q(nlp__summary_en__icontains=query)
        )

    items = list(filtered_queryset[:150])
    key_story_items = items[:5]

    sources = Source.objects.all().order_by("source_type", "name")

    latest_report = (
        DailyReport.objects
        .filter(period=DailyReport.Period.DAILY)
        .order_by("-report_date", "-updated_at")
        .first()
    )

    source_type_counts = _count_source_types(all_recent_items)
    counter_context = _build_counter_context(hours=24)

    jobs_count = JobListing.objects.filter(is_active=True).count()

    context = {
        "page_title": "NewsIQ - Tamil Nadu News Intelligence",

        "items": items,
        "key_story_items": key_story_items,
        "sources": sources,
        "latest_report": latest_report,

        "source_type": source_type,

        # Keep both names so old templates and new templates both work.
        "topic": primary_topic,
        "primary_topic": primary_topic,

        "query": query,

        "source_type_choices": _news_source_type_choices(),
        "news_topic_choices": ContentItem.NewsTopic.choices,

        "jobs_count": jobs_count,

        **source_type_counts,
        **counter_context,
    }

    return render(request, "aggregator/dashboard.html", context)


def x_wall(request):
    """
    Free X/Twitter display page.

    This does not use the paid X API.
    It embeds public X profile timelines using widgets.js.

    Profile sources with x_handle can be embedded.
    Query-only X sources cannot be embedded for free, so they are shown as links.
    """

    all_x_sources = (
        Source.objects
        .filter(
            source_type=Source.SourceType.X,
            is_active=True,
        )
        .order_by("name")
    )

    profile_sources = []
    query_sources = []

    for source in all_x_sources:
        if source.x_handle:
            profile_sources.append(source)
        else:
            query_sources.append(source)

    context = {
        "page_title": "NewsIQ - X/Twitter Commentary",
        "sources": profile_sources,
        "profile_sources": profile_sources,
        "query_sources": query_sources,
        "jobs_count": JobListing.objects.filter(is_active=True).count(),
    }

    return render(request, "aggregator/x_wall.html", context)


def jobs(request):
    # Only staff can trigger a crawl. Anonymous GETs (incl. crawlers/prefetch)
    # never run the pipeline. For unattended updates use cron + sync_public_jobs.
    if _is_staff(request):
        force_sync = request.GET.get("sync") == "1"
        sync_status = _auto_sync_jobs_if_needed(force=force_sync)
    else:
        sync_status = {"sync_ran": False, "sync_error": "", "sync_reason": "skipped"}

    query = request.GET.get("q", "").strip()
    district = request.GET.get("district", "").strip()
    category = request.GET.get("category", "").strip()
    recruiting_body = request.GET.get("recruiting_body", "").strip()
    qualification_level = request.GET.get("qualification_level", "").strip()
    link_status = request.GET.get("link_status", "").strip()
    min_salary = request.GET.get("min_salary", "").strip()

    jobs_qs = (
        JobListing.objects
        .select_related("content_item", "content_item__source")
        .filter(is_active=True)
        .order_by("-posted_at", "-created_at")
    )

    if district:
        jobs_qs = jobs_qs.filter(district__icontains=district)

    if category:
        jobs_qs = jobs_qs.filter(category__icontains=category)

    if recruiting_body:
        jobs_qs = jobs_qs.filter(recruiting_body=recruiting_body)

    if qualification_level:
        jobs_qs = jobs_qs.filter(qualification_level=qualification_level)

    if link_status:
        jobs_qs = jobs_qs.filter(link_status=link_status)

    if min_salary:
        try:
            min_salary_value = int(min_salary)
            jobs_qs = jobs_qs.filter(
                Q(salary_max__gte=min_salary_value)
                | Q(salary_min__gte=min_salary_value)
            )
        except ValueError:
            pass

    # Free-text search now runs in the DB, not in Python over 1000 rows.
    if query:
        jobs_qs = jobs_qs.filter(_job_search_q(query))

    jobs_list = list(jobs_qs[:200])

    latest_job = (
        JobListing.objects
        .filter(is_active=True)
        .order_by("-updated_at")
        .first()
    )

    context = {
        "page_title": "JobsIQ - Tamil Nadu Jobs Intelligence",

        "jobs": jobs_list,
        "jobs_count": JobListing.objects.filter(is_active=True).count(),
        "visible_jobs_count": len(jobs_list),

        "query": query,
        "district": district,
        "category": category,
        "recruiting_body": recruiting_body,
        "qualification_level": qualification_level,
        "link_status": link_status,
        "min_salary": min_salary,

        "job_recruiting_body_choices": JobListing.RecruitingBody.choices,
        "job_qualification_choices": JobListing.QualificationLevel.choices,
        "job_link_status_choices": JobListing.LinkStatus.choices,
        "job_type_choices": JobListing.JobType.choices,

        "sync_ran": sync_status["sync_ran"],
        "sync_error": sync_status["sync_error"],
        "sync_reason": sync_status["sync_reason"],
        "latest_job_updated_at": latest_job.updated_at if latest_job else None,

        **_job_counter_context(jobs_list),
    }

    return render(request, "aggregator/jobs.html", context)


def alerts(request):
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        keywords = request.POST.get("keywords", "").strip()
        match_mode = request.POST.get("match_mode", AlertRule.MatchMode.ANY)
        source_type = request.POST.get("source_type", "").strip()
        primary_topic = request.POST.get("primary_topic", "").strip()
        notification_channel = request.POST.get(
            "notification_channel",
            AlertRule.NotificationChannel.IN_APP,
        )
        email = request.POST.get("email", "").strip()
        phone = request.POST.get("phone", "").strip()

        try:
            minimum_relevance = float(
                request.POST.get("minimum_relevance", "0").strip() or 0
            )
        except ValueError:
            minimum_relevance = 0.0

        minimum_relevance = min(max(minimum_relevance, 0.0), 1.0)

        if name and keywords:
            AlertRule.objects.create(
                # Attach the owner when signed in; this is what a paid plan
                # will later hang off.
                user=request.user if request.user.is_authenticated else None,
                name=name,
                keywords=keywords,
                match_mode=match_mode
                if match_mode in AlertRule.MatchMode.values
                else AlertRule.MatchMode.ANY,
                source_type=source_type,
                primary_topic=primary_topic,
                minimum_relevance=minimum_relevance,
                notification_channel=notification_channel
                if notification_channel in AlertRule.NotificationChannel.values
                else AlertRule.NotificationChannel.IN_APP,
                email=email,
                phone=phone,
                # Email/WhatsApp delivery stays off until the contact is
                # verified. Prevents registering someone else's address/number.
                is_verified=False,
            )

        return redirect("alerts")

    rules = (
        AlertRule.objects
        .prefetch_related("events")
        .order_by("name")
    )

    events = (
        AlertEvent.objects
        .select_related("rule", "content_item", "content_item__source", "content_item__nlp")
        .order_by("-matched_at")[:100]
    )

    unread_count = AlertEvent.objects.filter(status=AlertEvent.Status.NEW).count()

    context = {
        "page_title": "NewsIQ Alerts & Notifications",
        "rules": rules,
        "events": events,
        "unread_count": unread_count,
        "source_type_choices": Source.SourceType.choices,
        "news_topic_choices": ContentItem.NewsTopic.choices,
        "match_mode_choices": AlertRule.MatchMode.choices,
        "notification_channel_choices": AlertRule.NotificationChannel.choices,
        "jobs_count": JobListing.objects.filter(is_active=True).count(),
    }

    return render(request, "aggregator/alerts.html", context)


def reports(request):
    period = request.GET.get("period", "daily").strip().lower()
    source_type = request.GET.get("source_type", "").strip()

    primary_topic = (
        request.GET.get("primary_topic", "").strip()
        or request.GET.get("topic", "").strip()
    )

    if period not in PERIOD_CONFIG:
        period = "daily"

    period_config = PERIOD_CONFIG[period]
    hours = period_config["hours"]

    period_queryset = _items_since(hours).exclude(
        content_type=ContentItem.ContentType.JOB_POST
    )

    if source_type:
        period_queryset = period_queryset.filter(
            source__source_type=source_type
        )

    if primary_topic:
        period_queryset = period_queryset.filter(
            primary_topic=primary_topic
        )

    period_items = list(period_queryset[:500])

    sources = Source.objects.all().order_by("source_type", "name")

    latest_report, report_build_status = _get_report_with_optional_build(
        request=request,
        period=period,
    )

    report_sections = latest_report.report_sections if latest_report else {}

    source_type_counts = _count_source_types(period_items)
    counter_context = _build_counter_context(hours=hours)

    jobs_count = JobListing.objects.filter(is_active=True).count()

    context = {
        "page_title": "NewsIQ Intelligence Report",

        "period": period,
        "period_label_en": period_config["label_en"],
        "period_label_ta": period_config["label_ta"],
        "period_hours": hours,
        "period_items_count": len(period_items),

        "items": period_items,
        "sources": sources,

        "latest_report": latest_report,
        "report_sections": report_sections,
        "report_build_status": report_build_status,

        "source_type": source_type,

        # Keep both names so old templates and new templates both work.
        "topic": primary_topic,
        "primary_topic": primary_topic,

        "source_type_choices": _news_source_type_choices(),
        "news_topic_choices": ContentItem.NewsTopic.choices,

        "jobs_count": jobs_count,

        **source_type_counts,
        **counter_context,
    }

    return render(request, "aggregator/reports.html", context)


# ---------------------------------------------------------------------
# API VIEWS
# ---------------------------------------------------------------------

def api_latest(request):
    limit = _safe_int(request.GET.get("limit"), default=50, max_value=200)

    source_type = request.GET.get("source_type", "").strip()

    primary_topic = (
        request.GET.get("primary_topic", "").strip()
        or request.GET.get("topic", "").strip()
    )

    query = request.GET.get("q", "").strip()
    include_jobs = request.GET.get("include_jobs") == "1"

    items = _recent_items_queryset()

    if not include_jobs:
        items = items.exclude(content_type=ContentItem.ContentType.JOB_POST)

    if source_type:
        items = items.filter(source__source_type=source_type)

    if primary_topic:
        items = items.filter(primary_topic=primary_topic)

    if query:
        items = items.filter(
            Q(title_ta__icontains=query)
            | Q(title_en__icontains=query)
            | Q(body_ta__icontains=query)
            | Q(body_en__icontains=query)
            | Q(nlp__summary_ta__icontains=query)
            | Q(nlp__summary_en__icontains=query)
        )

    items = list(items[:limit])

    return JsonResponse({
        "count": len(items),
        "items": [_serialize_item(item) for item in items],
    })


def api_youtube(request):
    limit = _safe_int(request.GET.get("limit"), default=50, max_value=200)

    items = list(
        ContentItem.objects
        .select_related("source", "nlp")
        .filter(source__source_type=Source.SourceType.YOUTUBE)
        .exclude(content_type=ContentItem.ContentType.JOB_POST)
        .order_by("-published_at", "-created_at")[:limit]
    )

    return JsonResponse({
        "count": len(items),
        "items": [_serialize_item(item) for item in items],
    })


def api_jobs(request):
    # Forced sync via API is staff-only too.
    if request.GET.get("sync") == "1" and _is_staff(request):
        _auto_sync_jobs_if_needed(force=True)

    limit = _safe_int(request.GET.get("limit"), default=50, max_value=200)

    query = request.GET.get("q", "").strip()
    district = request.GET.get("district", "").strip()
    category = request.GET.get("category", "").strip()
    recruiting_body = request.GET.get("recruiting_body", "").strip()
    qualification_level = request.GET.get("qualification_level", "").strip()
    link_status = request.GET.get("link_status", "").strip()
    min_salary = request.GET.get("min_salary", "").strip()

    jobs_qs = (
        JobListing.objects
        .select_related("content_item", "content_item__source")
        .filter(is_active=True)
        .order_by("-posted_at", "-created_at")
    )

    if district:
        jobs_qs = jobs_qs.filter(district__icontains=district)

    if category:
        jobs_qs = jobs_qs.filter(category__icontains=category)

    if recruiting_body:
        jobs_qs = jobs_qs.filter(recruiting_body=recruiting_body)

    if qualification_level:
        jobs_qs = jobs_qs.filter(qualification_level=qualification_level)

    if link_status:
        jobs_qs = jobs_qs.filter(link_status=link_status)

    if min_salary:
        try:
            min_salary_value = int(min_salary)
            jobs_qs = jobs_qs.filter(
                Q(salary_max__gte=min_salary_value)
                | Q(salary_min__gte=min_salary_value)
            )
        except ValueError:
            pass

    if query:
        jobs_qs = jobs_qs.filter(_job_search_q(query))

    jobs_list = list(jobs_qs[:limit])

    return JsonResponse({
        "count": len(jobs_list),
        "items": [_serialize_job(job) for job in jobs_list],
    })


def api_alerts(request):
    limit = _safe_int(request.GET.get("limit"), default=50, max_value=200)
    status = request.GET.get("status", "").strip()

    events = (
        AlertEvent.objects
        .select_related("rule", "content_item", "content_item__source", "content_item__nlp")
        .order_by("-matched_at")
    )

    if status:
        events = events.filter(status=status)

    events = list(events[:limit])

    return JsonResponse({
        "count": len(events),
        "unread_count": AlertEvent.objects.filter(status=AlertEvent.Status.NEW).count(),
        "items": [_serialize_alert_event(event) for event in events],
    })


def api_trends(request):
    hours = _safe_int(request.GET.get("hours"), default=24, max_value=8760)

    nlp_items = _nlp_since(hours)

    topics = Counter()
    primary_topics = Counter()
    parties = Counter()
    people = Counter()
    districts = Counter()
    sources = Counter()
    source_types = Counter()
    sentiment = Counter()
    emotions = Counter()

    topic_labels = _topic_display_map()

    for nlp in nlp_items:
        item = nlp.content_item

        topics.update(nlp.topics or [])

        if item.primary_topic:
            primary_topics.update([
                topic_labels.get(item.primary_topic, item.primary_topic)
            ])

        parties.update(nlp.parties or [])
        people.update(nlp.people or [])
        districts.update(nlp.districts or [])

        if item.source:
            sources.update([item.source.name])
            source_types.update([item.source.source_type])

        if nlp.sentiment:
            sentiment.update([nlp.sentiment])

        if nlp.emotion:
            emotions.update([nlp.emotion])

    return JsonResponse({
        "hours": hours,
        "primary_topics": primary_topics.most_common(25),
        "topics": topics.most_common(25),
        "parties": parties.most_common(25),
        "people": people.most_common(25),
        "districts": districts.most_common(25),
        "sources": sources.most_common(25),
        "source_types": source_types.most_common(25),
        "sentiment": sentiment.most_common(10),
        "emotions": emotions.most_common(10),
    })


def api_daily_report(request):
    """
    API for daily/weekly/monthly/annual reports.

    Existing URL still works:
        /api/daily-report/

    New period options:
        /api/daily-report/?period=daily
        /api/daily-report/?period=weekly
        /api/daily-report/?period=monthly
        /api/daily-report/?period=annual

    Optional generation (STAFF only):
        /api/daily-report/?period=weekly&generate=1
        /api/daily-report/?period=weekly&force=1
    """

    period = request.GET.get("period", "daily").strip().lower()

    if period not in PERIOD_CONFIG:
        period = "daily"

    latest_report, report_build_status = _get_report_with_optional_build(
        request=request,
        period=period,
    )

    if not latest_report:
        return JsonResponse({
            "ok": False,
            "period": period,
            "report": None,
            "build_status": report_build_status,
        })

    return JsonResponse({
        "ok": True,

        "report": {
            "report_date": latest_report.report_date.isoformat(),
            "period": latest_report.period,

            "summary_ta": latest_report.summary_ta,
            "summary_en": latest_report.summary_en,

            "report_sections": latest_report.report_sections or {},

            "top_stories": latest_report.top_stories,
            "source_coverage": latest_report.source_coverage,

            "party_mentions": latest_report.party_mentions,
            "topic_mentions": latest_report.topic_mentions,
            "district_mentions": latest_report.district_mentions,

            "created_at": (
                latest_report.created_at.isoformat()
                if latest_report.created_at else None
            ),

            "updated_at": (
                latest_report.updated_at.isoformat()
                if latest_report.updated_at else None
            ),
        },

        "build_status": report_build_status,
    })


def api_report(request):
    """
    Cleaner alias for report API.

    Recommended URL:
        /api/report/?period=weekly

    This simply reuses api_daily_report so both URLs return the same structure.
    """

    return api_daily_report(request)


def api_track(request):
    query = request.GET.get("q", "").strip()
    limit = _safe_int(request.GET.get("limit"), default=50, max_value=200)

    if not query:
        return JsonResponse({
            "query": query,
            "count": 0,
            "items": [],
        })

    items = list(
        ContentItem.objects
        .select_related("source", "nlp")
        .filter(
            Q(title_ta__icontains=query)
            | Q(title_en__icontains=query)
            | Q(body_ta__icontains=query)
            | Q(body_en__icontains=query)
            | Q(nlp__summary_ta__icontains=query)
            | Q(nlp__summary_en__icontains=query)
        )
        .order_by("-published_at", "-created_at")[:limit]
    )

    serialized_items = [_serialize_item(item) for item in items]

    return JsonResponse({
        "query": query,
        "count": len(serialized_items),
        "items": serialized_items,
    })