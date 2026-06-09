import hashlib
import re
from bs4 import BeautifulSoup
from django.utils import timezone
import dateparser


def sha256_text(value: str) -> str:
    return hashlib.sha256((value or '').encode('utf-8')).hexdigest()


def html_to_text(value: str) -> str:
    if not value:
        return ''
    soup = BeautifulSoup(value, 'html.parser')
    return re.sub(r'\s+', ' ', soup.get_text(' ', strip=True)).strip()


def clean_text(value: str) -> str:
    value = value or ''
    value = re.sub(r'\s+', ' ', value)
    return value.strip()


def parse_datetime(value):
    if not value:
        return None
    try:
        parsed = dateparser.parse(str(value))
        if not parsed:
            return None
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
        return parsed
    except Exception:
        return None


def safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default
