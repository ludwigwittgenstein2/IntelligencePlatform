from django.conf import settings
from django.db import models
from django.utils import timezone


class Source(models.Model):
    class SourceType(models.TextChoices):
        # NewsIQ source streams
        NEWS_SITE = "news_site", "News Site"
        YOUTUBE = "youtube", "YouTube"
        X = "x", "X/Twitter"
        GOVERNMENT = "government", "Government Source"
        ASSEMBLY = "assembly", "Assembly Source"
        PARTY = "party", "Party / Political Organization"
        COMMENTARY = "commentary", "Commentary"

        # JobsIQ source stream
        JOBS = "jobs", "Jobs"

    class CrawlMethod(models.TextChoices):
        RSS = "rss", "RSS"
        HTML = "html", "HTML"

        YOUTUBE_API = "youtube_api", "YouTube API"
        YOUTUBE_RSS = "youtube_rss", "YouTube RSS"

        X_API = "x_api", "X API"

        JOB_RSS = "job_rss", "Job RSS"
        JOB_HTML = "job_html", "Job HTML"
        JOB_CSV = "job_csv", "Job CSV"
        JOB_API = "job_api", "Job API"

    class ExtractMode(models.TextChoices):
        # How structured items are pulled out of a source. This is ORTHOGONAL to
        # crawl_method (which is about transport). Govt boards publish PDFs behind
        # a listing page; NCS/Apprenticeship are JS apps with no usable static HTML.
        AUTO = "auto", "Auto / default"
        LISTING_HTML = "listing_html", "HTML listing page"
        LISTING_PDF = "listing_pdf", "Listing → PDF notifications"
        SPA_API = "spa_api", "JS app (needs API or headless browser)"
        FEED = "feed", "RSS / Atom feed"

    name = models.CharField(max_length=255, unique=True)
    source_type = models.CharField(max_length=50, choices=SourceType.choices)

    url = models.URLField(blank=True, max_length=1000)
    rss_url = models.URLField(blank=True, max_length=1000)

    youtube_channel_id = models.CharField(max_length=255, blank=True)

    x_handle = models.CharField(max_length=255, blank=True)
    x_query = models.TextField(blank=True)

    crawl_method = models.CharField(max_length=50, choices=CrawlMethod.choices)

    extract_mode = models.CharField(
        max_length=32,
        choices=ExtractMode.choices,
        default=ExtractMode.AUTO,
        help_text="How to extract structured items. Govt boards are listing_pdf; NCS/Apprenticeship are spa_api.",
    )

    language = models.CharField(max_length=20, default="ta")

    is_active = models.BooleanField(default=True)

    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["source_type", "name"]

    def __str__(self):
        return self.name


class RawItem(models.Model):
    source = models.ForeignKey(
        Source,
        on_delete=models.CASCADE,
        related_name="raw_items",
    )

    external_id = models.CharField(max_length=500, blank=True, db_index=True)
    url = models.URLField(blank=True, max_length=1000)

    title = models.TextField(blank=True)
    description = models.TextField(blank=True)

    raw_text = models.TextField(blank=True)
    raw_html = models.TextField(blank=True)
    raw_json = models.JSONField(default=dict, blank=True)

    published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    fetched_at = models.DateTimeField(default=timezone.now, db_index=True)

    content_hash = models.CharField(max_length=64, db_index=True)
    status = models.CharField(max_length=50, default="new", db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["source", "external_id"]),
            models.Index(fields=["content_hash"]),
            models.Index(fields=["published_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "external_id"],
                name="unique_source_external_id",
            ),
        ]

    def __str__(self):
        return self.title[:100] or self.external_id or str(self.pk)


class ContentItem(models.Model):
    class ContentType(models.TextChoices):
        ARTICLE = "article", "Article"
        YOUTUBE_VIDEO = "youtube_video", "YouTube Video"
        TWEET = "tweet", "Tweet"
        JOB_POST = "job_post", "Job Post"

    class NewsTopic(models.TextChoices):
        POLITICS = "politics", "Politics"
        GOVERNMENT_POLICY = "government_policy", "Government & Policy"
        ASSEMBLY_WATCH = "assembly_watch", "Assembly Watch"
        ECONOMY_WELFARE = "economy_welfare", "Economy & Welfare"
        EDUCATION = "education", "Education"
        HEALTH = "health", "Health"
        LAW_ORDER = "law_order", "Law & Order"
        INFRASTRUCTURE_TRANSPORT = "infrastructure_transport", "Infrastructure & Transport"
        AGRICULTURE_FARMERS = "agriculture_farmers", "Agriculture & Farmers"
        CINEMA_CULTURE = "cinema_culture", "Cinema & Culture"
        DISTRICT_LOCAL = "district_local", "District & Local Governance"
        JOBS_EMPLOYMENT = "jobs_employment", "Jobs & Employment"
        GENERAL = "general", "General"

    raw_item = models.OneToOneField(
        RawItem,
        on_delete=models.CASCADE,
        related_name="content_item",
    )

    source = models.ForeignKey(
        Source,
        on_delete=models.CASCADE,
        related_name="content_items",
    )

    content_type = models.CharField(max_length=50, choices=ContentType.choices)

    # NewsIQ primary topic spine
    primary_topic = models.CharField(
        max_length=100,
        choices=NewsTopic.choices,
        default=NewsTopic.GENERAL,
        db_index=True,
    )

    # Additional cross-cutting topics/tags
    secondary_topics = models.JSONField(default=list, blank=True)

    title_ta = models.TextField(blank=True)
    title_en = models.TextField(blank=True)

    body_ta = models.TextField(blank=True)
    body_en = models.TextField(blank=True)

    url = models.URLField(blank=True, max_length=1000)
    author = models.CharField(max_length=255, blank=True)

    published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    metrics = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["content_type", "published_at"]),
            models.Index(fields=["source", "published_at"]),
            models.Index(fields=["primary_topic", "published_at"]),
        ]
        ordering = ["-published_at", "-created_at"]

    def __str__(self):
        return self.title_en[:100] or self.title_ta[:100] or str(self.pk)


class JobListing(models.Model):
    class PayPeriod(models.TextChoices):
        MONTHLY = "monthly", "Monthly"
        YEARLY = "yearly", "Yearly"
        DAILY = "daily", "Daily"
        HOURLY = "hourly", "Hourly"
        UNKNOWN = "unknown", "Unknown"

    class WorkMode(models.TextChoices):
        ONSITE = "onsite", "Onsite"
        REMOTE = "remote", "Remote"
        HYBRID = "hybrid", "Hybrid"
        UNKNOWN = "unknown", "Unknown"

    class JobType(models.TextChoices):
        FULL_TIME = "full_time", "Full-time"
        PART_TIME = "part_time", "Part-time"
        CONTRACT = "contract", "Contract"
        INTERNSHIP = "internship", "Internship"
        APPRENTICESHIP = "apprenticeship", "Apprenticeship"
        GOVERNMENT = "government", "Government"
        PRIVATE = "private", "Private"
        UNKNOWN = "unknown", "Unknown"

    class RecruitingBody(models.TextChoices):
        TNPSC = "tnpsc", "TNPSC"
        MRB = "mrb", "Medical Recruitment Board"
        TRB = "trb", "Teachers Recruitment Board"
        TNUSRB = "tnusrb", "Police / Uniformed Services"
        TN_GOVT_DEPARTMENT = "tn_govt_department", "Tamil Nadu Government Department"
        CENTRAL_GOVT = "central_govt", "Central Government"
        PSU_BANK_RAILWAY = "psu_bank_railway", "PSU / Bank / Railway"
        APPRENTICESHIP = "apprenticeship", "Apprenticeship"
        PRIVATE_VERIFIED = "private_verified", "Verified Private Jobs"
        UNKNOWN = "unknown", "Unknown"

    class QualificationLevel(models.TextChoices):
        BELOW_10TH = "below_10th", "Below 10th"
        TENTH_PASS = "10th_pass", "10th Pass"
        TWELFTH_PASS = "12th_pass", "12th Pass"
        ITI_DIPLOMA = "iti_diploma", "ITI / Diploma"
        GRADUATE = "graduate", "Graduate"
        POSTGRADUATE = "postgraduate", "Postgraduate"
        PROFESSIONAL = "professional", "Professional Degree"
        PHD = "phd", "PhD"
        UNKNOWN = "unknown", "Unknown"

    class LinkStatus(models.TextChoices):
        UNCHECKED = "unchecked", "Unchecked"
        VALID = "valid", "Valid"
        BROKEN = "broken", "Broken"
        BLOCKED = "blocked", "Blocked"

    content_item = models.OneToOneField(
        ContentItem,
        on_delete=models.CASCADE,
        related_name="job",
    )

    company = models.CharField(max_length=255, blank=True)
    role = models.CharField(max_length=255, blank=True)

    # JobsIQ primary spine
    recruiting_body = models.CharField(
        max_length=100,
        choices=RecruitingBody.choices,
        default=RecruitingBody.UNKNOWN,
        db_index=True,
    )

    # JobsIQ important user filter
    qualification_level = models.CharField(
        max_length=100,
        choices=QualificationLevel.choices,
        default=QualificationLevel.UNKNOWN,
        db_index=True,
    )
    qualification_text = models.TextField(blank=True)

    location = models.CharField(max_length=255, blank=True)
    district = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, default="Tamil Nadu")

    salary_text = models.CharField(max_length=255, blank=True)
    salary_min = models.IntegerField(null=True, blank=True)
    salary_max = models.IntegerField(null=True, blank=True)

    currency = models.CharField(max_length=20, default="INR")
    pay_period = models.CharField(
        max_length=50,
        choices=PayPeriod.choices,
        default=PayPeriod.UNKNOWN,
    )

    job_type = models.CharField(
        max_length=50,
        choices=JobType.choices,
        default=JobType.UNKNOWN,
    )

    work_mode = models.CharField(
        max_length=50,
        choices=WorkMode.choices,
        default=WorkMode.UNKNOWN,
    )

    experience = models.CharField(max_length=255, blank=True)
    education = models.CharField(max_length=255, blank=True)

    skills = models.JSONField(default=list, blank=True)

    # Sector/family label, not the primary spine
    category = models.CharField(
        max_length=100,
        blank=True,
        help_text="Sector/family: IT, healthcare, teaching, manufacturing, government, sales, etc.",
    )

    apply_url = models.URLField(blank=True, max_length=1000)

    link_status = models.CharField(
        max_length=50,
        choices=LinkStatus.choices,
        default=LinkStatus.UNCHECKED,
        db_index=True,
    )

    last_validated_at = models.DateTimeField(null=True, blank=True)

    posted_at = models.DateTimeField(null=True, blank=True)
    deadline = models.DateField(null=True, blank=True)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["recruiting_body", "posted_at"]),
            models.Index(fields=["qualification_level", "posted_at"]),
            models.Index(fields=["district", "posted_at"]),
            models.Index(fields=["category", "posted_at"]),
            models.Index(fields=["salary_min", "salary_max"]),
            models.Index(fields=["is_active", "posted_at"]),
            models.Index(fields=["deadline"]),
            models.Index(fields=["link_status"]),
        ]
        ordering = ["-posted_at", "-created_at"]

    def __str__(self):
        role = self.role or self.content_item.title_en or self.content_item.title_ta
        company = self.company or "Unknown company"
        return f"{role} - {company}"


class NLPResult(models.Model):
    content_item = models.OneToOneField(
        ContentItem,
        on_delete=models.CASCADE,
        related_name="nlp",
    )

    summary_ta = models.TextField(blank=True)
    summary_en = models.TextField(blank=True)

    topics = models.JSONField(default=list, blank=True)
    entities = models.JSONField(default=dict, blank=True)

    people = models.JSONField(default=list, blank=True)
    parties = models.JSONField(default=list, blank=True)
    districts = models.JSONField(default=list, blank=True)

    sentiment = models.CharField(max_length=50, blank=True)
    emotion = models.CharField(max_length=50, blank=True)

    intensity_score = models.FloatField(default=0.0)
    political_relevance_score = models.FloatField(default=0.0)
    news_relevance_score = models.FloatField(default=0.0)

    stance_notes = models.TextField(blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"NLP for {self.content_item_id}"


class DailyReport(models.Model):
    # NOTE: this model now stores reports for ANY period (daily/weekly/monthly/
    # annual), not just daily. The name is kept as DailyReport to avoid a larger
    # rename/migration; the `period` field is what distinguishes them.
    class Period(models.TextChoices):
        DAILY = "daily", "Daily"
        WEEKLY = "weekly", "Weekly"
        MONTHLY = "monthly", "Monthly"
        ANNUAL = "annual", "Annual"

    report_date = models.DateField()
    period = models.CharField(
        max_length=20,
        choices=Period.choices,
        default=Period.DAILY,
        db_index=True,
    )

    summary_ta = models.TextField(blank=True)
    summary_en = models.TextField(blank=True)

    top_stories = models.JSONField(default=list, blank=True)
    source_coverage = models.JSONField(default=dict, blank=True)

    party_mentions = models.JSONField(default=dict, blank=True)
    topic_mentions = models.JSONField(default=dict, blank=True)
    district_mentions = models.JSONField(default=dict, blank=True)

    # New readable NewsIQ report structure
    report_sections = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-report_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["report_date", "period"],
                name="unique_report_date_period",
            ),
        ]

    def __str__(self):
        return f"{self.get_period_display()} Report {self.report_date}"


class ChannelDigest(models.Model):
    """One rolled-up digest per YouTube channel, built from its recent video
    transcripts. Channel-level grain, complementing per-video NLPResult."""

    source = models.OneToOneField(
        Source,
        on_delete=models.CASCADE,
        related_name="digest",
    )

    summary_en = models.TextField(blank=True, default="")
    summary_ta = models.TextField(blank=True, default="")

    main_topics = models.JSONField(default=list, blank=True)
    key_issues = models.JSONField(default=list, blank=True)

    stance = models.CharField(max_length=32, blank=True, default="")
    stance_detail = models.TextField(blank=True, default="")
    sentiment = models.CharField(max_length=32, blank=True, default="")

    video_count = models.PositiveIntegerField(default=0)
    generated_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-generated_at"]

    def __str__(self):
        return f"Digest: {self.source.name}"


class AlertRule(models.Model):
    class MatchMode(models.TextChoices):
        ANY = "any", "Any keyword"
        ALL = "all", "All keywords"

    class NotificationChannel(models.TextChoices):
        IN_APP = "in_app", "In-app"
        EMAIL = "email", "Email"
        WHATSAPP = "whatsapp", "WhatsApp"

    # Optional owner. Anonymous rules are allowed but can only deliver in-app
    # until verified; this is what a paid subscription will later attach to.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="alert_rules",
    )

    name = models.CharField(max_length=255)
    keywords = models.TextField(
        help_text="Comma-separated keywords, people, parties, districts, or topics to watch.",
    )
    match_mode = models.CharField(
        max_length=20,
        choices=MatchMode.choices,
        default=MatchMode.ANY,
    )

    source_type = models.CharField(
        max_length=50,
        choices=Source.SourceType.choices,
        blank=True,
        db_index=True,
    )
    primary_topic = models.CharField(
        max_length=100,
        choices=ContentItem.NewsTopic.choices,
        blank=True,
        db_index=True,
    )
    minimum_relevance = models.FloatField(default=0.0)

    notification_channel = models.CharField(
        max_length=20,
        choices=NotificationChannel.choices,
        default=NotificationChannel.IN_APP,
    )
    email = models.EmailField(blank=True)
    phone = models.CharField(
        max_length=20,
        blank=True,
        help_text="E.164 format, e.g. +91XXXXXXXXXX, for WhatsApp delivery.",
    )

    # Email/WhatsApp delivery is blocked until the contact is verified. This
    # closes the abuse vector where anyone could register another person's
    # address or number for notifications.
    is_verified = models.BooleanField(default=False)
    verification_token = models.CharField(max_length=64, blank=True)

    is_active = models.BooleanField(default=True, db_index=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["is_active", "updated_at"]),
            models.Index(fields=["source_type", "primary_topic"]),
        ]

    def keyword_list(self):
        return [
            keyword.strip()
            for keyword in self.keywords.split(",")
            if keyword.strip()
        ]

    def __str__(self):
        return self.name


class AlertEvent(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "New"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
        READ = "read", "Read"

    rule = models.ForeignKey(
        AlertRule,
        on_delete=models.CASCADE,
        related_name="events",
    )
    content_item = models.ForeignKey(
        ContentItem,
        on_delete=models.CASCADE,
        related_name="alert_events",
    )

    matched_keywords = models.JSONField(default=list, blank=True)
    snippet = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NEW,
        db_index=True,
    )
    error_message = models.TextField(blank=True)

    matched_at = models.DateTimeField(default=timezone.now, db_index=True)
    notified_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-matched_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["rule", "content_item"],
                name="unique_alert_rule_content_item",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "matched_at"]),
            models.Index(fields=["rule", "matched_at"]),
        ]

    def __str__(self):
        return f"{self.rule.name}: {self.content_item_id}"