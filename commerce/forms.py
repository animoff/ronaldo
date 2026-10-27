"""Формы — граница между недоверенным HTTP-вводом и Python-значениями."""

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model


class QuantityForm(forms.Form):
    quantity = forms.IntegerField(label="Количество", min_value=1, max_value=99, initial=1)


class CartUpdateForm(forms.Form):
    quantity = forms.IntegerField(label="Количество", min_value=0, max_value=99)


class CheckoutForm(forms.Form):
    address = forms.CharField(
        label="Адрес доставки", min_length=10, max_length=500,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Город, улица, дом, квартира"}),
        help_text="Учебный заказ: настоящих оплаты и доставки здесь нет. Используйте вымышленный адрес.",
    )
    idempotency_key = forms.UUIDField(widget=forms.HiddenInput)


class RegistrationForm(UserCreationForm):
    email = forms.EmailField(label="Email (необязательно)", required=False)

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ("username", "email")
