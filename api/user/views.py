from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Cart, CartItem, Category, Order, OrderItem, Product
from .serializers import ProductSerializer


@api_view(["GET"])
def get_categories(request):
    categories = Category.objects.all().values("id", "name")
    return Response(categories)


@api_view(["GET"])
def get_products_by_category(request, category_id):
    category = get_object_or_404(Category, id=category_id)
    products = category.products.all()
    serializer = ProductSerializer(products, many=True, context={"request": request})
    return Response(serializer.data)


@api_view(["POST"])
def add_to_cart(request):
    phone = request.data.get("phone")
    product_id = request.data.get("product_id")
    quantity = int(request.data.get("quantity", 1))

    if not phone or not product_id:
        return Response({"error": "phone и product_id обязательны"}, status=400)

    product = get_object_or_404(Product, id=product_id)
    cart, _ = Cart.objects.get_or_create(phone=phone)

    item, created = CartItem.objects.get_or_create(
        cart=cart,
        product=product,
        defaults={"quantity": quantity},
    )

    if not created:
        item.quantity += quantity

    item.final_price = product.discounted_price()
    item.save()

    return Response(
        {
            "message": "Товар добавлен в корзину",
            "discount_percent": product.discount_percent,
            "final_price": str(item.final_price),
        },
    )


@api_view(["GET"])
def get_cart(request, phone):
    cart = get_object_or_404(Cart, phone=phone)

    items = cart.items.select_related("product")
    result = []
    for item in items:
        result.append(
            {
                "name": item.product.name,
                "price": float(item.product.price),
                "discount_percent": float(item.product.discount_percent),
                "quantity": item.quantity,
                "final_price": float(item.final_price),
            },
        )

    return Response(
        {
            "phone": phone,
            "items": result,
            "total_price": cart.total_price(),
        },
    )


@api_view(["POST"])
def make_order(request):
    phone = request.data.get("phone")
    if not phone:
        return Response({"error": "Требуется указать номер телефона"}, status=400)

    cart = get_object_or_404(Cart, phone=phone)
    if not cart.items.exists():
        return Response({"error": "Корзина пуста"}, status=400)

    order = Order.objects.create(
        total=cart.total_price(),
        phone=phone,
    )

    items_data = []
    for item in cart.items.select_related("product").all():
        OrderItem.objects.create(
            order=order,
            product=item.product,
            quantity=item.quantity,
            price=(
                item.final_price if item.final_price else item.product.discounted_price()
            ),
        )
        items_data.append(
            {
                "name": item.product.name,
                "price": float(item.product.price),
                "discount_percent": float(item.product.discount_percent),
                "quantity": item.quantity,
                "final_price": float(item.final_price),
            },
        )

    cart.items.all().delete()

    return Response(
        {
            "message": "Заказ оформлен",
            "order_id": order.id,
            "total": order.total,
            "items": items_data,  # 👈 возвращаем товары
        },
    )


@api_view(["GET"])
def get_new_orders(request):
    new_orders = Order.objects.filter(is_new=True).order_by("-created_at")

    result = []
    for order in new_orders:
        items = order.items.all()
        items_data = []
        for item in items:
            items_data.append(
                {
                    "product": item.product.name,
                    "quantity": item.quantity,
                    "price": float(item.price),
                    "subtotal": float(item.price * item.quantity),
                },
            )

        result.append(
            {
                "order_id": order.id,
                "created_at": order.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "phone": order.phone,
                "total": float(order.total),
                "items": items_data,
            },
        )

    return Response(result)
