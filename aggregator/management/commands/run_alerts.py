from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.utils import timezone

from aggregator.models import AlertEvent, AlertRule
from aggregator.services.alerts import create_alert_events


class Command(BaseCommand):
    help = "Match active alert rules against recent content and create notifications."

    def add_arguments(self, parser):
        parser.add_argument("--hours", type=int, default=24)
        parser.add_argument("--limit-per-rule", type=int, default=200)
        parser.add_argument("--dry-run", action="store_true")

    def _send_email(self, event):
        rule = event.rule
        item = event.content_item

        if not rule.email:
            return False, "Alert rule has no email address."

        title = item.title_en or item.title_ta or "NewsIQ alert match"
        subject = f"NewsIQ Alert: {rule.name}"
        body = "\n".join([
            f"Alert: {rule.name}",
            f"Matched: {', '.join(event.matched_keywords or [])}",
            f"Source: {item.source.name}",
            f"Title: {title}",
            f"URL: {item.url}",
            "",
            event.snippet,
        ])

        send_mail(
            subject=subject,
            message=body,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            recipient_list=[rule.email],
            fail_silently=False,
        )

        return True, ""

    def handle(self, *args, **options):
        hours = options["hours"]
        limit_per_rule = options["limit_per_rule"]
        dry_run = options["dry_run"]

        rules = AlertRule.objects.filter(is_active=True).order_by("name")

        if not rules.exists():
            self.stdout.write(self.style.WARNING(
                "No active alert rules found. Create rules in /alerts/ or Django admin."
            ))
            return

        total_created = 0
        total_sent = 0
        total_failed = 0

        for rule in rules:
            if dry_run:
                self.stdout.write(f"[DRY RUN] Checking rule: {rule.name}")
                continue

            events = create_alert_events(
                rule=rule,
                hours=hours,
                limit=limit_per_rule,
            )

            total_created += len(events)

            for event in events:
                if rule.notification_channel != AlertRule.NotificationChannel.EMAIL:
                    continue

                try:
                    sent, error = self._send_email(event)
                except Exception as exc:
                    sent = False
                    error = str(exc)

                if sent:
                    event.status = AlertEvent.Status.SENT
                    event.notified_at = timezone.now()
                    event.error_message = ""
                    total_sent += 1
                else:
                    event.status = AlertEvent.Status.FAILED
                    event.error_message = error
                    total_failed += 1

                event.save(update_fields=[
                    "status",
                    "notified_at",
                    "error_message",
                ])

            self.stdout.write(
                f"{rule.name}: created {len(events)} new alert event(s)"
            )

        self.stdout.write(self.style.SUCCESS(
            f"Alerts complete. Created={total_created}, "
            f"Emails sent={total_sent}, Failed={total_failed}"
        ))
