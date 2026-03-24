from django.contrib.auth.hashers import check_password, make_password
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from .forms import LoginForm, RegisterForm
from .models import Account


SESSION_ACCOUNT_ID = 'account_id'


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

        try:
            account = Account.objects.get(username__iexact=username)
        except Account.DoesNotExist:
            account = None

        if not account or not check_password(password, account.password):
            login_error = 'Invalid username or password.'
        else:
            _touch_account(account)
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
    request.session.pop(SESSION_ACCOUNT_ID, None)
    return redirect('account_access')


def about_me(request: HttpRequest) -> HttpResponse:
    account = _get_current_account(request)
    if not account:
        return redirect('account_access')

    _touch_account(account)
    return render(
        request,
        'profile.html',
        {
            'active_page': 'about',
            'account': account,
        },
    )