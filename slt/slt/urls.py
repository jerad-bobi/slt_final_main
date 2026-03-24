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
from .views import home, learn_vocabularies, lets_practice, sharpen_your_brain
from .views import signasl_lookup

urlpatterns = [
    path('', home, name='home'),
    path('sharpen-your-brain/', sharpen_your_brain, name='sharpen_your_brain'),
    path('lets-practice/', lets_practice, name='lets_practice'),
    path('api/signasl-lookup/', signasl_lookup, name='signasl_lookup'),
    path('learn-vocabularies/', learn_vocabularies, name='learn_vocabularies'),
    path('account/', account_access, name='account_access'),
    path('register/', register_view, name='register'),
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    path('about-me/', about_me, name='about_me'),
    path('admin/', admin.site.urls),
]
