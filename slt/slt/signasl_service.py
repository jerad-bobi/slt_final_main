from functools import lru_cache
import json
import random
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin
from urllib.request import Request, urlopen

from django.utils.text import slugify


SIGNASL_BASE_URL = 'https://www.signasl.org'
HANDSPEAK_BASE_URL = 'https://www.handspeak.com'
HANDSPEAK_SEARCH_URL = f'{HANDSPEAK_BASE_URL}/word/app/search-dict.php'
DICTIONARY_API_URL = 'https://api.dictionaryapi.dev/api/v2/entries/en'
PROVIDER_TIMEOUT_SECONDS = 6
MAX_WORDS = 8
QUIZ_CHOICES = 4
DIGIT_WORDS = {
    '0': 'zero',
    '1': 'one',
    '2': 'two',
    '3': 'three',
    '4': 'four',
    '5': 'five',
    '6': 'six',
    '7': 'seven',
    '8': 'eight',
    '9': 'nine',
}
QUIZ_TERMS = (
    'hello',
    'good',
    'bad',
    'please',
    'sorry',
    'thank you',
    'help',
    'friend',
    'family',
    'mother',
    'father',
    'brother',
    'sister',
    'teacher',
    'student',
    'school',
    'book',
    'read',
    'write',
    'learn',
    'study',
    'practice',
    'work',
    'play',
    'home',
    'water',
    'food',
    'eat',
    'drink',
    'apple',
    'banana',
    'orange',
    'happy',
    'sad',
    'love',
    'like',
    'day',
    'night',
    'morning',
    'today',
    'tomorrow',
    'week',
    'month',
    'year',
    'time',
    'name',
    'question',
    'answer',
    'yes',
    'no',
    'stop',
    'go',
    'slow',
    'fast',
    'computer',
    'phone',
    'music',
    'movie',
    'car',
    'travel',
    'finish',
)

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

HANDSPEAK_TITLE_PATTERN = re.compile(
    r'<title>\s*(?P<title>.*?)\s*•\s*ASL Dictionary\s*</title>',
    re.IGNORECASE | re.DOTALL,
)

HANDSPEAK_VIDEO_PATTERN = re.compile(
    r'<video[^>]*class="[^"]*v-asl[^"]*"[^>]*src="(?P<src>[^"]+)"[^>]*>.*?</video>',
    re.IGNORECASE | re.DOTALL,
)

HANDSPEAK_HEADING_PATTERN = re.compile(
    r'<h3[^>]*>\s*(?P<label>.*?)\s*</h3>',
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


def _format_quiz_label(term: str) -> str:
    return _clean_text(term).title()


def _absolute_url(base_url: str, maybe_relative_url: str) -> str:
    return urljoin(base_url, maybe_relative_url or '')


def _empty_result(slug: str, page_url: str, display_term: str, provider: str | None = None) -> dict:
    return {
        'slug': slug,
        'page_url': page_url,
        'display_term': display_term,
        'videos': [],
        'found': False,
        'provider': provider or '',
    }


def _normalize_match_key(value: str) -> str:
    return _clean_text(re.sub(r'[^a-z0-9]+', ' ', value.lower()))


def _extract_handspeak_match_keys(value: str) -> set[str]:
    candidates = {_normalize_match_key(value)}

    for token in re.split(r'\s*,\s*', value):
        normalized_token = _normalize_match_key(token)
        if normalized_token:
            candidates.add(normalized_token)

    for token in re.findall(r'\(([^)]+)\)', value):
        normalized_token = _normalize_match_key(token)
        if normalized_token:
            candidates.add(normalized_token)

    candidates.discard('')
    return candidates


def _open_json(request: Request) -> dict | list | None:
    try:
        return json.load(urlopen(request, timeout=PROVIDER_TIMEOUT_SECONDS))
    except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
        return None


def _open_html(request: Request) -> str | None:
    try:
        return urlopen(request, timeout=PROVIDER_TIMEOUT_SECONDS).read().decode('utf-8', errors='ignore')
    except (HTTPError, URLError, TimeoutError):
        return None


def _pick_handspeak_word(wordlist: list[dict], *queries: str) -> dict | None:
    normalized_queries = [_normalize_match_key(query) for query in queries if _normalize_match_key(query)]
    if not normalized_queries:
        return wordlist[0] if wordlist else None

    for item in wordlist:
        match_keys = _extract_handspeak_match_keys(str(item.get('signName', '')))
        if any(query in match_keys for query in normalized_queries):
            return item

    for item in wordlist:
        sign_name = _normalize_match_key(str(item.get('signName', '')))
        if any(query in sign_name.split(' ') for query in normalized_queries):
            return item

    for item in wordlist:
        sign_name = _normalize_match_key(str(item.get('signName', '')))
        if any(query and sign_name.startswith(query) for query in normalized_queries):
            return item

    return wordlist[0] if wordlist else None


def _get_handspeak_query_candidates(query: str) -> list[str]:
    normalized_query = _clean_text(query)
    candidates = [normalized_query]

    if normalized_query.isdigit() and len(normalized_query) == 1:
        digit_word = DIGIT_WORDS.get(normalized_query)
        if digit_word:
            candidates.append(digit_word)

    return candidates


def _parse_handspeak_videos(html: str, poster_url: str) -> list[dict]:
    videos = []
    headings = HANDSPEAK_HEADING_PATTERN.findall(html)

    for index, match in enumerate(HANDSPEAK_VIDEO_PATTERN.finditer(html)):
        source_url = _absolute_url(HANDSPEAK_BASE_URL, match.group('src').strip())
        if not source_url:
            continue

        label = ''
        if index < len(headings):
            label = _clean_text(re.sub(r'<[^>]+>', ' ', headings[index]))

        videos.append(
            {
                'src': source_url,
                'poster': poster_url,
                'provider': 'Handspeak',
                'label': label,
            }
        )

    return videos


@lru_cache(maxsize=256)
def fetch_quiz_entry(term: str) -> dict:
    result = fetch_sign_entry(term)
    result['term'] = term
    result['definition'] = fetch_definition(term)
    return result


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

    encoded_term = quote(normalized_term, safe='')
    request = Request(f'{DICTIONARY_API_URL}/{encoded_term}', headers={'User-Agent': 'Mozilla/5.0'})
    payload = _open_json(request)
    if not isinstance(payload, list):
        return None

    if not payload:
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
def fetch_signasl_page(slug: str) -> dict:
    page_url = f'{SIGNASL_BASE_URL}/sign/{slug}'
    request = Request(page_url, headers={'User-Agent': 'Mozilla/5.0'})

    html = _open_html(request)
    if html is None:
        return _empty_result(slug, page_url, slug.replace('-', ' '), 'SignASL')

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
        'provider': 'SignASL',
    }


@lru_cache(maxsize=256)
def fetch_handspeak_page(query: str) -> dict:
    normalized_query = _clean_text(query)
    slug = slugify(normalized_query)
    fallback_page_url = f'{HANDSPEAK_BASE_URL}/word/'
    if not normalized_query:
        return _empty_result(slug, fallback_page_url, normalized_query, 'Handspeak')

    for candidate_query in _get_handspeak_query_candidates(normalized_query):
        search_request = Request(
            f'{HANDSPEAK_SEARCH_URL}?q={quote(candidate_query, safe="")}',
            headers={'User-Agent': 'Mozilla/5.0'},
        )
        payload = _open_json(search_request)
        if not isinstance(payload, dict) or not payload.get('ok'):
            continue

        wordlist = payload.get('wordlist')
        if not isinstance(wordlist, list) or not wordlist:
            continue

        selected_word = _pick_handspeak_word(wordlist, normalized_query, candidate_query)
        if not selected_word:
            continue

        page_path = str(selected_word.get('url', '')).strip()
        page_url = _absolute_url(HANDSPEAK_BASE_URL, page_path)
        detail_request = Request(page_url, headers={'User-Agent': 'Mozilla/5.0'})
        html = _open_html(detail_request)
        if html is None:
            return _empty_result(slug, page_url or fallback_page_url, normalized_query, 'Handspeak')

        title_match = HANDSPEAK_TITLE_PATTERN.search(html)
        display_term = normalized_query
        if title_match and title_match.group('title'):
            display_term = _clean_text(title_match.group('title').replace("'", ' '))

        media_list = payload.get('media') if isinstance(payload.get('media'), list) else []
        poster_url = ''
        if media_list:
            poster_url = _absolute_url(HANDSPEAK_BASE_URL, str(media_list[0].get('mediaShot', '')).strip())

        videos = _parse_handspeak_videos(html, poster_url)
        return {
            'slug': slug,
            'page_url': page_url or fallback_page_url,
            'display_term': display_term,
            'videos': videos,
            'found': bool(videos),
            'provider': 'Handspeak',
        }

    return _empty_result(slug, fallback_page_url, normalized_query, 'Handspeak')


@lru_cache(maxsize=256)
def fetch_sign_entry(term: str) -> dict:
    normalized_term = _clean_text(term)
    slug = slugify(normalized_term)
    display_term = normalized_term or slug.replace('-', ' ')

    if not normalized_term:
        return _empty_result(slug, '', display_term)

    for provider in (fetch_signasl_page, fetch_handspeak_page):
        try:
            if provider is fetch_signasl_page:
                result = provider(slug)
            else:
                result = provider(normalized_term)
        except Exception:
            continue

        if result.get('found'):
            return result

    return _empty_result(slug, '', display_term)


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
            letter_result = fetch_sign_entry(token)
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
            number_result = fetch_sign_entry(token)
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
                digit_result = fetch_sign_entry(digit)
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
        phrase_result = fetch_sign_entry(phrase)
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

        result = fetch_sign_entry(word)
        result['term'] = word
        result['definition'] = fetch_definition(word)
        entries.append(result)

    return {
        'strategy': 'word-by-word',
        'entries': entries,
        'sequence': _build_sequence(entries),
        'truncated': truncated,
    }


def get_quiz_question() -> dict:
    return get_quiz_question_from_terms(QUIZ_TERMS)


def get_quiz_question_from_terms(terms: tuple[str, ...] | list[str]) -> dict:
    terms = list(terms)
    random.shuffle(terms)

    correct_entry = None
    correct_term = ''

    for term in terms:
        entry = fetch_quiz_entry(term)
        if entry['found'] and entry['videos']:
            correct_entry = entry
            correct_term = term
            break

    if not correct_entry:
        raise LookupError('No quiz entries available from the configured sign providers.')

    distractor_pool = [term for term in QUIZ_TERMS if term != correct_term]
    distractor_terms = random.sample(distractor_pool, k=QUIZ_CHOICES - 1)
    choice_terms = [correct_term, *distractor_terms]
    random.shuffle(choice_terms)

    primary_video = correct_entry['videos'][0]

    return {
        'prompt': 'What does this sign mean?',
        'video': {
            'src': primary_video['src'],
            'poster': primary_video['poster'],
            'provider': primary_video.get('provider') or 'SignASL',
            'page_url': correct_entry['page_url'],
        },
        'choices': [
            {
                'value': choice,
                'label': _format_quiz_label(choice),
            }
            for choice in choice_terms
        ],
        'correct_answer': correct_term,
        'correct_label': _format_quiz_label(correct_term),
        'definition': correct_entry.get('definition') or '',
    }