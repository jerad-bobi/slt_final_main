import json
import re
from base64 import b64decode
from binascii import Error as BinasciiError

from django.db import transaction
from django.db.models import Count, Max
from django.http import JsonResponse
from django.shortcuts import render

from accounts.models import Account, BrainQuizAttempt, SkeletalSignSample

from .skeletal_classifier_service import normalize_landmarks, predict_sign_from_landmarks
from .signasl_service import QUIZ_TERMS, get_quiz_question_from_terms, lookup_text


BRAIN_QUIZ_SEEN_TERMS = 'brain_quiz_seen_terms'
SESSION_ACCOUNT_ID = 'account_id'
SKELETAL_CAPTURE_MAX_BYTES = 5 * 1024 * 1024


def _normalize_sign_folder_name(raw_name: str) -> str:
    cleaned = re.sub(r'[^A-Za-z0-9 _-]', '', raw_name).strip()
    cleaned = re.sub(r'\s+', '_', cleaned)
    return cleaned[:64]


def home(request):
    return render(request, 'home.html', {'active_page': 'home'})


def sharpen_your_brain(request):
    return render(
        request,
        'sharpen_your_brain.html',
        {
            'active_page': 'brain',
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


def learn_vocabularies(request):
    return render(
        request,
        'learn_vocabularies.html',
        {
            'active_page': 'vocabularies',
        },
    )


def syllabus_letters_and_numbers(request):
    return render(
        request,
        'page.html',
        {
            'active_page': 'brain',
            'is_syllabus': True,
            'page_title': 'Letters and Numbers',
            'page_description': 'Learn the core sign vocabulary for letters and numbers.',
            'cutscene_caption': 'Loading alphabet and number signs...',
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