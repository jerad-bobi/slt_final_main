import json

from django.db import transaction
from django.db.models import Count, Max
from django.http import JsonResponse
from django.shortcuts import render

from accounts.models import Account, BrainQuizAttempt

from .signasl_service import QUIZ_TERMS, get_quiz_question_from_terms, lookup_text


BRAIN_QUIZ_SEEN_TERMS = 'brain_quiz_seen_terms'
SESSION_ACCOUNT_ID = 'account_id'


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