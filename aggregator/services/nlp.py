import re
from typing import Dict, List

from aggregator.models import ContentItem
from .translation import translate_text
from .utils import clean_text

PEOPLE_TERMS = {
    'மு.க.ஸ்டாலின்': ['ஸ்டாலின்', 'மு.க.ஸ்டாலின்', 'MK Stalin', 'M K Stalin'],
    'எடப்பாடி பழனிசாமி': ['எடப்பாடி', 'EPS', 'பழனிசாமி', 'Edappadi'],
    'விஜய்': ['விஜய்', 'TVK Vijay', 'தளபதி', 'Vijay'],
    'சீமான்': ['சீமான்', 'Seeman'],
    'அண்ணாமலை': ['அண்ணாமலை', 'Annamalai'],
    'நரேந்திர மோடி': ['மோடி', 'Modi'],
    'ஆளுநர்': ['ஆளுநர்', 'Governor', 'Ravi', 'ஆர்.என்.ரவி'],
}

PARTY_TERMS = {
    'DMK': ['திமுக', 'DMK', 'தி.மு.க'],
    'AIADMK': ['அதிமுக', 'AIADMK', 'அ.தி.மு.க'],
    'BJP': ['பாஜக', 'BJP', 'பாரதிய ஜனதா'],
    'TVK': ['தவெக', 'TVK', 'தமிழக வெற்றிக் கழகம்'],
    'NTK': ['நாம் தமிழர்', 'NTK', 'நாதக'],
    'PMK': ['பாமக', 'PMK'],
    'VCK': ['விசிக', 'VCK', 'விடுதலை சிறுத்தைகள்'],
    'Congress': ['காங்கிரஸ்', 'Congress'],
}

DISTRICT_TERMS = [
    'சென்னை', 'கோயம்புத்தூர்', 'மதுரை', 'திருநெல்வேலி', 'தூத்துக்குடி', 'கன்னியாகுமரி',
    'சேலம்', 'திருச்சி', 'தஞ்சாவூர்', 'வேலூர்', 'திருப்பூர்', 'ஈரோடு', 'கடலூர்',
    'விழுப்புரம்', 'ராமநாதபுரம்', 'சிவகங்கை', 'நாகப்பட்டினம்', 'கரூர்', 'தர்மபுரி',
    'கிருஷ்ணகிரி', 'நீலகிரி', 'புதுக்கோட்டை', 'திருவாரூர்', 'திருவண்ணாமலை',
]

TOPIC_KEYWORDS = {
    'politics_governance': ['அரசு', 'முதல்வர்', 'அமைச்சர்', 'சட்டசபை', 'governance', 'government'],
    'election': ['தேர்தல்', 'வாக்கு', 'வாக்காளர்', 'கூட்டணி', 'campaign', 'election'],
    'opposition_parties': ['எதிர்க்கட்சி', 'அதிமுக', 'எடப்பாடி', 'opposition'],
    'centre_state': ['மத்திய அரசு', 'ஆளுநர்', 'Governor', 'centre', 'மோடி'],
    'law_order': ['கொலை', 'வன்முறை', 'போலீஸ்', 'கைது', 'சட்டம்', 'law', 'crime'],
    'court_legal': ['நீதிமன்றம்', 'உச்சநீதிமன்றம்', 'High Court', 'court', 'case'],
    'caste_identity': ['சாதி', 'இனம்', 'ஒதுக்கீடு', 'reservation', 'community'],
    'religion_identity': ['மதம்', 'கோவில்', 'church', 'mosque', 'Hindu', 'Christian', 'Muslim'],
    'education': ['கல்வி', 'பள்ளி', 'கல்லூரி', 'NEET', 'மாணவர்', 'education'],
    'jobs_economy': ['வேலை', 'தொழில்', 'முதலீடு', 'தொழிற்சாலை', 'economy', 'jobs'],
    'welfare_schemes': ['உதவி', 'திட்டம்', 'மகளிர்', 'ரேஷன்', 'welfare', 'scheme'],
    'infrastructure': ['சாலை', 'பாலம்', 'மெட்ரோ', 'மின்சாரம்', 'நீர்', 'road', 'metro'],
    'corruption': ['ஊழல்', 'லஞ்சம்', 'corruption', 'scam'],
    'health': ['மருத்துவம்', 'மருத்துவமனை', 'சுகாதாரம்', 'doctor', 'hospital', 'health'],
    'weather_disaster': ['மழை', 'வெள்ளம்', 'புயல்', 'வானிலை', 'rain', 'flood', 'weather'],
    'business_price': ['விலை', 'பங்குச்சந்தை', 'தங்கம்', 'பெட்ரோல்', 'diesel', 'gold', 'price'],
    'sports_cinema_culture': ['விளையாட்டு', 'சினிமா', 'திரைப்படம்', 'கிரிக்கெட்', 'cinema', 'sports'],
}

NEGATIVE_WORDS = ['கண்டனம்', 'எதிர்ப்பு', 'கைது', 'ஊழல்', 'கொலை', 'வன்முறை', 'அதிர்ச்சி', 'பிரச்சனை', 'தாக்குதல்', 'தடை']
POSITIVE_WORDS = ['வரவேற்பு', 'வெற்றி', 'நன்மை', 'முன்னேற்றம்', 'வளர்ச்சி', 'பாராட்டு', 'அனுமதி']
ANGER_WORDS = ['கண்டனம்', 'ஆவேசம்', 'கோபம்', 'எதிர்ப்பு', 'தாக்குதல்', 'வன்முறை']
FEAR_WORDS = ['அச்சம்', 'பயம்', 'அபாயம்', 'அதிர்ச்சி', 'எச்சரிக்கை']
HOPE_WORDS = ['வளர்ச்சி', 'முன்னேற்றம்', 'வாய்ப்பு', 'நம்பிக்கை']


def _contains_any(text: str, terms: List[str]) -> bool:
    low = text.lower()
    return any(term.lower() in low for term in terms)


def extract_people(text: str) -> List[str]:
    return [name for name, terms in PEOPLE_TERMS.items() if _contains_any(text, terms)]


def extract_parties(text: str) -> List[str]:
    return [name for name, terms in PARTY_TERMS.items() if _contains_any(text, terms)]


def extract_districts(text: str) -> List[str]:
    return [d for d in DISTRICT_TERMS if d in text]


def classify_topics(text: str) -> List[str]:
    topics = []
    for topic, keywords in TOPIC_KEYWORDS.items():
        if _contains_any(text, keywords):
            topics.append(topic)
    return topics or ['general_news']


def summarize_text(text: str, max_sentences: int = 3) -> str:
    text = clean_text(text)
    if not text:
        return ''
    parts = re.split(r'(?<=[.!?।])\s+|(?<=।)\s+|(?<=\?)\s+', text)
    parts = [p.strip() for p in parts if p.strip()]
    if not parts:
        return text[:500]
    return ' '.join(parts[:max_sentences])[:1000]


def sentiment_and_emotion(text: str):
    neg = sum(text.count(w) for w in NEGATIVE_WORDS)
    pos = sum(text.count(w) for w in POSITIVE_WORDS)
    if neg > pos:
        sentiment = 'negative'
    elif pos > neg:
        sentiment = 'positive'
    else:
        sentiment = 'neutral'

    emotion_scores = {
        'anger': sum(text.count(w) for w in ANGER_WORDS),
        'fear': sum(text.count(w) for w in FEAR_WORDS),
        'hope': sum(text.count(w) for w in HOPE_WORDS),
    }
    emotion, score = max(emotion_scores.items(), key=lambda kv: kv[1])
    if score == 0:
        emotion = 'neutral'
    return sentiment, emotion, emotion_scores


def intensity_score(text: str, topics: List[str], parties: List[str], people: List[str]) -> float:
    exclamations = text.count('!')
    conflict_words = sum(text.count(w) for w in NEGATIVE_WORDS + ANGER_WORDS)
    named_entities = len(set(parties + people))
    topic_weight = min(len(topics) / 6, 1)
    score = min(1.0, 0.10 * exclamations + 0.12 * conflict_words + 0.10 * named_entities + 0.18 * topic_weight)
    return round(score, 3)


def news_relevance_score(topics: List[str], parties: List[str], people: List[str], districts: List[str]) -> float:
    score = 0.0
    score += min(len(topics) * 0.08, 0.32)
    score += min(len(districts) * 0.08, 0.16)
    score += min(len(parties) * 0.15, 0.30)
    score += min(len(people) * 0.11, 0.22)
    if topics == ['general_news']:
        score = max(score, 0.10)
    return round(min(score, 1.0), 3)


def analyze_content_item(item: ContentItem) -> Dict:
    tamil_text = clean_text(f'{item.title_ta}. {item.body_ta}')
    english_text = clean_text(f'{item.title_en}. {item.body_en}')
    combined_text = clean_text(f'{tamil_text} {english_text}')

    people = extract_people(combined_text)
    parties = extract_parties(combined_text)
    districts = extract_districts(combined_text)
    topics = classify_topics(combined_text)
    sentiment, emotion, emotion_scores = sentiment_and_emotion(combined_text)
    intensity = intensity_score(combined_text, topics, parties, people)
    relevance = news_relevance_score(topics, parties, people, districts)

    summary_ta = summarize_text(tamil_text)
    summary_en = summarize_text(english_text)
    if not summary_en and summary_ta:
        summary_en = translate_text(summary_ta, source='ta', target='en')

    entities = {
        'people': people,
        'parties': parties,
        'districts': districts,
        'emotion_scores': emotion_scores,
        'translation_available': bool(summary_en),
    }

    return {
        'summary_ta': summary_ta,
        'summary_en': summary_en,
        'topics': topics,
        'entities': entities,
        'people': people,
        'parties': parties,
        'districts': districts,
        'sentiment': sentiment,
        'emotion': emotion,
        'intensity_score': intensity,
        'news_relevance_score': relevance,
        # Kept for backward compatibility with the first MVP database/API.
        'political_relevance_score': relevance,
        'stance_notes': 'Rule-based MVP analysis. Translation is optional; configure TRANSLATION_PROVIDER for English fields.',
    }
