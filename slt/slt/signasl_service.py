from functools import lru_cache
import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.utils.text import slugify


SIGNASL_BASE_URL = 'https://www.signasl.org'
DICTIONARY_API_URL = 'https://api.dictionaryapi.dev/api/v2/entries/en'
MAX_WORDS = 8

VIDEO_PATTERN = re.compile(
    r'<video[^>]*poster="(?P<poster>[^"]*)"[^>]*>\s*'
    r'<source\s+src="(?P<src>[^"]+)"[^>]*>.*?</video>.*?'
    r'<i>(?P<label>.*?)</i>\s*<span[^>]*>-\s*(?P<provider>[^<]+)',
    re.IGNORECASE | re.DOTALL,
)

TITLE_PATTERN = re.compile(
    r'<title>\s*American Sign Language ASL Video Dictionary(?:\s*-\s*(?P<title>.*?))?\s*</title>',
    re.IGNORECASE | re.DOTALL,
)


def _clean_text(value: str) -> str:
    return re.sub(r'\s+', ' ', value).strip()


def _build_sequence(entries: list[dict]) -> list[dict]:
    return [
        {
            'src': entry['videos'][0]['src'],
            'poster': entry['videos'][0]['poster'],
        }
        for entry in entries
        if entry['found'] and entry['videos']
    ]


@lru_cache(maxsize=256)
def fetch_definition(term: str) -> str | None:
    normalized_term = _clean_text(term).lower()
    if not normalized_term:
        return None

    if len(normalized_term) == 1 and normalized_term.isalpha():
        upper_term = normalized_term.upper()
        return f'The letter {upper_term} in the English alphabet.'

    if normalized_term.isdigit():
        return f'The number {normalized_term}.'

    request = Request(f'{DICTIONARY_API_URL}/{normalized_term}', headers={'User-Agent': 'Mozilla/5.0'})

    try:
        payload = json.load(urlopen(request, timeout=20))
    except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
        return None

    if not isinstance(payload, list) or not payload:
        return None

    try:
        meanings = payload[0].get('meanings', [])
        for meaning in meanings:
            definitions = meaning.get('definitions', [])
            for definition in definitions:
                text = _clean_text(definition.get('definition', ''))
                if text:
                    return text
    except (AttributeError, IndexError, TypeError):
        return None

    return None


@lru_cache(maxsize=256)
def fetch_sign_page(slug: str) -> dict:
    page_url = f'{SIGNASL_BASE_URL}/sign/{slug}'
    request = Request(page_url, headers={'User-Agent': 'Mozilla/5.0'})

    try:
        html = urlopen(request, timeout=20).read().decode('utf-8', errors='ignore')
    except (HTTPError, URLError, TimeoutError):
        return {
            'slug': slug,
            'page_url': page_url,
            'display_term': slug.replace('-', ' '),
            'videos': [],
            'found': False,
        }

    title_match = TITLE_PATTERN.search(html)
    display_term = _clean_text(title_match.group('title')) if title_match and title_match.group('title') else slug.replace('-', ' ')
    videos = []

    for match in VIDEO_PATTERN.finditer(html):
        source_url = match.group('src').strip()
        provider = _clean_text(match.group('provider'))
        poster = match.group('poster').strip()
        label = _clean_text(match.group('label'))

        if not source_url:
            continue

        videos.append(
            {
                'src': source_url,
                'poster': poster,
                'provider': provider,
                'label': label,
            }
        )

    return {
        'slug': slug,
        'page_url': page_url,
        'display_term': display_term,
        'videos': videos,
        'found': bool(videos),
    }


def lookup_text(text: str) -> dict:
    normalized = _clean_text(re.sub(r'[^\w\s\-\']+', ' ', text.lower()))
    words = [word for word in normalized.split(' ') if word]

    if not words:
        return {
            'strategy': 'empty',
            'entries': [],
            'sequence': [],
            'truncated': False,
        }

    phrase = ' '.join(words)

    if len(words) == 1:
        token = words[0]

        if len(token) == 1 and token.isalpha():
            letter_result = fetch_sign_page(token)
            letter_result['term'] = token
            letter_result['definition'] = fetch_definition(token)
            entries = [letter_result]
            return {
                'strategy': 'alphabet',
                'entries': entries,
                'sequence': _build_sequence(entries),
                'truncated': False,
            }

        if token.isdigit():
            number_result = fetch_sign_page(token)
            number_result['term'] = token
            number_result['definition'] = fetch_definition(token)

            if number_result['found']:
                entries = [number_result]
                return {
                    'strategy': 'number',
                    'entries': entries,
                    'sequence': _build_sequence(entries),
                    'truncated': False,
                }

            entries = []
            for digit in token[:MAX_WORDS]:
                digit_result = fetch_sign_page(digit)
                digit_result['term'] = digit
                digit_result['definition'] = fetch_definition(digit)
                entries.append(digit_result)

            return {
                'strategy': 'number-sequence',
                'entries': entries,
                'sequence': _build_sequence(entries),
                'truncated': len(token) > MAX_WORDS,
            }

    phrase_slug = slugify(phrase)

    if len(words) > 1 and len(words) <= 5 and phrase_slug:
        phrase_result = fetch_sign_page(phrase_slug)
        if phrase_result['found']:
            phrase_result['term'] = phrase
            phrase_result['definition'] = fetch_definition(phrase) or f'A short phrase result for "{phrase}".'
            return {
                'strategy': 'phrase',
                'entries': [phrase_result],
                'sequence': _build_sequence([phrase_result]),
                'truncated': False,
            }

    truncated = len(words) > MAX_WORDS
    entries = []

    for word in words[:MAX_WORDS]:
        slug = slugify(word)
        if not slug:
            continue

        result = fetch_sign_page(slug)
        result['term'] = word
        result['definition'] = fetch_definition(word)
        entries.append(result)

    return {
        'strategy': 'word-by-word',
        'entries': entries,
        'sequence': _build_sequence(entries),
        'truncated': truncated,
    }