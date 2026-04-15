import json
import re
import string
from base64 import b64decode
from binascii import Error as BinasciiError

from django.db import transaction
from django.db.models import Count, Max
from django.http import JsonResponse
from django.shortcuts import render

from accounts.models import Account, BrainQuizAttempt, SkeletalSignSample, SyllabusProgress

from .skeletal_classifier_service import normalize_landmarks, predict_sign_from_landmarks
from .signasl_service import QUIZ_TERMS, get_quiz_question_from_terms, lookup_text


BRAIN_QUIZ_SEEN_TERMS = 'brain_quiz_seen_terms'
SESSION_ACCOUNT_ID = 'account_id'
SKELETAL_CAPTURE_MAX_BYTES = 5 * 1024 * 1024
SYLLABUS_PROGRESS_SESSION_KEY = 'syllabus_progress'
LETTERS_AND_NUMBERS_SYLLABUS_KEY = 'letters-and-numbers'
AMBIGUOUS_SIGN_CONTEXTS = {
    frozenset({'2', 'V'}): {
        'alphabet': 'V',
        'numbers': '2',
    },
}


def _normalize_sign_folder_name(raw_name: str) -> str:
    cleaned = re.sub(r'[^A-Za-z0-9 _-]', '', raw_name).strip()
    cleaned = re.sub(r'\s+', '_', cleaned)
    return cleaned[:64]


def _get_letters_and_numbers_terms() -> list[str]:
    return list(string.ascii_uppercase) + [str(number) for number in range(10)]


def _clamp_syllabus_term_index(raw_index, terms: list[str]) -> int:
    if not terms:
        return 0

    try:
        index = int(raw_index)
    except (TypeError, ValueError):
        index = 0

    return max(0, min(index, len(terms) - 1))


def _build_syllabus_progress_payload(terms: list[str], progress) -> dict | None:
    if not progress or not terms:
        return None

    current_term_index = _clamp_syllabus_term_index(progress.get('current_term_index', 0), terms)
    return {
        'current_term_index': current_term_index,
        'current_term': terms[current_term_index],
        'total_terms': len(terms),
        'updated_at': progress.get('updated_at'),
    }


def _normalize_prediction_context(raw_context) -> str:
    context = str(raw_context or '').strip().lower()
    if context in {'alphabet', 'numbers'}:
        return context
    return 'general'


def _apply_prediction_context(result: dict, prediction_context: str) -> dict:
    if prediction_context == 'general' or not result.get('ok'):
        result['prediction_context'] = prediction_context
        return result

    predicted_sign = str(result.get('predicted_sign') or '').strip()
    candidates = result.get('candidates')
    candidate_signs = []
    if isinstance(candidates, list):
        for candidate in candidates:
            sign = str(candidate.get('sign') or '').strip()
            if sign:
                candidate_signs.append(sign)

    candidate_signs.append(predicted_sign)

    for ambiguous_group, context_map in AMBIGUOUS_SIGN_CONTEXTS.items():
        matched_signs = [sign for sign in candidate_signs if sign in ambiguous_group]
        if not matched_signs:
            continue

        resolved_sign = context_map.get(prediction_context)
        if not resolved_sign or resolved_sign not in ambiguous_group:
            continue

        result['raw_predicted_sign'] = predicted_sign
        result['predicted_sign'] = resolved_sign
        result['prediction_context'] = prediction_context
        result['resolved_by_context'] = True

        if isinstance(candidates, list):
            matching_candidate = next((candidate for candidate in candidates if str(candidate.get('sign') or '').strip() == resolved_sign), None)
            if matching_candidate:
                result['confidence'] = matching_candidate.get('confidence', result.get('confidence'))
                result['confidence_percent'] = matching_candidate.get('confidence_percent', result.get('confidence_percent'))
                result['distance'] = matching_candidate.get('distance', result.get('distance'))
                result['matched_samples'] = matching_candidate.get('samples', result.get('matched_samples'))

        return result

    result['prediction_context'] = prediction_context
    return result


def home(request):
    return render(request, 'home.html', {'active_page': 'home'})


def sharpen_your_brain(request):
    letters_and_numbers_terms = _get_letters_and_numbers_terms()
    letters_and_numbers_progress = _get_syllabus_progress(request, LETTERS_AND_NUMBERS_SYLLABUS_KEY, letters_and_numbers_terms)

    return render(
        request,
        'sharpen_your_brain.html',
        {
            'active_page': 'brain',
            'letters_and_numbers_progress': letters_and_numbers_progress,
        },
    )


def lets_practice(request):
    return render(
        request,
        'lets_practice.html',
        {
            'active_page': 'practice',
        },
    )


def signasl_lookup(request):
    text = request.GET.get('text', '')
    payload = lookup_text(text)
    return JsonResponse(payload)


def save_skeletal_hand_capture(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed.'}, status=405)

    try:
        payload = json.loads(request.body.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({'error': 'Invalid request body.'}, status=400)

    image_data = str(payload.get('image_data', '')).strip()
    sign_name_raw = str(payload.get('sign_name', '')).strip()
    sign_folder_name = _normalize_sign_folder_name(sign_name_raw)
    landmarks = payload.get('landmarks')
    feature_vector = normalize_landmarks(landmarks if isinstance(landmarks, list) else [])

    if not sign_folder_name:
        return JsonResponse({'error': 'Missing sign name.'}, status=400)

    if feature_vector is None:
        return JsonResponse({'error': 'Missing or invalid hand landmarks.'}, status=400)

    if not image_data:
        return JsonResponse({'error': 'Missing image data.'}, status=400)

    if not image_data.startswith('data:image/png;base64,'):
        return JsonResponse({'error': 'Only PNG data URL is supported.'}, status=400)

    encoded_part = image_data.split(',', 1)[1]
    try:
        binary_content = b64decode(encoded_part, validate=True)
    except (BinasciiError, ValueError):
        return JsonResponse({'error': 'Malformed image payload.'}, status=400)

    if not binary_content:
        return JsonResponse({'error': 'Empty image payload.'}, status=400)

    if len(binary_content) > SKELETAL_CAPTURE_MAX_BYTES:
        return JsonResponse({'error': 'Image payload too large.'}, status=413)

    filename = ''

    saved_sample = SkeletalSignSample.objects.create(
        sign_name=sign_name_raw,
        sign_folder=sign_folder_name,
        filename=filename,
        image_png=binary_content,
        feature_vector=feature_vector,
        source='capture',
    )

    return JsonResponse(
        {
            'saved': True,
            'filename': f'sample_{saved_sample.id}.png',
            'sample_id': saved_sample.id,
            'sign_name': sign_name_raw,
            'sign_folder': sign_folder_name,
        }
    )


def predict_skeletal_sign(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed.'}, status=405)

    try:
        payload = json.loads(request.body.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({'error': 'Invalid request body.'}, status=400)

    landmarks = payload.get('landmarks')
    if not isinstance(landmarks, list):
        return JsonResponse({'error': 'Landmarks are required.'}, status=400)

    result = predict_sign_from_landmarks(landmarks)
    if not result.get('ok'):
        return JsonResponse(result, status=400)

    prediction_context = _normalize_prediction_context(payload.get('prediction_context'))
    result = _apply_prediction_context(result, prediction_context)
    return JsonResponse(result)

    return JsonResponse(result)


def _get_current_account(request):
    account_id = request.session.get(SESSION_ACCOUNT_ID)
    if not account_id:
        return None

    try:
        return Account.objects.get(id=account_id)
    except Account.DoesNotExist:
        request.session.pop(SESSION_ACCOUNT_ID, None)
        return None


def _get_syllabus_progress(request, syllabus_key: str, terms: list[str]) -> dict | None:
    account = _get_current_account(request)
    if account:
        progress = (
            SyllabusProgress.objects.filter(account=account, syllabus_key=syllabus_key)
            .values('current_term_index', 'updated_at')
            .first()
        )
        if progress:
            updated_at = progress.get('updated_at')
            progress['updated_at'] = updated_at.isoformat() if updated_at else None
        return _build_syllabus_progress_payload(terms, progress)

    session_progress = request.session.get(SYLLABUS_PROGRESS_SESSION_KEY, {})
    progress = session_progress.get(syllabus_key)
    return _build_syllabus_progress_payload(terms, progress)


def _save_syllabus_progress(request, syllabus_key: str, terms: list[str], current_term_index: int) -> dict:
    clamped_index = _clamp_syllabus_term_index(current_term_index, terms)
    progress_payload = {
        'current_term_index': clamped_index,
        'current_term': terms[clamped_index],
        'total_terms': len(terms),
    }

    account = _get_current_account(request)
    if account:
        progress, _ = SyllabusProgress.objects.update_or_create(
            account=account,
            syllabus_key=syllabus_key,
            defaults=progress_payload,
        )
        return {
            'current_term_index': clamped_index,
            'current_term': progress.current_term,
            'total_terms': progress.total_terms,
            'updated_at': progress.updated_at.isoformat(),
        }

    session_progress = request.session.get(SYLLABUS_PROGRESS_SESSION_KEY, {})
    session_progress[syllabus_key] = {
        'current_term_index': clamped_index,
        'updated_at': None,
    }
    request.session[SYLLABUS_PROGRESS_SESSION_KEY] = session_progress
    request.session.modified = True
    return {
        'current_term_index': clamped_index,
        'current_term': terms[clamped_index],
        'total_terms': len(terms),
        'updated_at': None,
    }


def _clear_syllabus_progress(request, syllabus_key: str) -> None:
    account = _get_current_account(request)
    if account:
        SyllabusProgress.objects.filter(account=account, syllabus_key=syllabus_key).delete()
        return

    session_progress = request.session.get(SYLLABUS_PROGRESS_SESSION_KEY, {})
    if syllabus_key in session_progress:
        session_progress.pop(syllabus_key, None)
        request.session[SYLLABUS_PROGRESS_SESSION_KEY] = session_progress
        request.session.modified = True


def brain_quiz_question(request):
    seen_terms = request.session.get(BRAIN_QUIZ_SEEN_TERMS, [])
    available_terms = [term for term in QUIZ_TERMS if term not in seen_terms]

    if not available_terms:
        seen_terms = []
        available_terms = list(QUIZ_TERMS)

    try:
        payload = get_quiz_question_from_terms(available_terms)
    except LookupError:
        return JsonResponse({'error': 'Quiz content unavailable.'}, status=503)

    correct_answer = payload.get('correct_answer')
    if correct_answer:
        seen_terms.append(correct_answer)
        request.session[BRAIN_QUIZ_SEEN_TERMS] = seen_terms

    return JsonResponse(payload)


def brain_quiz_attempt_save(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed.'}, status=405)

    account = _get_current_account(request)
    if not account:
        return JsonResponse({'error': 'Authentication required.'}, status=401)

    try:
        payload = json.loads(request.body.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({'error': 'Invalid request body.'}, status=400)

    score = payload.get('score', 0)

    try:
        score = max(0, int(score))
    except (TypeError, ValueError):
        return JsonResponse({'error': 'Score must be an integer.'}, status=400)

    with transaction.atomic():
        latest_attempt_number = (
            BrainQuizAttempt.objects.select_for_update()
            .filter(username=account)
            .aggregate(max_attempt=Max('attempt_number'))['max_attempt']
            or 0
        )
        attempt = BrainQuizAttempt.objects.create(
            username=account,
            attempt_number=latest_attempt_number + 1,
            score=score,
        )

    return JsonResponse(
        {
            'saved': True,
            'username': account.username,
            'attempt_number': attempt.attempt_number,
            'score': attempt.score,
            'date_attempt': attempt.date_attempt.isoformat(),
        }
    )


def brain_quiz_leaderboard(request):
    leaderboard_rows = list(
        BrainQuizAttempt.objects.values('username__username')
        .annotate(
            best_score=Max('score'),
            total_attempts=Count('id'),
            last_attempt=Max('date_attempt'),
        )
        .order_by('-best_score', 'last_attempt', 'username__username')
    )

    top_rows = []
    current_account = _get_current_account(request)
    current_account_entry = None

    for index, row in enumerate(leaderboard_rows, start=1):
        entry = {
            'rank': index,
            'username': row['username__username'],
            'best_score': row['best_score'] or 0,
            'total_attempts': row['total_attempts'],
            'last_attempt': row['last_attempt'].isoformat() if row['last_attempt'] else None,
        }

        if index <= 10:
            top_rows.append(entry)

        if current_account and entry['username'] == current_account.username:
            current_account_entry = entry

    return JsonResponse(
        {
            'entries': top_rows,
            'total_players': len(leaderboard_rows),
            'updated_at': leaderboard_rows[0]['last_attempt'].isoformat() if leaderboard_rows and leaderboard_rows[0]['last_attempt'] else None,
            'current_account': current_account_entry,
        }
    )


def save_syllabus_progress(request, syllabus_key: str):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed.'}, status=405)

    if syllabus_key != LETTERS_AND_NUMBERS_SYLLABUS_KEY:
        return JsonResponse({'error': 'Unknown syllabus.'}, status=404)

    terms = _get_letters_and_numbers_terms()

    try:
        payload = json.loads(request.body.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({'error': 'Invalid request body.'}, status=400)

    if bool(payload.get('completed')):
        _clear_syllabus_progress(request, syllabus_key)
        return JsonResponse({'saved': True, 'completed': True})

    progress = _save_syllabus_progress(request, syllabus_key, terms, payload.get('current_term_index', 0))
    return JsonResponse({'saved': True, 'completed': False, 'progress': progress})


def learn_vocabularies(request):
    return render(
        request,
        'learn_vocabularies.html',
        {
            'active_page': 'vocabularies',
        },
    )


def syllabus_letters_and_numbers(request):
    syllabus_terms = _get_letters_and_numbers_terms()
    progress = _get_syllabus_progress(request, LETTERS_AND_NUMBERS_SYLLABUS_KEY, syllabus_terms)
    initial_term_index = progress['current_term_index'] if progress else 0

    return render(
        request,
        'syllabus_letters_and_numbers.html',
        {
            'active_page': 'brain',
            'is_syllabus': True,
            'page_title': 'Letters and Numbers',
            'page_description': 'Learn the core sign vocabulary for letters and numbers.',
            'cutscene_caption': 'Loading alphabet and number signs...',
            'lesson_term': syllabus_terms[initial_term_index],
            'initial_term_index': initial_term_index,
            'syllabus_progress': progress,
            'syllabus_terms': syllabus_terms,
        },
    )


def syllabus_greetings_and_personal(request):
    return render(
        request,
        'page.html',
        {
            'active_page': 'brain',
            'is_syllabus': True,
            'page_title': 'Greetings and Personal',
            'page_description': 'Practice signs for greetings and personal introductions.',
            'cutscene_caption': 'Preparing conversational starter signs...',
        },
    )


def syllabus_polite_phrases(request):
    return render(
        request,
        'page.html',
        {
            'active_page': 'brain',
            'is_syllabus': True,
            'page_title': 'Polite Phrases',
            'page_description': 'Review common polite expressions used in daily conversations.',
            'cutscene_caption': 'Calibrating courtesy expressions...',
        },
    )


def syllabus_daily_life(request):
    return render(
        request,
        'page.html',
        {
            'active_page': 'brain',
            'is_syllabus': True,
            'page_title': 'Daily Life',
            'page_description': 'Explore practical signs used in routine day-to-day activities.',
            'cutscene_caption': 'Loading daily routine sign missions...',
        },
    )


def syllabus_basic_adjectives(request):
    return render(
        request,
        'page.html',
        {
            'active_page': 'brain',
            'is_syllabus': True,
            'page_title': 'Basic Adjectives',
            'page_description': 'Study beginner adjective signs for common descriptions.',
            'cutscene_caption': 'Generating descriptive sign challenges...',
        },
    )


def about_me(request):
    return render(
        request,
        'page.html',
        {
            'active_page': 'about',
            'page_title': 'About Me',
            'page_description': 'Profile + story soon.',
        },
    )