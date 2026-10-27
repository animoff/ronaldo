"""Исполняемые примеры контрактов каталога.

TestCase создаёт отдельную тестовую БД и откатывает изменения каждого теста.
Проверяем результат, а не количество вызовов внутренней функции: реализацию
можно улучшать, сохраняя поведение для пользователя.
"""
from decimal import Decimal
from io import StringIO

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.urls import reverse

from .models import Category, Product, ProductSize, Size


class CatalogFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(name="Одежда", slug="clothes")
        cls.other_category = Category.objects.create(name="Рабочий стол", slug="desk")
        cls.product = Product.objects.create(
            name="Python T-shirt", slug="python-shirt", category=cls.category,
            color="Чёрный", price=Decimal("1900.00"), description="Хлопковая футболка",
        )
        cls.hidden = Product.objects.create(
            name="Secret product", slug="secret", category=cls.category,
            color="Белый", price=Decimal("100.00"), is_active=False,
        )
        cls.size = Size.objects.create(name="M")
        cls.variant = ProductSize.objects.create(product=cls.product, size=cls.size, stock=4)


class CatalogModelTests(CatalogFixture):
    def test_slug_is_generated_for_russian_name(self):
        category = Category.objects.create(name="Полезные книги")
        self.assertEqual(category.slug, "полезные-книги")
        self.product.slug = ""
        self.product.name = "Учебный товар"
        self.product.save()
        self.assertEqual(self.product.slug, "учебный-товар")

    def test_explicit_slug_is_preserved_when_name_changes(self):
        self.product.name = "New name"
        self.product.save()
        self.assertEqual(self.product.slug, "python-shirt")

    def test_active_queryset_hides_unpublished_products(self):
        self.assertQuerySetEqual(Product.objects.active(), [self.product])

    def test_price_validator_gives_useful_form_error(self):
        self.product.price = Decimal("-1")
        with self.assertRaises(ValidationError) as error:
            self.product.full_clean()
        self.assertIn("price", error.exception.message_dict)

    def test_database_rejects_negative_price_even_without_full_clean(self):
        # save()/update() не вызывают full_clean автоматически. Поэтому одного
        # валидатора недостаточно: CheckConstraint защищает БД независимо от UI.
        with self.assertRaises(IntegrityError), transaction.atomic():
            Product.objects.filter(pk=self.product.pk).update(price=Decimal("-1"))

    def test_duplicate_size_for_same_product_is_rejected(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProductSize.objects.create(product=self.product, size=self.size, stock=2)

    def test_zero_stock_is_valid(self):
        self.variant.stock = 0
        self.variant.full_clean()
        self.variant.save()
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 0)

    def test_category_with_products_cannot_be_deleted_accidentally(self):
        with self.assertRaises(ProtectedError):
            self.category.delete()

    def test_select_related_loads_categories_in_one_query(self):
        with self.assertNumQueries(1):
            names = [product.category.name for product in Product.objects.select_related("category")]
        self.assertEqual(names, ["Одежда", "Одежда"])

    def test_readable_stock_alias(self):
        self.assertEqual(self.product.product_sizes.get(), self.variant)


class CatalogViewTests(CatalogFixture):
    def test_home_has_active_featured_products(self):
        response = self.client.get(reverse("main:home"))
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.product, response.context["featured_products"])
        self.assertNotIn(self.hidden, response.context["featured_products"])

    def test_catalog_only_shows_published_products(self):
        response = self.client.get(reverse("main:product_list"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["products"]), [self.product])

    def test_search_filters_products(self):
        response = self.client.get(reverse("main:product_list"), {"q": "Python"})
        self.assertEqual(list(response.context["products"]), [self.product])
        response = self.client.get(reverse("main:product_list"), {"q": "does-not-exist"})
        self.assertEqual(list(response.context["products"]), [])

    def test_category_filter_does_not_leak_other_products(self):
        response = self.client.get(reverse("main:product_list"), {"category": "desk"})
        self.assertEqual(list(response.context["products"]), [])

    def test_pagination_limits_page_and_handles_invalid_number(self):
        for number in range(11):
            Product.objects.create(name=f"Item {number}", slug=f"item-{number}",
                                   category=self.category, color="Серый", price=10)
        response = self.client.get(reverse("main:product_list"), {"page": "not-a-number"})
        self.assertEqual(response.context["products"].number, 1)
        self.assertEqual(len(response.context["products"]), 9)
        response = self.client.get(reverse("main:product_list"), {"page": 2})
        self.assertEqual(len(response.context["products"]), 3)

    def test_detail_loads_available_sizes(self):
        response = self.client.get(self.product.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["product"], self.product)
        self.assertEqual(list(response.context["product_sizes"]), [self.variant])

    def test_hidden_and_missing_products_return_404(self):
        for slug in ("secret", "missing"):
            response = self.client.get(reverse("main:product_detail", kwargs={"slug": slug}))
            self.assertEqual(response.status_code, 404)

    def test_unicode_slug_can_be_opened(self):
        self.product.slug = "русский-товар"
        self.product.save()
        response = self.client.get(self.product.get_absolute_url())
        self.assertEqual(response.status_code, 200)

    def test_catalog_rejects_post_requests(self):
        response = self.client.post(reverse("main:product_list"))
        self.assertEqual(response.status_code, 405)


class DemoDataTests(TestCase):
    def test_seed_is_repeatable_and_preserves_user_edits(self):
        call_command("seed_demo", stdout=StringIO())
        initial_counts = (Product.objects.count(), Category.objects.count(), ProductSize.objects.count())
        product = Product.objects.get(slug="python-tshirt")
        product.price = Decimal("123.45")
        product.save()
        variant = product.product_sizes.first()
        variant.stock = 3
        variant.save()
        call_command("seed_demo", stdout=StringIO())
        self.assertEqual((Product.objects.count(), Category.objects.count(), ProductSize.objects.count()), initial_counts)
        self.assertEqual(initial_counts[0], 12)
        product.refresh_from_db()
        variant.refresh_from_db()
        self.assertEqual(product.price, Decimal("123.45"))
        self.assertEqual(variant.stock, 3)
