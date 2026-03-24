from django import forms

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

        return cleaned_data


class LoginForm(forms.Form):
    username = forms.CharField(max_length=150)
    password = forms.CharField(widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'auth-input'})