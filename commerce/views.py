"""Тонкие HTTP-обработчики: проверяют ввод/права, вызывают сервис, выбирают ответ."""

import uuid

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from main.models import ProductSize
from .cart import Cart
from .forms import CartUpdateForm, CheckoutForm, QuantityForm, RegistrationForm
from .models import Order
from .services import CheckoutError, place_order


@require_GET
def cart(request):
    return render(request, "commerce/cart.html", Cart(request).context())


@require_POST
def cart_add(request, sku_id):
    sku = get_object_or_404(ProductSize.objects.select_related("product", "size"),
                            pk=sku_id, product__is_active=True)
    form = QuantityForm(request.POST)
    if form.is_valid():
        try:
            Cart(request).add(sku, form.cleaned_data["quantity"])
            messages.success(request, "Товар добавлен в корзину.")
        except ValueError as exc:
            messages.error(request, str(exc))
    else:
        messages.error(request, "Укажите целое количество от 1 до 99.")
    # Post/Redirect/Get: обновление страницы не отправит форму второй раз.
    return redirect("commerce:cart")


@require_POST
def cart_update(request, sku_id):
    sku = get_object_or_404(ProductSize.objects.select_related("product", "size"), pk=sku_id)
    form = CartUpdateForm(request.POST)
    if form.is_valid():
        try:
            if not sku.product.is_active and form.cleaned_data["quantity"]:
                raise ValueError("Этот товар больше недоступен.")
            Cart(request).set(sku, form.cleaned_data["quantity"])
        except ValueError as exc:
            messages.error(request, str(exc))
    else:
        messages.error(request, "Укажите целое количество от 0 до 99.")
    return redirect("commerce:cart")


@login_required
@require_http_methods(["GET", "POST"])
def checkout(request):
    basket = Cart(request)
    context = basket.context()
    attempts = request.session.get("checkout_attempts", {})
    if request.method == "POST":
        form = CheckoutForm(request.POST)
        if form.is_valid():
            key = str(form.cleaned_data["idempotency_key"])
            attempt = attempts.get(key)
            if not attempt or attempt["owner_id"] != request.user.pk:
                form.add_error(None, "Форма устарела. Откройте оформление заново.")
            else:
                previous = Order.objects.filter(idempotency_key=key, owner=request.user).first()
                if previous:
                    # Повтор после успешного POST работает даже с уже пустой корзиной.
                    return redirect("commerce:order_detail", pk=previous.pk)
                if attempt["quantities"] != basket.quantities:
                    form.add_error(None, "Корзина изменилась. Откройте оформление заново.")
                else:
                    try:
                        order = place_order(owner=request.user, quantities=basket.quantities,
                                            address=form.cleaned_data["address"], idempotency_key=key)
                    except CheckoutError as exc:
                        form.add_error(None, str(exc))
                    else:
                        basket.clear()
                        messages.success(request, "Учебный заказ создан. Оплата не списывалась.")
                        return redirect("commerce:order_detail", pk=order.pk)
        # Ошибки возвращаем со статусом 400, не прячем их за успешным 200.
        return render(request, "commerce/checkout.html", {**context, "form": form}, status=400)

    if not context["lines"]:
        messages.info(request, "Сначала добавьте товар в корзину.")
        return redirect("commerce:cart")
    key = str(uuid.uuid4())
    # Несколько вкладок допустимы, но сессия не должна расти без ограничения.
    attempts = dict(list(attempts.items())[-4:])
    attempts[key] = {"owner_id": request.user.pk, "quantities": basket.quantities.copy()}
    request.session["checkout_attempts"] = attempts
    return render(request, "commerce/checkout.html", {**context, "form": CheckoutForm(initial={"idempotency_key": key})})


@login_required
@require_GET
def order_list(request):
    orders = Order.objects.filter(owner=request.user)
    page = Paginator(orders, 10).get_page(request.GET.get("page"))
    return render(request, "commerce/order_list.html", {"orders": page})


@login_required
@require_GET
def order_detail(request, pk):
    # ID из URL не даёт права читать чужой объект! Фильтруем по владельцу в БД.
    # 404 также не подтверждает постороннему существование конкретного заказа.
    order = get_object_or_404(Order.objects.filter(owner=request.user).prefetch_related("items"), pk=pk)
    return render(request, "commerce/order_detail.html", {"order": order})


@require_http_methods(["GET", "POST"])
def register(request):
    if request.user.is_authenticated:
        return redirect("main:home")
    form = RegistrationForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        user = form.save()  # UserCreationForm хеширует пароль; сырой пароль в БД не записывается.
        login(request, user)
        messages.success(request, "Аккаунт создан. Добро пожаловать!")
        return redirect("main:product_list")
    return render(request, "registration/register.html", {"form": form})
