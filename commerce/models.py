"""Заказ хранит историю покупки, независимую от будущих изменений каталога."""

import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models


class Order(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "Новый"
        PROCESSING = "processing", "В обработке"
        SHIPPED = "shipped", "Отправлен"

    # Ссылка уважает выбранную AUTH_USER_MODEL. Собственного User лучше выбирать
    # до первых миграций: замена модели в заполненном проекте требует отдельного плана.
    # PROTECT не позволит случайно удалить владельца вместе с историей заказов.
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders"
    )
    address = models.TextField("Адрес доставки", max_length=500)
    status = models.CharField("Статус", max_length=20, choices=Status.choices, default=Status.NEW)
    total = models.DecimalField("Итого", max_digits=14, decimal_places=2, default=Decimal("0.00"))
    # UNIQUE в самой БД — последняя защита от двух одинаковых POST одновременно.
    idempotency_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField("Создан", auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "заказ"
        verbose_name_plural = "заказы"
        indexes = [models.Index(fields=["owner", "-created_at"], name="order_owner_created_idx")]
        constraints = [models.CheckConstraint(condition=models.Q(total__gte=0), name="order_total_nonnegative")]

    def __str__(self):
        return f"Заказ №{self.pk}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    # Удаление SKU не уничтожает историю. В UI заказа используем именно снимки ниже.
    sku = models.ForeignKey("main.ProductSize", on_delete=models.SET_NULL, null=True, blank=True)
    product_name = models.CharField("Название при покупке", max_length=100)
    size_name = models.CharField("Размер при покупке", max_length=20)
    unit_price = models.DecimalField("Цена при покупке", max_digits=10, decimal_places=2)
    quantity = models.PositiveSmallIntegerField("Количество")

    class Meta:
        ordering = ["pk"]
        verbose_name = "позиция заказа"
        verbose_name_plural = "позиции заказа"
        constraints = [
            models.CheckConstraint(condition=models.Q(quantity__gte=1), name="orderitem_quantity_positive"),
            models.CheckConstraint(condition=models.Q(unit_price__gte=0), name="orderitem_price_nonnegative"),
        ]

    @property
    def line_total(self):
        # Decimal, а не float: 0.1 + 0.2 должно быть ровно 0.3 при денежных расчётах.
        return self.unit_price * self.quantity

    def __str__(self):
        return f"{self.product_name} / {self.size_name} × {self.quantity}"
