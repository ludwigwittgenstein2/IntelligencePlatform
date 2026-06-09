#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

LOG="$(pwd)/pipeline.log"
exec >> "$LOG" 2>&1
echo "=== pipeline start $(date -Is) ==="

python manage.py crawl_youtube --limit 15
python manage.py crawl_rss --limit 15
python manage.py sync_public_jobs --limit-per-source 50
python manage.py fetch_transcripts --limit 30 --whisper-model small
python manage.py translate_items
python manage.py analyze_items
python manage.py summarize_youtube_channels
python manage.py build_daily_report

echo "=== pipeline done $(date -Is) ==="