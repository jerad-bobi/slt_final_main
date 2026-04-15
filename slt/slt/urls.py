"""
URL configuration for slt project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path

from accounts.views import about_me, account_access, login_view, logout_view, register_view
from .views import (
    brain_quiz_attempt_save,
    brain_quiz_leaderboard,
    brain_quiz_question,
    home,
    learn_vocabularies,
    lets_practice,
    predict_skeletal_sign,
    save_skeletal_hand_capture,
    save_syllabus_progress,
    sharpen_your_brain,
    syllabus_basic_adjectives,
    syllabus_daily_life,
    syllabus_greetings_and_personal,
    syllabus_letters_and_numbers,
    syllabus_polite_phrases,
)
from .views import signasl_lookup

urlpatterns = [
    path('', home, name='home'),
    path('sharpen-your-brain/', sharpen_your_brain, name='sharpen_your_brain'),
    path('lets-practice/', lets_practice, name='lets_practice'),
    path('api/signasl-lookup/', signasl_lookup, name='signasl_lookup'),
    path('api/save-skeletal-hand-capture/', save_skeletal_hand_capture, name='save_skeletal_hand_capture'),
    path('api/predict-skeletal-sign/', predict_skeletal_sign, name='predict_skeletal_sign'),
    path('api/brain-quiz-question/', brain_quiz_question, name='brain_quiz_question'),
    path('api/brain-quiz-attempt-save/', brain_quiz_attempt_save, name='brain_quiz_attempt_save'),
    path('api/brain-quiz-leaderboard/', brain_quiz_leaderboard, name='brain_quiz_leaderboard'),
    path('api/syllabus-progress/<slug:syllabus_key>/', save_syllabus_progress, name='save_syllabus_progress'),
    path('learn-vocabularies/', learn_vocabularies, name='learn_vocabularies'),
    path('syllabus/letters-and-numbers/', syllabus_letters_and_numbers, name='syllabus_letters_and_numbers'),
    path('syllabus/greetings-and-personal/', syllabus_greetings_and_personal, name='syllabus_greetings_and_personal'),
    path('syllabus/polite-phrases/', syllabus_polite_phrases, name='syllabus_polite_phrases'),
    path('syllabus/daily-life/', syllabus_daily_life, name='syllabus_daily_life'),
    path('syllabus/basic-adjectives/', syllabus_basic_adjectives, name='syllabus_basic_adjectives'),
    path('account/', account_access, name='account_access'),
    path('register/', register_view, name='register'),
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    path('about-me/', about_me, name='about_me'),
    path('admin/', admin.site.urls),
]
