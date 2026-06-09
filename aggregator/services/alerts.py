from __future__ import annotations

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from aggregator.models import AlertEvent, AlertRule, ContentItem


def searchable_text(item):
    nlp = getattr(item, "nlp", None)

    parts = [
        item.title_ta,
        item.title_en,
        item.body_ta,
        item.body_en,
        item.primary_topic,
        item.source.name if item.source else "",
        item.source.source_type if item.source else "",
    ]

    if nlp:
        parts.extend([
            nlp.summary_ta,
            nlp.summary_en,
            " ".join(nlp.topics or []),
            " ".join(nlp.people or []),
            " ".join(nlp.parties or []),
            " ".join(nlp.districts or []),
            nlp.sentiment,
            nlp.emotion,
        ])

    return " ".join(str(part) for part in parts if part).lower()


def item_relevance(item):
    nlp = getattr(item, "nlp", None)
    if not nlp:
        return 0.0

    return float(nlp.news_relevance_score or 0.0)


def matched_keywords(rule, item):
    keywords = rule.keyword_list()
    if not keywords:
        return []

    text = searchable_text(item)

    matches = [
        keyword
        for keyword in keywords
        if keyword.lower() in text
    ]

    if rule.match_mode == AlertRule.MatchMode.ALL:
        return matches if len(matches) == len(keywords) else []

    return matches


def item_matches_rule(rule, item):
    if rule.source_type and item.source.source_type != rule.source_type:
        return False, []

    if rule.primary_topic and item.primary_topic != rule.primary_topic:
        return False, []

    if item_relevance(item) < rule.minimum_relevance:
        return False, []

    matches = matched_keywords(rule, item)
    return bool(matches), matches


def candidate_items_for_rule(rule, hours=24):
    if rule.last_checked_at:
        since = rule.last_checked_at
    else:
        since = timezone.now() - timedelta(hours=hours)

    items = (
        ContentItem.objects
        .select_related("source", "nlp")
        .filter(
            Q(published_at__gte=since)
            | Q(published_at__isnull=True, created_at__gte=since)
        )
        .order_by("-published_at", "-created_at")
    )

    if rule.source_type:
        items = items.filter(source__source_type=rule.source_type)

    if rule.primary_topic:
        items = items.filter(primary_topic=rule.primary_topic)

    return items


def build_snippet(item, max_length=280):
    nlp = getattr(item, "nlp", None)

    text = (
        item.title_en
        or item.title_ta
        or (nlp.summary_en if nlp else "")
        or (nlp.summary_ta if nlp else "")
        or item.body_en
        or item.body_ta
    )

    text = " ".join(str(text or "").split())

    if len(text) <= max_length:
        return text

    return f"{text[:max_length - 1].rstrip()}..."


def create_alert_events(rule, hours=24, limit=200):
    created_events = []
    checked_at = timezone.now()

    for item in candidate_items_for_rule(rule, hours=hours)[:limit]:
        is_match, matches = item_matches_rule(rule, item)

        if not is_match:
            continue

        event, was_created = AlertEvent.objects.get_or_create(
            rule=rule,
            content_item=item,
            defaults={
                "matched_keywords": matches,
                "snippet": build_snippet(item),
            },
        )

        if was_created:
            created_events.append(event)

    rule.last_checked_at = checked_at
    rule.save(update_fields=["last_checked_at", "updated_at"])

    return created_events
