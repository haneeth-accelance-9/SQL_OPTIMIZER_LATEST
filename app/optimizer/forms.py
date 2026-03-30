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


class UserProfileForm(forms.ModelForm):
    """Editable profile form combining auth user fields with profile metadata."""

    first_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "First name", "autocomplete": "given-name"}),
    )
    last_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Last name", "autocomplete": "family-name"}),
    )
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={"placeholder": "you@company.com", "autocomplete": "email"}),
    )

    class Meta:
        model = UserProfile
        fields = ("first_name", "last_name", "email", "team_name", "image_url")
        widgets = {
            "team_name": forms.TextInput(attrs={"placeholder": "Your team or department"}),
            "image_url": forms.URLInput(attrs={"placeholder": "https://example.com/profile-image.jpg"}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user")
        super().__init__(*args, **kwargs)
        self.fields["first_name"].initial = self.user.first_name
        self.fields["last_name"].initial = self.user.last_name
        self.fields["email"].initial = self.user.email
        for field in self.fields.values():
            field.widget.attrs.setdefault(
                "class",
                "mt-1 block w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 shadow-sm focus:border-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-200",
            )

    def save(self, commit=True):
        profile = super().save(commit=False)
        self.user.first_name = self.cleaned_data.get("first_name", "")
        self.user.last_name = self.cleaned_data.get("last_name", "")
        self.user.email = self.cleaned_data.get("email", "")
        if commit:
            self.user.save(update_fields=["first_name", "last_name", "email"])
            profile.user = self.user
            profile.save()
        return profile
