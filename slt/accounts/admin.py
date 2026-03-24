from django.contrib import admin

from .models import Account


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ('username', 'real_name', 'email', 'date_created', 'last_accessed')
    search_fields = ('username', 'real_name', 'email')