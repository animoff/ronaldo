from django.urls import path
from . import views

app_name = "commerce"
urlpatterns = [
    path("cart/", views.cart, name="cart"),
    path("cart/add/<int:sku_id>/", views.cart_add, name="cart_add"),
    path("cart/update/<int:sku_id>/", views.cart_update, name="cart_update"),
    path("checkout/", views.checkout, name="checkout"),
    path("orders/", views.order_list, name="order_list"),
    path("orders/<int:pk>/", views.order_detail, name="order_detail"),
    path("accounts/register/", views.register, name="register"),
]
