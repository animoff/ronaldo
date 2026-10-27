"""Каталог: Python-классы описывают таблицы, связи и ограничения данных.

Модель — не словарь: Django сохраняет её экземпляры через ORM, а миграции
меняют схему БД. Валидация формы помогает пользователю исправить ввод;
ограничения БД защищают данные также при импорте и конкурентных запросах.
"""

from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils.text import slugify


class Category(models.Model):
    name = models.CharField("название", max_length=100)
    # unique создаёт ограничение UNIQUE и индекс для поиска по адресу страницы.
    slug = models.SlugField("адрес", max_length=100, unique=True, allow_unicode=True)

    class Meta:
        ordering = ["name", "pk"]
        verbose_name = "категория"
        verbose_name_plural = "категории"

    def save(self, *args, **kwargs):
        if not self.slug:
            # allow_unicode оставляет кириллицу; в URL используем <str:slug>.
            self.slug = slugify(self.name, allow_unicode=True)
        # Одинаковые slug запрещены БД: администратор задаёт другой явно.
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Size(models.Model):
    name = models.CharField("размер", max_length=20)

    class Meta:
        ordering = ["pk"]
        verbose_name = "размер"
        verbose_name_plural = "размеры"

    def __str__(self):
        return self.name


class ProductQuerySet(models.QuerySet):
    def active(self):
        """Цепочка остаётся ленивой: SELECT выполнится при чтении результатов."""
        return self.filter(is_active=True)


class Product(models.Model):
    name = models.CharField("название", max_length=100)
    slug = models.SlugField("адрес", max_length=100, unique=True, allow_unicode=True)
    # PROTECT не позволяет случайно удалить категорию вместе с товарами.
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="products", verbose_name="категория"
    )
    color = models.CharField("цвет", max_length=100)
    # Деньги храним в Decimal, а не float: 0.1 + 0.2 не должно менять сумму заказа.
    price = models.DecimalField(
        "цена", max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0"))]
    )
    description = models.TextField("описание", blank=True)
    main_image = models.ImageField("фотография", upload_to="products/main/", blank=True)
    is_active = models.BooleanField("опубликован", default=True)
    created_at = models.DateTimeField("создан", auto_now_add=True)
    updated_at = models.DateTimeField("обновлён", auto_now=True)

    objects = ProductQuerySet.as_manager()

    class Meta:
        # Вторая колонка делает порядок стабильным даже при равных датах.
        ordering = ["-created_at", "-pk"]
        constraints = [models.CheckConstraint(condition=models.Q(price__gte=0), name="product_price_nonnegative")]
        verbose_name = "товар"
        verbose_name_plural = "товары"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name, allow_unicode=True)
        super().save(*args, **kwargs)

    @property
    def product_sizes(self):
        """Читаемый псевдоним для опечатки в исходной версии проекта.

        Старое related_name оставлено, чтобы ранее написанный код продолжал
        работать. Обратная связь возвращает RelatedManager, а не один объект.
        """
        return self.prduct_size

    def get_absolute_url(self):
        # reverse связывает адрес с именем маршрута: HTML не знает его структуру.
        return reverse("main:product_detail", kwargs={"slug": self.slug})

    def __str__(self):
        return self.name


class ProductSize(models.Model):
    """Остаток конкретного размера: один товар может иметь несколько вариантов."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="prduct_size", verbose_name="товар")
    size = models.ForeignKey(Size, on_delete=models.PROTECT, verbose_name="размер")
    stock = models.PositiveBigIntegerField("остаток", default=0)

    class Meta:
        ordering = ["pk"]
        constraints = [
            models.UniqueConstraint(fields=["product", "size"], name="unique_product_size"),
        ]
        verbose_name = "остаток размера"
        verbose_name_plural = "остатки размеров"

    def __str__(self):
        return f"{self.product.name}, {self.size.name}: {self.stock} шт."


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images", verbose_name="товар")
    image = models.ImageField("фотография", upload_to="products/extra/")

    class Meta:
        verbose_name = "фотография товара"
        verbose_name_plural = "фотографии товаров"

    def __str__(self):
        return f"Фото товара №{self.product_id}"
