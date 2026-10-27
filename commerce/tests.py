"""Тесты проверяют наблюдаемое поведение, включая деньги, права и откат БД.

Запуск: python manage.py test commerce. Django создаёт отдельную тестовую БД:
демонстрационные товары и реальные локальные заказы не затрагиваются.
"""

import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, connections, transaction
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse

from main.models import Category, Product, ProductSize, Size
from .models import Order, OrderItem
from .services import CheckoutError, place_order


class ShopFixtures(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create_user(username="student", password="Learning-example-2026!")
        cls.other = get_user_model().objects.create_user(username="other", password="Learning-other-2026!")
        cls.category = Category.objects.create(name="Обувь", slug="shoes")
        cls.size = Size.objects.create(name="42")
        cls.product = Product.objects.create(name="Учебные кеды", slug="sneakers", category=cls.category,
                                             color="белый", price=Decimal("123.45"), is_active=True)
        cls.sku = ProductSize.objects.create(product=cls.product, size=cls.size, stock=5)

    def place(self, **overrides):
        kwargs = {"owner": self.owner, "quantities": {str(self.sku.pk): 2},
                  "address": "Учебный город, Тестовая улица, 10", "idempotency_key": uuid.uuid4()}
        kwargs.update(overrides)
        return place_order(**kwargs)

    def add_to_cart(self, quantity=2):
        return self.client.post(reverse("commerce:cart_add", args=[self.sku.pk]), {"quantity": quantity})

    def checkout_data(self):
        response = self.client.get(reverse("commerce:checkout"))
        return {"address": "Учебный город, Тестовая улица, 10",
                "idempotency_key": response.context["form"].initial["idempotency_key"]}


class CheckoutServiceTests(ShopFixtures):
    def test_total_and_stock_use_database_price(self):
        order = self.place()
        self.sku.refresh_from_db()
        self.assertEqual(order.total, Decimal("246.90"))
        self.assertEqual(self.sku.stock, 3)
        self.assertEqual(order.items.get().line_total, Decimal("246.90"))

    def test_price_and_names_are_snapshots(self):
        order = self.place()
        Product.objects.filter(pk=self.product.pk).update(price=Decimal("999.99"), name="Новое имя")
        item = order.items.get()
        self.assertEqual(item.product_name, "Учебные кеды")
        self.assertEqual(item.unit_price, Decimal("123.45"))

    def test_deleted_sku_preserves_order_item(self):
        order = self.place()
        self.sku.delete()
        item = order.items.get()
        self.assertIsNone(item.sku_id)
        self.assertEqual(item.product_name, "Учебные кеды")

    def test_repeat_key_returns_existing_order_without_reserving_again(self):
        key = uuid.uuid4()
        first = self.place(idempotency_key=key)
        second = self.place(idempotency_key=key)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Order.objects.count(), 1)
        self.sku.refresh_from_db()
        self.assertEqual(self.sku.stock, 3)

    def test_another_owner_cannot_reuse_key(self):
        key = uuid.uuid4()
        self.place(idempotency_key=key)
        with self.assertRaises(CheckoutError):
            self.place(owner=self.other, idempotency_key=key)

    def test_insufficient_stock_rolls_back_whole_order(self):
        second_size = Size.objects.create(name="43")
        second_sku = ProductSize.objects.create(product=self.product, size=second_size, stock=0)
        with self.assertRaises(CheckoutError):
            self.place(quantities={str(self.sku.pk): 2, str(second_sku.pk): 1})
        self.sku.refresh_from_db()
        self.assertEqual(self.sku.stock, 5, "First SKU update must also roll back")
        self.assertFalse(Order.objects.exists())
        self.assertFalse(OrderItem.objects.exists())

    def test_inactive_product_cannot_be_ordered(self):
        Product.objects.filter(pk=self.product.pk).update(is_active=False)
        with self.assertRaises(CheckoutError):
            self.place()
        self.assertFalse(Order.objects.exists())

    def test_invalid_quantities_cannot_be_ordered(self):
        for quantity in (0, -1, 100, "2", True):
            with self.subTest(quantity=quantity), self.assertRaises(CheckoutError):
                self.place(quantities={str(self.sku.pk): quantity})
        self.assertFalse(Order.objects.exists())

    def test_invalid_sku_keys_are_rejected_before_database_query(self):
        for key in (self.sku.pk, "²", "01", "0", "9" * 100, str(2**63)):
            with self.subTest(key=key), self.assertRaises(CheckoutError):
                self.place(quantities={key: 1})
        self.assertFalse(Order.objects.exists())

    def test_database_rejects_zero_quantity(self):
        order = self.place()
        with self.assertRaises(IntegrityError), transaction.atomic():
            OrderItem.objects.create(order=order, sku=self.sku, product_name="x", size_name="42",
                                     unit_price=Decimal("1.00"), quantity=0)


class CartAndCheckoutViewsTests(ShopFixtures):
    def test_cart_add_update_remove(self):
        self.assertRedirects(self.add_to_cart(), reverse("commerce:cart"))
        page = self.client.get(reverse("commerce:cart"))
        self.assertEqual(page.context["total"], Decimal("246.90"))
        self.client.post(reverse("commerce:cart_update", args=[self.sku.pk]), {"quantity": 1})
        self.assertEqual(self.client.session["cart"][str(self.sku.pk)], 1)
        self.client.post(reverse("commerce:cart_update", args=[self.sku.pk]), {"quantity": 0})
        self.assertEqual(self.client.session["cart"], {})

    def test_cart_rejects_bad_quantities_and_stock_overflow(self):
        for value in (-1, "nope", 1.5, 99, ""):
            with self.subTest(value=value):
                self.add_to_cart(value)
                self.assertEqual(self.client.session.get("cart", {}), {})

    def test_get_cannot_change_cart(self):
        self.assertEqual(self.client.get(reverse("commerce:cart_add", args=[self.sku.pk])).status_code, 405)
        self.assertEqual(self.client.get(reverse("commerce:cart_update", args=[self.sku.pk])).status_code, 405)

    def test_post_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post(reverse("commerce:cart_add", args=[self.sku.pk]), {"quantity": 1})
        self.assertEqual(response.status_code, 403)

    def test_stale_deleted_sku_is_removed_from_cart(self):
        self.add_to_cart()
        self.sku.delete()
        page = self.client.get(reverse("commerce:cart"))
        self.assertEqual(page.context["lines"], [])
        self.assertEqual(self.client.session["cart"], {})

    def test_malformed_session_keys_are_cleaned_without_error(self):
        session = self.client.session
        session["cart"] = {"²": 1, "9" * 100: 1, str(self.sku.pk): 2}
        session.save()
        response = self.client.get(reverse("commerce:cart"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["lines"]), 1)
        self.assertEqual(response.context["total"], Decimal("246.90"))

    def test_checkout_requires_login(self):
        response = self.client.get(reverse("commerce:checkout"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_checkout_and_repeat_submit(self):
        self.client.force_login(self.owner)
        self.add_to_cart()
        data = self.checkout_data()
        first = self.client.post(reverse("commerce:checkout"), data)
        self.assertEqual(first.status_code, 302)
        self.assertEqual(self.client.session["cart"], {})
        second = self.client.post(reverse("commerce:checkout"), data)
        self.assertEqual(second.url, first.url)
        self.assertEqual(Order.objects.count(), 1)
        self.sku.refresh_from_db()
        self.assertEqual(self.sku.stock, 3)

    def test_unknown_token_is_rejected(self):
        self.client.force_login(self.owner)
        self.add_to_cart()
        response = self.client.post(reverse("commerce:checkout"),
                                    {"address": "Тестовая улица, 10", "idempotency_key": uuid.uuid4()})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Order.objects.exists())

    def test_changed_cart_requires_new_checkout(self):
        self.client.force_login(self.owner)
        self.add_to_cart()
        data = self.checkout_data()
        self.add_to_cart(1)
        response = self.client.post(reverse("commerce:checkout"), data)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Order.objects.exists())

    def test_price_in_post_is_ignored(self):
        self.client.force_login(self.owner)
        self.add_to_cart()
        data = {**self.checkout_data(), "price": "0.01", "total": "0.01"}
        self.client.post(reverse("commerce:checkout"), data)
        self.assertEqual(Order.objects.get().total, Decimal("246.90"))

    def test_user_cannot_read_another_users_order(self):
        order = self.place()
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("commerce:order_detail", args=[order.pk])).status_code, 404)
        response = self.client.get(reverse("commerce:order_list"))
        self.assertEqual(list(response.context["orders"]), [])

    def test_owner_can_read_order(self):
        order = self.place()
        self.client.force_login(self.owner)
        response = self.client.get(reverse("commerce:order_detail", args=[order.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["order"].pk, order.pk)

    def test_registration_hashes_password_and_logs_in(self):
        response = self.client.post(reverse("commerce:register"), {
            "username": "new_student", "email": "student@example.com",
            "password1": "Study-web-development-2026!", "password2": "Study-web-development-2026!",
        })
        self.assertEqual(response.status_code, 302)
        user = get_user_model().objects.get(username="new_student")
        self.assertNotEqual(user.password, "Study-web-development-2026!")
        self.assertTrue(user.check_password("Study-web-development-2026!"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_logout_is_post_only(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
        self.assertEqual(self.client.post(reverse("logout")).status_code, 302)
        self.assertNotIn("_auth_user_id", self.client.session)


class ApiTests(ShopFixtures):
    def test_product_json_money_is_string(self):
        response = self.client.get(reverse("api:product_list"))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["price"], "123.45")
        self.assertEqual(data["results"][0]["category"]["slug"], "shoes")

    def test_product_detail_and_missing_product(self):
        response = self.client.get(reverse("api:product_detail", args=[self.product.slug]))
        self.assertEqual(response.json()["sizes"][0]["stock"], 5)
        self.assertEqual(self.client.get(reverse("api:product_detail", args=["missing"])).status_code, 404)

    def test_hidden_product_does_not_leak(self):
        Product.objects.filter(pk=self.product.pk).update(is_active=False)
        self.assertEqual(self.client.get(reverse("api:product_list")).json()["count"], 0)
        self.assertEqual(self.client.get(reverse("api:product_detail", args=[self.product.slug])).status_code, 404)

    def test_filter_and_invalid_pagination(self):
        self.assertEqual(self.client.get(reverse("api:product_list"), {"q": "несуществующий"}).json()["count"], 0)
        self.assertEqual(self.client.get(reverse("api:product_list"), {"category": "missing"}).json()["count"], 0)
        for page in ("bad", 0, -1):
            self.assertEqual(self.client.get(reverse("api:product_list"), {"page": page}).status_code, 400)
        self.assertEqual(self.client.get(reverse("api:product_list"), {"page": 999}).status_code, 404)

    def test_api_pagination_has_no_duplicates(self):
        for index in range(14):
            Product.objects.create(name=f"Товар {index}", slug=f"item-{index}", category=self.category,
                                   color="blue", price=Decimal("1.00"))
        first = self.client.get(reverse("api:product_list")).json()
        second = self.client.get(reverse("api:product_list"), {"page": 2}).json()
        self.assertEqual(first["count"], 15)
        self.assertEqual(len(first["results"]), 12)
        self.assertEqual(len(second["results"]), 3)
        self.assertFalse({item["id"] for item in first["results"]} & {item["id"] for item in second["results"]})

    def test_orders_require_authentication_and_are_owner_scoped(self):
        self.place()
        self.assertEqual(self.client.get(reverse("api:order_list")).status_code, 401)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("api:order_list")).json()["count"], 0)
        self.client.force_login(self.owner)
        response = self.client.get(reverse("api:order_list"))
        self.assertEqual(response.json()["results"][0]["total"], "246.90")
        self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_read_only_api_rejects_post(self):
        self.assertEqual(self.client.post(reverse("api:product_list"), {}).status_code, 405)


# Эти тесты требуют настоящих конкурентных транзакций. SQLite не имеет строковых
# блокировок: пропуск здесь честно обозначает границу локальной учебной проверки.
@skipUnless(connection.vendor == "postgresql", "Конкурентные покупки проверяются на PostgreSQL")
class PostgreSQLConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(username="concurrency-student")
        category = Category.objects.create(name="Конкуренция", slug="concurrency")
        product = Product.objects.create(name="Последний товар", slug="last-item", category=category,
                                         color="blue", price=Decimal("10.00"))
        size = Size.objects.create(name="M")
        self.sku = ProductSize.objects.create(product=product, size=size, stock=1)

    def run_concurrently(self, keys):
        barrier = Barrier(2)

        def checkout(key):
            # Каждый поток получает отдельное соединение; иначе это не конкуренция БД.
            try:
                owner = get_user_model().objects.get(pk=self.owner.pk)
                barrier.wait(timeout=10)
                try:
                    return place_order(owner=owner, quantities={str(self.sku.pk): 1},
                                       address="Учебный адрес, дом 1", idempotency_key=key).pk
                except CheckoutError:
                    return None
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            return list(executor.map(checkout, keys))

    def test_only_one_buyer_gets_last_unit(self):
        result = self.run_concurrently([uuid.uuid4(), uuid.uuid4()])
        self.assertEqual(sum(order_id is not None for order_id in result), 1)
        self.assertEqual(Order.objects.count(), 1)
        self.sku.refresh_from_db()
        self.assertEqual(self.sku.stock, 0)

    def test_concurrent_duplicate_submission_creates_one_order(self):
        key = uuid.uuid4()
        result = self.run_concurrently([key, key])
        self.assertIsNotNone(result[0])
        self.assertEqual(result[0], result[1])
        self.assertEqual(Order.objects.count(), 1)
        self.sku.refresh_from_db()
        self.assertEqual(self.sku.stock, 0)
