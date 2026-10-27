"""Админка — внутренний инструмент сотрудников, не публичный магазин."""
from django.contrib import admin
from .models import Category, Product, ProductImage, ProductSize, Size


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name",)


@admin.register(Size)
class SizeAdmin(admin.ModelAdmin):
    search_fields = ("name",)


class ProductSizeInline(admin.TabularInline):
    model = ProductSize
    extra = 0


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "price", "is_active", "updated_at")
    list_filter = ("is_active", "category")
    search_fields = ("name", "description")
    prepopulated_fields = {"slug": ("name",)}
    list_select_related = ("category",)
    readonly_fields = ("created_at", "updated_at")
    inlines = (ProductSizeInline, ProductImageInline)


@admin.register(ProductSize)
class ProductSizeAdmin(admin.ModelAdmin):
    list_display = ("product", "size", "stock")
    list_select_related = ("product", "size")
    search_fields = ("product__name",)
