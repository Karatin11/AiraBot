from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from .models import CartItem, Product, User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "email", "password")
        extra_kwargs = {"password": {"write_only": True}}


class ProductSerializer(serializers.ModelSerializer):
    final_price = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ["id", "name", "price", "discount_percent", "final_price", "image"]

    def get_final_price(self, obj):
        if obj.discount_percent > 0:
            return (
                obj.price * (Decimal(100) - Decimal(obj.discount_percent)) / Decimal(100)
            )
        return obj.price

    def get_image(self, obj):
        request = self.context.get("request")
        if obj.image and hasattr(obj.image, "url"):
            return request.build_absolute_uri(obj.image.url) if request else obj.image.url
        return None


class CartItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name")
    product_price = serializers.DecimalField(
        source="product.price",
        max_digits=10,
        decimal_places=2,
    )

    class Meta:
        model = CartItem
        fields = (
            "product_name",
            "product_price",
            "quantity",
            "discount_percent",
            "final_price",
        )
