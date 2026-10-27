from django.urls import path
from . import api

app_name = "api"
urlpatterns = [
    path("products/", api.product_list, name="product_list"),
    path("products/<str:slug>/", api.product_detail, name="product_detail"),
    path("orders/", api.order_list, name="order_list"),
]
