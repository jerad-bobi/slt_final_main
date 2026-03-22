from django.http import JsonResponse
from django.shortcuts import render

from .signasl_service import lookup_text


def home(request):
    return render(request, 'home.html', {'active_page': 'home'})


def sharpen_your_brain(request):
    return render(
        request,
        'page.html',
        {
            'active_page': 'brain',
            'page_title': 'Sharpen Your Brain',
            'page_description': 'Brain drills soon.',
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