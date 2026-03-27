"""
Enterprise auth forms: signup with validation and security best practices.
"""
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError

User = get_user_model()


class SignUpForm(UserCreationForm):
    """
    Registration form: username, optional email, password with confirmation.
    Enterprise: no PII in error messages; use Django's built-in validators.
    """

    email = forms.EmailField(
        required=False,
        label="Email (optional)",
        widget=forms.EmailInput(attrs={
            "autocomplete": "email",
            "placeholder": "you@company.com",
        }),
    )

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update({
            "autocomplete": "username",
            "placeholder": "Choose a username",
        })
        self.fields["password1"].widget.attrs.update({
            "autocomplete": "new-password",
            "placeholder": "Min. 8 characters",
        })
        self.fields["password2"].widget.attrs.update({
            "autocomplete": "new-password",
            "placeholder": "Confirm password",
        })
        # Optional: add help text for password requirements
        if "password1" in self.fields:
            self.fields["password1"].help_text = None  # Remove default Django help text if desired
        if "password2" in self.fields:
            self.fields["password2"].help_text = None

    def clean_username(self):
        username = self.cleaned_data.get("username")
        if username and len(username) < 3:
            raise ValidationError("Username must be at least 3 characters.")
        return username
