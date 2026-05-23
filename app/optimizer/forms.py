"""
Enterprise auth forms: signup with validation and security best practices.
"""
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError

from optimizer.models import UserProfile

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


class UserProfileForm(forms.Form):
    """Profile form: update email and optionally change password."""

    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={"placeholder": "you@company.com", "autocomplete": "email"}),
    )
    password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={
            "placeholder": "Leave blank to keep current password",
            "autocomplete": "new-password",
        }),
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user")
        self.instance = kwargs.pop("instance", None)
        super().__init__(*args, **kwargs)
        self.fields["email"].initial = self.user.email
        css = (
            "mt-1 block w-full rounded-xl border border-slate-200 bg-white px-4 py-3 "
            "text-sm text-slate-700 shadow-sm focus:border-sky-500 focus:outline-none "
            "focus:ring-2 focus:ring-sky-200"
        )
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", css)

    def clean_password(self):
        password = self.cleaned_data.get("password")
        if password:
            if len(password) < 10:
                raise ValidationError("Password must be at least 10 characters.")
            if not any(c.isalpha() for c in password):
                raise ValidationError("Password must contain at least one letter.")
            if not any(c.isdigit() for c in password):
                raise ValidationError("Password must contain at least one number.")
        return password

    def save(self):
        self.user.email = self.cleaned_data.get("email", "")
        password = self.cleaned_data.get("password")
        if password:
            self.user.set_password(password)
            self.user.save(update_fields=["email", "password"])
        else:
            self.user.save(update_fields=["email"])
        return self.instance
