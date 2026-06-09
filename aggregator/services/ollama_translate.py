import os
import requests


OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_TRANSLATION_MODEL = os.getenv("OLLAMA_TRANSLATION_MODEL", "gpt-oss:20b")


def ask_ollama(system_prompt: str, user_prompt: str) -> str:
    url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat"

    payload = {
        "model": OLLAMA_TRANSLATION_MODEL,
        "stream": False,
        "messages": [
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ],
        "options": {
            "temperature": 0.1,
        },
    }

    response = requests.post(url, json=payload, timeout=120)
    response.raise_for_status()

    data = response.json()
    return data.get("message", {}).get("content", "").strip()


def translate_to_english(text: str) -> str:
    if not text or not text.strip():
        return ""

    system_prompt = """
You are a professional Tamil-to-English news translator.

Translate the given text into clear, natural English.
Rules:
- Preserve names, places, political parties, and organizations accurately.
- Do not add new information.
- Do not summarize unless the input is already a summary.
- Return only the English translation.
"""

    user_prompt = f"""
Translate this Tamil news text into English:

{text}
"""

    return ask_ollama(system_prompt, user_prompt)


def translate_to_tamil(text: str) -> str:
    if not text or not text.strip():
        return ""

    system_prompt = """
You are a professional English-to-Tamil news translator.

Translate the given text into clear, modern Tamil.
Rules:
- Preserve names, places, political parties, and organizations accurately.
- Do not add new information.
- Do not summarize unless the input is already a summary.
- Return only the Tamil translation.
"""

    user_prompt = f"""
Translate this English news text into Tamil:

{text}
"""

    return ask_ollama(system_prompt, user_prompt)


def summarize_in_english(text: str) -> str:
    if not text or not text.strip():
        return ""

    system_prompt = """
You are a Tamil Nadu news intelligence analyst.

Write a short English news summary.
Rules:
- 1 to 2 sentences only.
- Be factual and neutral.
- Do not exaggerate.
- Do not add facts not present in the text.
- Return only the summary.
"""

    user_prompt = f"""
Summarize this news item in English:

{text}
"""

    return ask_ollama(system_prompt, user_prompt)


def summarize_in_tamil(text: str) -> str:
    if not text or not text.strip():
        return ""

    system_prompt = """
You are a Tamil Nadu news intelligence analyst.

Write a short Tamil news summary.
Rules:
- 1 to 2 sentences only.
- Be factual and neutral.
- Do not exaggerate.
- Do not add facts not present in the text.
- Return only the Tamil summary.
"""

    user_prompt = f"""
இந்த செய்தியை தமிழில் சுருக்கமாக எழுதவும்:

{text}
"""

    return ask_ollama(system_prompt, user_prompt)