"""Optional Tamil-English translation helpers.

The MVP can run without a translation provider. In that case Tamil text is still
stored and analyzed, while English fields are left blank or marked as pending.

Supported providers:
1. TRANSLATION_PROVIDER=libretranslate
   LIBRETRANSLATE_URL=http://localhost:5000
   LIBRETRANSLATE_API_KEY=optional

2. TRANSLATION_PROVIDER=openai_compatible
   OPENAI_COMPATIBLE_BASE_URL=http://localhost:11434/v1 or any compatible URL
   OPENAI_COMPATIBLE_API_KEY=optional
   OPENAI_COMPATIBLE_MODEL=llama3.2:latest

The openai_compatible mode is useful if you run a local OpenAI-compatible server
through Ollama, LM Studio, vLLM, or an institutional LLM endpoint.
"""

from __future__ import annotations

import os
from typing import Literal

import requests

Language = Literal['ta', 'en']


class TranslationUnavailable(Exception):
    pass


def _clean_translation(text: str) -> str:
    return (text or '').strip().strip('"').strip()


def _translate_with_libretranslate(text: str, source: Language, target: Language) -> str:
    base_url = os.getenv('LIBRETRANSLATE_URL', '').rstrip('/')
    if not base_url:
        raise TranslationUnavailable('LIBRETRANSLATE_URL is not configured')

    payload = {
        'q': text,
        'source': source,
        'target': target,
        'format': 'text',
    }
    api_key = os.getenv('LIBRETRANSLATE_API_KEY', '')
    if api_key:
        payload['api_key'] = api_key

    response = requests.post(f'{base_url}/translate', json=payload, timeout=60)
    response.raise_for_status()
    data = response.json()
    translated = data.get('translatedText', '')
    return _clean_translation(translated)


def _translate_with_openai_compatible(text: str, source: Language, target: Language) -> str:
    base_url = os.getenv('OPENAI_COMPATIBLE_BASE_URL', '').rstrip('/')
    model = os.getenv('OPENAI_COMPATIBLE_MODEL', '')
    api_key = os.getenv('OPENAI_COMPATIBLE_API_KEY', '')
    if not base_url or not model:
        raise TranslationUnavailable('OPENAI_COMPATIBLE_BASE_URL and OPENAI_COMPATIBLE_MODEL are required')

    if source == 'ta' and target == 'en':
        instruction = 'Translate the following Tamil news text into clear English. Return only the translation.'
    elif source == 'en' and target == 'ta':
        instruction = 'Translate the following English news text into clear Tamil. Return only the translation.'
    else:
        instruction = f'Translate this text from {source} to {target}. Return only the translation.'

    headers = {'Content-Type': 'application/json'}
    if api_key:
        headers['Authorization'] = f'Bearer {api_key}'

    payload = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': instruction},
            {'role': 'user', 'content': text[:6000]},
        ],
        'temperature': 0.1,
    }
    response = requests.post(f'{base_url}/chat/completions', json=payload, headers=headers, timeout=120)
    response.raise_for_status()
    data = response.json()
    translated = data.get('choices', [{}])[0].get('message', {}).get('content', '')
    return _clean_translation(translated)


def translate_text(text: str, source: Language = 'ta', target: Language = 'en') -> str:
    """Translate text if a provider is configured.

    Returns an empty string when translation is not configured or fails. This is
    intentional: the crawler/NLP pipeline should not break just because a
    translation service is unavailable.
    """
    text = (text or '').strip()
    if not text:
        return ''
    if source == target:
        return text

    provider = os.getenv('TRANSLATION_PROVIDER', 'none').strip().lower()
    try:
        if provider == 'libretranslate':
            return _translate_with_libretranslate(text, source, target)
        if provider == 'openai_compatible':
            return _translate_with_openai_compatible(text, source, target)
    except Exception:
        return ''
    return ''


def translation_status() -> dict:
    provider = os.getenv('TRANSLATION_PROVIDER', 'none').strip().lower()
    return {
        'provider': provider,
        'configured': provider in {'libretranslate', 'openai_compatible'},
        'libretranslate_url': os.getenv('LIBRETRANSLATE_URL', ''),
        'openai_compatible_base_url': os.getenv('OPENAI_COMPATIBLE_BASE_URL', ''),
        'openai_compatible_model': os.getenv('OPENAI_COMPATIBLE_MODEL', ''),
    }
