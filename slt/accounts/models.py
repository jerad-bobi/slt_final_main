from django.db import models
from django.utils import timezone


class Account(models.Model):
    real_name = models.CharField(max_length=150)
    username = models.CharField(max_length=150, unique=True)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=128)
    verification = models.BooleanField(default=False)
    date_created = models.DateTimeField(auto_now_add=True)
    last_accessed = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'user_account'
        ordering = ['username']

    def __str__(self) -> str:
        return self.username