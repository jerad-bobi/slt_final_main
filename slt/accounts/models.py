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


class BrainQuizAttempt(models.Model):
    username = models.ForeignKey(
        Account,
        to_field='username',
        db_column='username',
        on_delete=models.CASCADE,
        related_name='brain_quiz_attempts',
    )
    attempt_number = models.PositiveIntegerField()
    score = models.PositiveIntegerField(default=0)
    date_attempt = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'brain_quiz_attempt'
        ordering = ['-date_attempt']
        constraints = [
            models.UniqueConstraint(fields=['username', 'attempt_number'], name='unique_brain_attempt_per_user'),
        ]

    def __str__(self) -> str:
        return f'{self.username_id} attempt {self.attempt_number}'


class SkeletalSignSample(models.Model):
    sign_name = models.CharField(max_length=64)
    sign_folder = models.CharField(max_length=64)
    filename = models.CharField(max_length=255, blank=True)
    image_png = models.BinaryField()
    feature_vector = models.JSONField()
    source = models.CharField(max_length=32, default='capture')
    captured_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'skeletal_sign_sample'
        ordering = ['-captured_at']

    def __str__(self) -> str:
        return f'{self.sign_folder} sample {self.id}'