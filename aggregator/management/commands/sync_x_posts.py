import hashlib
import os
from datetime import datetime

import requests
from dateutil import parser as date_parser

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from aggregator.models import ContentItem, NLPResult, RawItem, Source


X_RECENT_SEARCH_URL = "https://api.x.com/2/tweets/search/recent"


PARTY_KEYWORDS = {
    "DMK": ["dmk", "திமுக"],
    "AIADMK": ["aiadmk", "அதிமுக"],
    "BJP": ["bjp", "பாஜக"],
    "TVK": ["tvk", "தவெக", "விஜய்"],
    "NTK": ["ntk", "நாம் தமிழர்", "சீமான்"],
    "VCK": ["vck", "விசிக"],
    "PMK": ["pmk", "பாமக"],
    "Congress": ["congress", "காங்கிரஸ்"],
}

PEOPLE_KEYWORDS = {
    "M. K. Stalin": ["stalin", "ஸ்டாலின்", "முதல்வர்"],
    "Udhayanidhi Stalin": ["udhayanidhi", "உதயநிதி", "துணை முதல்வர்"],
    "Edappadi K. Palaniswami": ["eps", "edappadi", "எடப்பாடி"],
    "Vijay": ["vijay", "விஜய்", "tvk"],
    "Annamalai": ["annamalai", "அண்ணாமலை"],
    "Seeman": ["seeman", "சீமான்"],
    "Savukku Shankar": ["savukku", "சவுக்கு"],
    "Maridhas": ["maridhas", "மாரிதாஸ்"],
}

DISTRICT_KEYWORDS = [
    "Chennai", "Coimbatore", "Madurai", "Tirunelveli", "Thoothukudi",
    "Salem", "Erode", "Tiruchirappalli", "Vellore", "Kanyakumari",
    "சென்னை", "கோவை", "மதுரை", "திருநெல்வேலி", "தூத்துக்குடி",
    "சேலம்", "ஈரோடு", "திருச்சி", "வேலூர்", "கன்னியாகுமரி",
]

NEWS_TOPIC_KEYWORDS = {
    "politics": [
        "dmk", "aiadmk", "bjp", "tvk", "ntk", "vck", "pmk",
        "election", "alliance", "opposition", "party",
        "திமுக", "அதிமுக", "பாஜக", "தவெக", "கட்சி", "தேர்தல்",
    ],
    "government_policy": [
        "chief minister", "deputy chief minister", "minister", "scheme",
        "welfare", "government", "govt", "policy",
        "முதல்வர்", "துணை முதல்வர்", "அமைச்சர்", "அரசு", "திட்டம்",
    ],
    "assembly_watch": [
        "assembly", "legislative assembly", "bill", "debate", "question hour",
        "சட்டசபை", "சட்டமன்றம்", "மசோதா", "விவாதம்",
    ],
    "education": [
        "school", "college", "student", "teacher", "exam", "neet",
        "பள்ளி", "கல்லூரி", "மாணவர்", "ஆசிரியர்", "தேர்வு",
    ],
    "health": [
        "hospital", "doctor", "nurse", "health", "medical",
        "மருத்துவம்", "மருத்துவமனை", "சுகாதாரம்",
    ],
    "law_order": [
        "police", "court", "crime", "arrest", "case", "violence",
        "காவல்", "குற்றம்", "கைது", "நீதிமன்றம்", "வழக்கு",
    ],
    "infrastructure_transport": [
        "road", "bridge", "bus", "train", "metro", "airport", "highway",
        "சாலை", "பாலம்", "பேருந்து", "ரயில்", "மெட்ரோ",
    ],
    "agriculture_farmers": [
        "farmer", "crop", "paddy", "rain", "irrigation", "delta",
        "விவசாயி", "நெல்", "மழை", "நீர்ப்பாசனம்", "டெல்டா",
    ],
    "cinema_culture": [
        "cinema", "film", "movie", "actor", "vijay", "ajith", "rajinikanth",
        "சினிமா", "திரைப்படம்", "நடிகர்", "விஜய்", "ரஜினி",
    ],
    "jobs_employment": [
        "job", "jobs", "recruitment", "vacancy", "tnpsc", "employment",
        "வேலை", "வேலைவாய்ப்பு", "பணி", "ஆட்சேர்ப்பு",
    ],
}


def make_hash(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:64]


def clean_text(text):
    return " ".join((text or "").split()).strip()


def parse_x_datetime(value):
    if not value:
        return timezone.now()

    try:
        parsed = date_parser.parse(value)

        if timezone.is_naive(parsed):
            return timezone.make_aware(parsed)

        return parsed
    except Exception:
        return timezone.now()


def classify_news_topic(text):
    text_lower = clean_text(text).lower()

    scores = {}

    for topic, keywords in NEWS_TOPIC_KEYWORDS.items():
        score = 0

        for keyword in keywords:
            if keyword.lower() in text_lower:
                score += 1

        if score:
            scores[topic] = score

    if not scores:
        return ContentItem.NewsTopic.GENERAL, []

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    primary_topic = ranked[0][0]
    secondary_topics = [topic for topic, score in ranked[1:4]]

    return primary_topic, secondary_topics


def extract_matches(text, keyword_map):
    text_lower = clean_text(text).lower()
    matches = []

    for label, keywords in keyword_map.items():
        for keyword in keywords:
            if keyword.lower() in text_lower:
                matches.append(label)
                break

    return matches


def extract_districts(text):
    text_lower = clean_text(text).lower()
    found = []

    for district in DISTRICT_KEYWORDS:
        if district.lower() in text_lower:
            found.append(district)

    return found


def build_x_url(username, tweet_id):
    if username:
        return f"https://x.com/{username}/status/{tweet_id}"

    return f"https://x.com/i/web/status/{tweet_id}"


def normalize_query(query):
    query = clean_text(query)

    if not query:
        return ""

    if "-is:retweet" not in query:
        query = f"{query} -is:retweet"

    return query


def get_author_map(response_json):
    includes = response_json.get("includes", {})
    users = includes.get("users", [])

    return {
        user.get("id"): user
        for user in users
        if user.get("id")
    }


def x_recent_search(bearer_token, query, max_results=50, next_token=None):
    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "User-Agent": "TamilNaduNewsIQ/1.0",
    }

    params = {
        "query": query,
        "max_results": max(min(max_results, 100), 10),
        "tweet.fields": ",".join([
            "id",
            "text",
            "created_at",
            "lang",
            "author_id",
            "conversation_id",
            "public_metrics",
            "referenced_tweets",
            "possibly_sensitive",
        ]),
        "expansions": "author_id",
        "user.fields": ",".join([
            "id",
            "name",
            "username",
            "verified",
            "verified_type",
            "public_metrics",
            "profile_image_url",
        ]),
    }

    if next_token:
        params["next_token"] = next_token

    response = requests.get(
        X_RECENT_SEARCH_URL,
        headers=headers,
        params=params,
        timeout=30,
    )

    if response.status_code == 429:
        raise CommandError("X API rate limit reached. Try again later.")

    if response.status_code in [401, 403]:
        raise CommandError(
            "X API authentication failed. Check X_BEARER_TOKEN and API access."
        )

    response.raise_for_status()
    return response.json()


def upsert_tweet(source, tweet, author):
    tweet_id = tweet.get("id", "")
    text = clean_text(tweet.get("text", ""))
    created_at = parse_x_datetime(tweet.get("created_at"))
    public_metrics = tweet.get("public_metrics", {}) or {}

    username = author.get("username", "") if author else ""
    author_name = author.get("name", "") if author else ""

    url = build_x_url(username, tweet_id)
    external_id = tweet_id
    content_hash = make_hash(text)

    primary_topic, secondary_topics = classify_news_topic(text)
    parties = extract_matches(text, PARTY_KEYWORDS)
    people = extract_matches(text, PEOPLE_KEYWORDS)
    districts = extract_districts(text)

    raw_item, _ = RawItem.objects.update_or_create(
        source=source,
        external_id=external_id,
        defaults={
            "url": url,
            "title": text[:240],
            "description": text,
            "raw_text": text,
            "raw_html": "",
            "raw_json": {
                "tweet": tweet,
                "author": author or {},
            },
            "published_at": created_at,
            "content_hash": content_hash,
            "status": "fetched",
        },
    )

    content_item, _ = ContentItem.objects.update_or_create(
        raw_item=raw_item,
        defaults={
            "source": source,
            "content_type": ContentItem.ContentType.TWEET,
            "primary_topic": primary_topic,
            "secondary_topics": secondary_topics,
            "title_ta": text[:240] if tweet.get("lang") == "ta" else "",
            "title_en": text[:240] if tweet.get("lang") != "ta" else "",
            "body_ta": text if tweet.get("lang") == "ta" else "",
            "body_en": text if tweet.get("lang") != "ta" else "",
            "url": url,
            "author": author_name or username,
            "published_at": created_at,
            "metrics": {
                "x_tweet_id": tweet_id,
                "x_username": username,
                "x_author_name": author_name,
                "x_lang": tweet.get("lang", ""),
                "retweet_count": public_metrics.get("retweet_count", 0),
                "reply_count": public_metrics.get("reply_count", 0),
                "like_count": public_metrics.get("like_count", 0),
                "quote_count": public_metrics.get("quote_count", 0),
                "impression_count": public_metrics.get("impression_count", 0),
                "source_role": "political_commentary",
                "confidence": "commentary_or_public_signal",
            },
        },
    )

    NLPResult.objects.update_or_create(
        content_item=content_item,
        defaults={
            "summary_ta": text[:500] if tweet.get("lang") == "ta" else "",
            "summary_en": text[:500] if tweet.get("lang") != "ta" else "",
            "topics": [primary_topic] + secondary_topics,
            "entities": {
                "author": author_name,
                "username": username,
            },
            "people": people,
            "parties": parties,
            "districts": districts,
            "sentiment": "",
            "emotion": "",
            "intensity_score": 0.0,
            "political_relevance_score": 1.0 if primary_topic in [
                ContentItem.NewsTopic.POLITICS,
                ContentItem.NewsTopic.GOVERNMENT_POLICY,
                ContentItem.NewsTopic.ASSEMBLY_WATCH,
            ] else 0.5,
            "news_relevance_score": 0.7,
            "stance_notes": "Imported from X/Twitter. Treat as public reaction or commentary, not verified reporting.",
        },
    )

    return content_item


class Command(BaseCommand):
    help = "Sync X/Twitter posts into NewsIQ using X API recent search."

    def add_arguments(self, parser):
        parser.add_argument("--source", dest="source", type=str, default="")
        parser.add_argument("--limit-per-source", dest="limit_per_source", type=int, default=50)
        parser.add_argument("--max-pages", dest="max_pages", type=int, default=1)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        bearer_token = os.environ.get("X_BEARER_TOKEN", "").strip()

        if not bearer_token:
            raise CommandError(
                "Missing X_BEARER_TOKEN. Run: export X_BEARER_TOKEN='your_token_here'"
            )

        source_filter = options["source"].strip()
        limit_per_source = max(min(options["limit_per_source"], 100), 10)
        max_pages = max(options["max_pages"], 1)
        dry_run = options["dry_run"]

        sources = Source.objects.filter(
            source_type=Source.SourceType.X,
            is_active=True,
        ).order_by("name")

        if source_filter:
            sources = sources.filter(name__icontains=source_filter)

        if not sources.exists():
            self.stdout.write(
                self.style.WARNING(
                    "No active X sources found. Run: python manage.py seed_x_sources"
                )
            )
            return

        total_seen = 0
        total_saved = 0

        for source in sources:
            query = normalize_query(source.x_query)

            if not query and source.x_handle:
                query = normalize_query(f"from:{source.x_handle}")

            if not query:
                self.stdout.write(
                    self.style.WARNING(f"Skipping {source.name}: no x_query or x_handle")
                )
                continue

            self.stdout.write(self.style.WARNING(f"Syncing X source: {source.name}"))
            self.stdout.write(f"Query: {query}")

            next_token = None
            source_seen = 0
            source_saved = 0

            for page_number in range(max_pages):
                try:
                    response_json = x_recent_search(
                        bearer_token=bearer_token,
                        query=query,
                        max_results=limit_per_source,
                        next_token=next_token,
                    )
                except Exception as exc:
                    self.stdout.write(
                        self.style.ERROR(f"Failed: {source.name} - {exc}")
                    )
                    break

                tweets = response_json.get("data", []) or []
                author_map = get_author_map(response_json)

                if not tweets:
                    self.stdout.write("No posts returned.")
                    break

                for tweet in tweets:
                    total_seen += 1
                    source_seen += 1

                    author = author_map.get(tweet.get("author_id"), {})

                    if dry_run:
                        username = author.get("username", "")
                        self.stdout.write(
                            f"[DRY RUN] @{username}: {clean_text(tweet.get('text', ''))[:140]}"
                        )
                        continue

                    upsert_tweet(source, tweet, author)
                    total_saved += 1
                    source_saved += 1

                meta = response_json.get("meta", {}) or {}
                next_token = meta.get("next_token")

                if not next_token:
                    break

            self.stdout.write(
                self.style.SUCCESS(
                    f"{source.name}: seen {source_seen}, saved {source_saved}"
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Total seen: {total_seen}. Total saved: {total_saved}."
            )
        )