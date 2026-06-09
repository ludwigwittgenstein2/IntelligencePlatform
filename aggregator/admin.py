from django.contrib import admin
from .models import (
    AlertEvent,
    AlertRule,
    ContentItem,
    DailyReport,
    NLPResult,
    RawItem,
    Source,
)


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ('name', 'source_type', 'crawl_method', 'is_active', 'updated_at')
    list_filter = ('source_type', 'crawl_method', 'is_active')
    search_fields = ('name', 'url', 'rss_url', 'youtube_channel_id', 'x_query')


@admin.register(RawItem)
class RawItemAdmin(admin.ModelAdmin):
    list_display = ('title', 'source', 'published_at', 'fetched_at', 'status')
    list_filter = ('source', 'status')
    search_fields = ('title', 'description', 'raw_text', 'url', 'external_id')
    readonly_fields = ('fetched_at',)


@admin.register(ContentItem)
class ContentItemAdmin(admin.ModelAdmin):
    list_display = ('title_ta', 'source', 'content_type', 'published_at')
    list_filter = ('source', 'content_type')
    search_fields = ('title_ta', 'title_en', 'body_ta', 'body_en', 'url')


@admin.register(NLPResult)
class NLPResultAdmin(admin.ModelAdmin):
    list_display = ('content_item', 'sentiment', 'emotion', 'intensity_score', 'news_relevance_score')
    list_filter = ('sentiment', 'emotion')
    search_fields = ('summary_ta', 'summary_en', 'stance_notes')


@admin.register(DailyReport)
class DailyReportAdmin(admin.ModelAdmin):
    list_display = ('report_date', 'updated_at')
    search_fields = ('summary_ta', 'summary_en')


@admin.register(AlertRule)
class AlertRuleAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'keywords',
        'source_type',
        'primary_topic',
        'notification_channel',
        'is_active',
        'last_checked_at',
    )
    list_filter = (
        'is_active',
        'notification_channel',
        'source_type',
        'primary_topic',
    )
    search_fields = ('name', 'keywords', 'email')


@admin.register(AlertEvent)
class AlertEventAdmin(admin.ModelAdmin):
    list_display = (
        'rule',
        'content_item',
        'status',
        'matched_keywords',
        'matched_at',
        'notified_at',
    )
    list_filter = ('status', 'rule')
    search_fields = (
        'rule__name',
        'snippet',
        'content_item__title_ta',
        'content_item__title_en',
    )
    readonly_fields = ('matched_at', 'notified_at', 'read_at')
