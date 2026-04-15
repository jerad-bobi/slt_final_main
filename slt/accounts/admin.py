from django.contrib import admin

from .models import Account, SearchHistory


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ('username', 'real_name', 'email', 'date_created', 'last_accessed')
    search_fields = ('username', 'real_name', 'email')


@admin.register(SearchHistory)
class SearchHistoryAdmin(admin.ModelAdmin):
    list_display = ('account', 'search_term', 'searched_at')
    list_filter = ('searched_at',)
    search_fields = ('account__username', 'search_term')
    readonly_fields = ('searched_at',)