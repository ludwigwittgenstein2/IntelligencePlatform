from django.urls import path

from . import views


urlpatterns = [
    # Public pages
    path("", views.dashboard, name="dashboard"),
    path("jobs/", views.jobs, name="jobs"),
    path("reports/", views.reports, name="reports"),
    path("x/", views.x_wall, name="x_wall"),
    path("alerts/", views.alerts, name="alerts"),

    # NewsIQ API endpoints
    path("api/latest/", views.api_latest, name="api_latest"),
    path("api/trends/", views.api_trends, name="api_trends"),
    path("api/youtube/", views.api_youtube, name="api_youtube"),
    path("api/track/", views.api_track, name="api_track"),

    # JobsIQ API endpoints
    path("api/jobs/", views.api_jobs, name="api_jobs"),
    path("api/alerts/", views.api_alerts, name="api_alerts"),

    # Report API endpoints
    path("api/report/", views.api_report, name="api_report"),
    path("api/daily-report/", views.api_daily_report, name="api_daily_report"),
]
