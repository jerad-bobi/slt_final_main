from django import forms
from django.contrib.auth.password_validation import validate_password

from .models import Account


class RegisterForm(forms.ModelForm):
    confirm_password = forms.CharField(widget=forms.PasswordInput)
    password = forms.CharField(widget=forms.PasswordInput)

    class Meta:
        model = Account
        fields = ['real_name', 'username', 'email', 'password']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'auth-input'})

    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        if Account.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError('Username already used.')
        return username

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if Account.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('Email already used.')
        return email

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')

        if password and confirm_password and password != confirm_password:
            self.add_error('confirm_password', 'Passwords do not match.')

        if password and not self.errors.get('password'):
            try:
                validate_password(password)
            except forms.ValidationError as error:
                self.add_error('password', error)

        return cleaned_data


class LoginForm(forms.Form):
    username = forms.CharField(max_length=150)
    password = forms.CharField(widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'auth-input'})


class ForgotPasswordForm(forms.Form):
    username = forms.CharField(max_length=150)
    new_password = forms.CharField(widget=forms.PasswordInput)
    confirm_password = forms.CharField(widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'auth-input'})

    def clean(self):
        cleaned_data = super().clean()
        new_password = cleaned_data.get('new_password')
        confirm_password = cleaned_data.get('confirm_password')

        if new_password and confirm_password and new_password != confirm_password:
            self.add_error('confirm_password', 'Passwords do not match.')

        if new_password and not self.errors.get('new_password'):
            try:
                validate_password(new_password)
            except forms.ValidationError as error:
                self.add_error('new_password', error)

        return cleaned_data