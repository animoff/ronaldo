"""HTTP-представления каталога: запрос → ORM → контекст → HTML.

Views отвечают за HTTP. Сложные изменения состояния (например, оформление
заказа) вынесены в сервисы commerce: так их можно вызвать также из API.
"""

from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from .models import Category, Product


@require_GET
def home(request):
    return render(request, "home.html", {
        "featured_products": Product.objects.active().select_related("category")[:6],
        "product_count": Product.objects.active().count(),
        "category_count": Category.objects.count(),
    })


@require_GET
def product_list(request):
    # select_related делает JOIN: имя категории не требует нового SELECT для
    # каждого товара (типичная проблема N+1 запросов).
    queryset = Product.objects.active().select_related("category")
    query = request.GET.get("q", "").strip()[:100]
    current_category = request.GET.get("category", "").strip()[:100]
    if query:
        # ORM передаёт значения параметрами SQL. Не склеиваем SQL со строкой q!
        queryset = queryset.filter(Q(name__icontains=query) | Q(description__icontains=query))
    if current_category:
        queryset = queryset.filter(category__slug=current_category)
    # get_page мягко обрабатывает ?page=abc и слишком большие номера.
    page = Paginator(queryset, 9).get_page(request.GET.get("page"))
    return render(request, "main/product_list.html", {
        "products": page,
        "page_obj": page,
        "categories": Category.objects.all(),
        "current_category": current_category,
        "query": query,
    })


@require_GET
def product_detail(request, slug):
    # Неактивный товар недоступен даже по прямому URL. Это правило должно быть
    # в запросе, а не только в шаблоне списка.
    product = get_object_or_404(
        Product.objects.active().select_related("category").prefetch_related("images"),
        slug=slug,
    )
    return render(request, "main/product_detail.html", {
        "product": product,
        "product_sizes": product.product_sizes.select_related("size"),
    })
