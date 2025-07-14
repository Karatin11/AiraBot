from __future__ import annotations

from django.conf import settings
from django.conf.urls.static import static
from django.urls import path

from api.user import views

urlpatterns = [
    path("categories/", views.get_categories, name="get_categories"),
    path(
        "products/<int:category_id>/",
        views.get_products_by_category,
        name="get_products_by_category",
    ),
    path("cart/add/", views.add_to_cart, name="add_to_cart"),
    path("cart/<str:phone>/", views.get_cart, name="get_cart_by_phone"),
    path("order/", views.make_order, name="make_order"),
    path("order/new/", views.get_new_orders, name="new-orders"),
    *static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT),
]
