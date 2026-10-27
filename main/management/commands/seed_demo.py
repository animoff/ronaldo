"""Повторяемая команда: python manage.py seed_demo.

get_or_create находит запись по стабильному ключу и не перезаписывает изменения
ученика. В отличие от fixture, эта команда не привязана к числовым primary key.
"""
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from main.models import Category, Product, ProductSize, Size


class Command(BaseCommand):
    help = "Добавляет учебные товары и остатки; существующие данные не перезаписывает."

    @transaction.atomic
    def handle(self, *args, **options):
        # atomic: либо создаётся весь набор, либо при ошибке не сохраняется ничего.
        categories = {}
        for slug, name in [("clothes", "Одежда"), ("accessories", "Аксессуары"), ("workspace", "Рабочее место")]:
            categories[slug], _ = Category.objects.get_or_create(slug=slug, defaults={"name": name})
        sizes = {}
        for name in ("S", "M", "L", "One size"):
            sizes[name], _ = Size.objects.get_or_create(name=name)
        data = [
            ("python-tshirt", "Футболка Python", "clothes", "2400.00", "Графит", "Плотный хлопок и любимый язык. Для первого pull request и сотого релиза."),
            ("django-hoodie", "Худи Django", "clothes", "5900.00", "Зелёный", "Мягкое худи для прохладных вечеров с документацией Django."),
            ("terminal-cap", "Кепка Terminal", "clothes", "1800.00", "Чёрный", "Минимализм командной строки в повседневном гардеробе."),
            ("backend-tote", "Шопер Backend", "accessories", "1200.00", "Бежевый", "Для ноутбука, книги и идей. Повторное использование — хорошая привычка."),
            ("commit-notebook", "Блокнот Commit", "workspace", "790.00", "Терракота", "Записывай гипотезы до отладки и выводы после неё."),
            ("api-mug", "Кружка API", "workspace", "990.00", "Молочный", "Чашка чая, HTTP 200 и немного спокойствия перед деплоем."),
            ("debug-stickers", "Набор стикеров Debug", "accessories", "390.00", "Разноцветный", "Укрась ноутбук напоминаниями о любимых инструментах."),
            ("query-mat", "Коврик Query", "workspace", "1600.00", "Серый", "Большой коврик для рабочего стола: место для клавиатуры и SQL-запросов."),
            ("git-socks", "Носки Git", "clothes", "590.00", "Синий", "Два носка, одна ветка. Мягкая ткань на каждый день."),
            ("focus-bottle", "Бутылка Focus", "accessories", "1700.00", "Оливковый", "Не забывай пить воду и делать перерывы между задачами."),
            ("review-pen", "Ручка Review", "workspace", "290.00", "Чёрный", "Для заметок на code review и первых схем архитектуры."),
            ("deploy-bag", "Чехол Deploy", "accessories", "2100.00", "Графит", "Защита ноутбука в дороге. Подходит для устройств до 14 дюймов."),
        ]
        created_count = 0
        for slug, name, category, price, color, description in data:
            product, created = Product.objects.get_or_create(slug=slug, defaults={
                "name": name, "category": categories[category], "price": Decimal(price),
                "color": color, "description": description, "is_active": True,
            })
            created_count += int(created)
            variant_sizes = ("S", "M", "L") if slug in ("python-tshirt", "django-hoodie") else ("One size",)
            for size_name in variant_sizes:
                ProductSize.objects.get_or_create(product=product, size=sizes[size_name], defaults={"stock": 20})
        self.stdout.write(self.style.SUCCESS(f"Каталог готов. Добавлено товаров: {created_count}. Пароли и пользователи не создавались."))
