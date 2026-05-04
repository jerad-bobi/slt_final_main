import time

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.db.models import Max
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from .forms import ForgotPasswordForm, LoginForm, RegisterForm
from .models import Account, BrainQuizAttempt


SESSION_ACCOUNT_ID = 'account_id'

SCORE_FILTERS = {
    'newest': {
        'label': 'Newest first',
        'ordering': ('-date_attempt', '-attempt_number'),
    },
    'oldest': {
        'label': 'Oldest first',
        'ordering': ('date_attempt', 'attempt_number'),
    },
    'highest': {
        'label': 'Highest score',
        'ordering': ('-score', '-date_attempt', '-attempt_number'),
    },
    'lowest': {
        'label': 'Lowest score',
        'ordering': ('score', '-date_attempt', '-attempt_number'),
    },
}


def _get_client_ip(request: HttpRequest) -> str:
    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()[:128]

    return request.META.get('REMOTE_ADDR', 'unknown')[:128]


def _get_login_cache_key(prefix: str, username: str, client_ip: str) -> str:
    normalized_username = username.strip().lower() or 'unknown'
    normalized_ip = client_ip.strip().lower() or 'unknown'
    return f'accounts:{prefix}:{normalized_ip}:{normalized_username}'


def _format_lockout_message(remaining_seconds: int) -> str:
    if remaining_seconds >= 60:
        remaining_minutes = max(1, (remaining_seconds + 59) // 60)
        return f'Too many login attempts. Try again in about {remaining_minutes} minute(s).'
    return f'Too many login attempts. Try again in {remaining_seconds} second(s).'


def _get_login_lockout_seconds(username: str, client_ip: str) -> int:
    lock_key = _get_login_cache_key('login_lock', username, client_ip)
    locked_until = cache.get(lock_key)
    if not locked_until:
        return 0

    remaining_seconds = max(0, int(locked_until - time.time()))
    if remaining_seconds <= 0:
        cache.delete(lock_key)
        return 0

    return remaining_seconds


def _record_failed_login(username: str, client_ip: str) -> None:
    failures_key = _get_login_cache_key('login_failures', username, client_ip)
    lock_key = _get_login_cache_key('login_lock', username, client_ip)
    lockout_seconds = max(1, settings.LOGIN_LOCKOUT_SECONDS)
    max_attempts = max(1, settings.LOGIN_MAX_ATTEMPTS)

    failed_attempts = cache.get(failures_key, 0) + 1
    cache.set(failures_key, failed_attempts, timeout=lockout_seconds)

    if failed_attempts >= max_attempts:
        cache.set(lock_key, time.time() + lockout_seconds, timeout=lockout_seconds)
        cache.delete(failures_key)


def _clear_failed_login_state(username: str, client_ip: str) -> None:
    cache.delete_many(
        [
            _get_login_cache_key('login_failures', username, client_ip),
            _get_login_cache_key('login_lock', username, client_ip),
        ]
    )


def _get_current_account(request: HttpRequest) -> Account | None:
    account_id = request.session.get(SESSION_ACCOUNT_ID)
    if not account_id:
        return None

    try:
        return Account.objects.get(id=account_id)
    except Account.DoesNotExist:
        request.session.pop(SESSION_ACCOUNT_ID, None)
        return None


def _touch_account(account: Account) -> None:
    account.last_accessed = timezone.now()
    account.save(update_fields=['last_accessed'])


def account_access(request: HttpRequest) -> HttpResponse:
    account = _get_current_account(request)
    if account:
        _touch_account(account)
        return redirect('about_me')

    return render(
        request,
        'account_access.html',
        {
            'active_page': 'about',
        },
    )


def register_view(request: HttpRequest) -> HttpResponse:
    account = _get_current_account(request)
    if account:
        _touch_account(account)
        return redirect('about_me')

    form = RegisterForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        new_account = form.save(commit=False)
        new_account.password = make_password(form.cleaned_data['password'])
        new_account.last_accessed = timezone.now()
        new_account.save()
        request.session.cycle_key()
        request.session[SESSION_ACCOUNT_ID] = new_account.id
        return redirect('about_me')

    return render(
        request,
        'register.html',
        {
            'active_page': 'about',
            'form': form,
        },
    )


def login_view(request: HttpRequest) -> HttpResponse:
    account = _get_current_account(request)
    if account:
        _touch_account(account)
        return redirect('about_me')

    form = LoginForm(request.POST or None)
    login_error = None

    if request.method == 'POST' and form.is_valid():
        username = form.cleaned_data['username'].strip()
        password = form.cleaned_data['password']
        client_ip = _get_client_ip(request)
        lockout_seconds = _get_login_lockout_seconds(username, client_ip)

        if lockout_seconds:
            login_error = _format_lockout_message(lockout_seconds)
            return render(
                request,
                'login.html',
                {
                    'active_page': 'about',
                    'form': form,
                    'login_error': login_error,
                },
            )

        try:
            account = Account.objects.get(username__iexact=username)
        except Account.DoesNotExist:
            account = None

        if not account or not check_password(password, account.password):
            _record_failed_login(username, client_ip)
            login_error = 'Invalid username or password.'
        else:
            _clear_failed_login_state(username, client_ip)
            _touch_account(account)
            request.session.cycle_key()
            request.session[SESSION_ACCOUNT_ID] = account.id
            return redirect('about_me')

    return render(
        request,
        'login.html',
        {
            'active_page': 'about',
            'form': form,
            'login_error': login_error,
        },
    )


def logout_view(request: HttpRequest) -> HttpResponse:
    request.session.flush()
    return redirect('account_access')


def forgot_password_view(request: HttpRequest) -> HttpResponse:
    form = ForgotPasswordForm(request.POST or None)
    forgot_password_message = None
    forgot_password_error = None

    if request.method == 'POST' and form.is_valid():
        username = form.cleaned_data['username'].strip()
        new_password = form.cleaned_data['new_password']

        try:
            account = Account.objects.get(username__iexact=username)
            account.password = make_password(new_password)
            account.save(update_fields=['password'])
            forgot_password_message = 'Password updated successfully! You can now login with your new password.'
            form = ForgotPasswordForm()
        except Account.DoesNotExist:
            forgot_password_error = 'Username not found.'

    return render(
        request,
        'forgot_password.html',
        {
            'active_page': 'about',
            'form': form,
            'forgot_password_message': forgot_password_message,
            'forgot_password_error': forgot_password_error,
        },
    )


def about_me(request: HttpRequest) -> HttpResponse:
    account = _get_current_account(request)
    if not account:
        return redirect('account_access')

    _touch_account(account)
    attempts_queryset = account.brain_quiz_attempts.all()
    selected_score_filter = request.GET.get('score_filter', 'newest').strip().lower()
    if selected_score_filter not in SCORE_FILTERS:
        selected_score_filter = 'newest'

    selected_filter = SCORE_FILTERS[selected_score_filter]
    attempts = list(attempts_queryset.order_by(*selected_filter['ordering']))
    best_score = attempts_queryset.aggregate(best_score=Max('score'))['best_score']
    filter_options = [
        {
            'value': key,
            'label': config['label'],
        }
        for key, config in SCORE_FILTERS.items()
    ]

    return render(
        request,
        'profile.html',
        {
            'active_page': 'about',
            'account': account,
            'quiz_attempts': attempts,
            'quiz_attempt_count': attempts_queryset.count(),
            'best_score': best_score,
            'selected_score_filter': selected_score_filter,
            'selected_score_filter_label': selected_filter['label'],
            'score_filter_options': filter_options,
        },
    )