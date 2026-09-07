from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django import forms

from .models import UserProfilePreference


class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")


class PreferenceForm(forms.ModelForm):
    class Meta:
        model = UserProfilePreference
        fields = ["preferred_regions", "keywords", "email_digest_enabled"]
        widgets = {
            "preferred_regions": forms.TextInput(
                attrs={"class": "input-field", "placeholder": "e.g. Europe, UK, Remote"}
            ),
            "keywords": forms.TextInput(
                attrs={"class": "input-field", "placeholder": "e.g. quant, machine learning"}
            ),
        }
