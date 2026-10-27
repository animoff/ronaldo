"""Админка позволяет менять статус, но не переписывать финансовую историю."""
from django.contrib import admin
from .models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    fields = ("product_name", "size_name", "unit_price", "quantity", "line_total")
    readonly_fields = fields
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "owner", "status", "total", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("owner__username", "address")
    readonly_fields = ("owner", "address", "total", "idempotency_key", "created_at")
    inlines = (OrderItemInline,)
    list_select_related = ("owner",)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
