"""Минимальный JSON API без DRF: полезно сначала понять обычный HTTP.

GET /api/products/?q=...&category=...&page=1
GET /api/products/<slug>/
GET /api/orders/                  — только собственные заказы, session auth

Денежные значения сериализуем строками, даты — ISO 8601. Все списки имеют
пагинацию. API только для чтения; покупки демонстрируются HTML-формами с CSRF.
"""

from django.core.paginator import EmptyPage, Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_GET

from main.models import Product
from .models import Order

PAGE_SIZE = 12


def error(message, *, status):
    return JsonResponse({"error": message}, status=status)


def paginated(request, queryset, serialize):
    try:
        page_number = int(request.GET.get("page", "1"))
        if page_number < 1:
            raise ValueError
    except (ValueError, TypeError):
        return error("page должен быть положительным целым числом.", status=400)
    paginator = Paginator(queryset, PAGE_SIZE)
    try:
        page = paginator.page(page_number)
    except EmptyPage:
        return error("Страница не существует.", status=404)
    return JsonResponse({"count": paginator.count, "page": page.number, "pages": paginator.num_pages,
                         "next_page": page.next_page_number() if page.has_next() else None,
                         "results": [serialize(item) for item in page]})


def product_data(product):
    return {"id": product.pk, "name": product.name, "slug": product.slug,
            "price": str(product.price), "currency": "RUB",
            "category": {"name": product.category.name, "slug": product.category.slug},
            "url": reverse("api:product_detail", kwargs={"slug": product.slug})}


@require_GET
def product_list(request):
    products = Product.objects.filter(is_active=True).select_related("category").order_by("pk")
    query = request.GET.get("q", "").strip()[:100]
    category = request.GET.get("category", "").strip()[:100]
    if query:
        # ORM связывает параметры с SQL отдельно: строка пользователя не становится SQL-кодом.
        products = products.filter(Q(name__icontains=query) | Q(description__icontains=query))
    if category:
        products = products.filter(category__slug=category)
    return paginated(request, products, product_data)


@require_GET
def product_detail(request, slug):
    product = Product.objects.filter(slug=slug, is_active=True).select_related("category").first()
    if product is None:
        return error("Товар не найден.", status=404)
    data = product_data(product)
    data.update({"description": product.description, "color": product.color,
                 "image": product.main_image.url if product.main_image else None,
                 "sizes": [{"id": sku.pk, "name": sku.size.name, "stock": sku.stock}
                           for sku in product.prduct_size.select_related("size").order_by("pk")]})
    return JsonResponse(data)


def order_data(order):
    return {"id": order.pk, "status": order.status, "total": str(order.total),
            "currency": "RUB", "created_at": order.created_at.isoformat(),
            "items": [{"product": item.product_name, "size": item.size_name,
                       "quantity": item.quantity, "unit_price": str(item.unit_price),
                       "line_total": str(item.line_total)} for item in order.items.all()]}


@require_GET
def order_list(request):
    if not request.user.is_authenticated:
        # HTML-login_required вернул бы 302 и страницу входа; API-клиенту нужен JSON.
        response = error("Для просмотра заказов войдите в аккаунт.", status=401)
        response["Cache-Control"] = "private, no-store"
        return response
    orders = Order.objects.filter(owner=request.user).prefetch_related("items").order_by("-created_at", "-pk")
    response = paginated(request, orders, order_data)
    response["Cache-Control"] = "private, no-store"
    return response
