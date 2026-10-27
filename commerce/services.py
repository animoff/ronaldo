"""Бизнес-операция оформления. Её можно вызвать из HTML, API или команды.

HTTP-view отвечает за права и формы, сервис — за целостность покупки.
Сеть, отправка писем и платежи не должны выполняться внутри этой транзакции.
Для них в реальном сервисе понадобятся outbox и идемпотентный обработчик.
"""

from decimal import Decimal

from django.db import transaction
from django.db.models import F

from main.models import ProductSize
from .models import Order, OrderItem
from .validation import valid_sku_key


class CheckoutError(ValueError):
    """Ожидаемая ошибка предметной области, которую можно показать пользователю."""


@transaction.atomic
def place_order(*, owner, quantities, address, idempotency_key):
    if not owner.is_authenticated:
        raise CheckoutError("Войдите в аккаунт перед оформлением заказа.")
    if not isinstance(quantities, dict) or not quantities:
        raise CheckoutError("Корзина пуста.")
    if any(not valid_sku_key(key) or not isinstance(value, int) or isinstance(value, bool)
           or not 1 <= value <= 99 for key, value in quantities.items()):
        raise CheckoutError("Некорректное количество товара.")

    # На PostgreSQL конкурентная вставка того же unique-ключа дождётся первой
    # транзакции. get_or_create затем вернёт уже готовый заказ, не списывая склад снова.
    order, created = Order.objects.get_or_create(
        idempotency_key=idempotency_key, defaults={"owner": owner, "address": address}
    )
    if not created:
        if order.owner_id != owner.pk:
            raise CheckoutError("Этот ключ оформления принадлежит другому пользователю.")
        return order

    # Один порядок блокировок уменьшает риск deadlock при двух корзинах с общими SKU.
    # of=("self",) блокирует только SKU, а не общую строку размера или товара.
    # Цена фиксируется такой, какой она была при чтении запроса оформления.
    # SQLite select_for_update не поддерживает: для параллельных покупок используйте
    # PostgreSQL. Условный UPDATE ниже защищает остаток от ухода в минус в обеих БД.
    skus = list(ProductSize.objects.select_for_update(of=("self",)).filter(
        pk__in=quantities, product__is_active=True
    ).select_related("product", "size").order_by("pk"))
    if len(skus) != len(quantities):
        raise CheckoutError("Один из товаров больше недоступен. Обновите корзину.")

    total = Decimal("0.00")
    items = []
    for sku in skus:
        quantity = quantities[str(sku.pk)]
        # F выполняет арифметику в SQL, а WHERE stock >= quantity гарантирует,
        # что между чтением и записью мы не продадим отсутствующий остаток.
        updated = ProductSize.objects.filter(pk=sku.pk, stock__gte=quantity).update(stock=F("stock") - quantity)
        if updated != 1:
            raise CheckoutError(f"Недостаточно товара: {sku.product.name}, размер {sku.size.name}.")
        items.append(OrderItem(order=order, sku=sku, product_name=sku.product.name,
                               size_name=sku.size.name, unit_price=sku.product.price, quantity=quantity))
        total += sku.product.price * quantity

    OrderItem.objects.bulk_create(items)
    order.total = total
    order.save(update_fields=["total"])
    # Любое исключение выше откатывает всё: и заказ, и позиции, и списание склада.
    return order
