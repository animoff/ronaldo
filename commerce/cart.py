"""В сессии храним только ID SKU и количество. Цены всегда берём из БД."""

from decimal import Decimal

from main.models import ProductSize
from .validation import valid_sku_key

CART_SESSION_KEY = "cart"
MAX_QUANTITY = 99


class Cart:
    def __init__(self, request):
        self.session = request.session
        raw = self.session.get(CART_SESSION_KEY, {})
        # Даже серверные данные проверяем: формат мог измениться между релизами.
        self.quantities = {
            str(key): value for key, value in raw.items()
            if valid_sku_key(key) and isinstance(value, int) and not isinstance(value, bool)
            and 1 <= value <= MAX_QUANTITY
        } if isinstance(raw, dict) else {}
        if self.quantities != raw:
            self.save()

    def save(self):
        # Присваивание сообщает Django, что сессия изменилась. Изменение вложенного
        # dict без присваивания или session.modified = True может не сохраниться.
        self.session[CART_SESSION_KEY] = self.quantities.copy()

    def add(self, sku, quantity):
        self.set(sku, self.quantities.get(str(sku.pk), 0) + quantity)

    def set(self, sku, quantity):
        if not 0 <= quantity <= MAX_QUANTITY:
            raise ValueError(f"В корзине может быть от 0 до {MAX_QUANTITY} единиц одной позиции.")
        if quantity > sku.stock:
            raise ValueError(f"На складе осталось {sku.stock} шт. для {sku.product.name} ({sku.size.name}).")
        if quantity == 0:
            self.quantities.pop(str(sku.pk), None)
        else:
            self.quantities[str(sku.pk)] = quantity
        self.save()

    def lines(self):
        # JOIN заменяет запросы к product и size в каждой итерации (проблема N+1).
        skus = ProductSize.objects.filter(
            pk__in=self.quantities, product__is_active=True
        ).select_related("product", "size").order_by("pk")
        result = []
        present = set()
        for sku in skus:
            present.add(str(sku.pk))
            quantity = self.quantities[str(sku.pk)]
            result.append({"sku": sku, "product": sku.product, "quantity": quantity,
                           "unit_price": sku.product.price, "line_total": sku.product.price * quantity})
        # Удалённый или скрытый товар больше нельзя заказать; очищаем устаревшие ID.
        if present != set(self.quantities):
            self.quantities = {key: value for key, value in self.quantities.items() if key in present}
            self.save()
        return result

    def context(self):
        lines = self.lines()
        return {"lines": lines, "total": sum((line["line_total"] for line in lines), Decimal("0.00"))}

    def clear(self):
        self.quantities = {}
        self.save()
