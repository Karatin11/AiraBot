from __future__ import annotations

from decimal import Decimal

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    pass


class Category(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self) -> str:
        return self.name


class Product(models.Model):
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name="products",
    )
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    discount_percent = models.PositiveIntegerField(
        default=0,
        help_text="Скидка в процентах",
    )
    image = models.ImageField(upload_to="product_images/", blank=True, null=True)

    def discounted_price(self):
        if self.discount_percent:
            return self.price * (
                Decimal(1) - Decimal(self.discount_percent) / Decimal(100)
            )
        return self.price

    def __str__(self) -> str:
        return self.name


class Cart(models.Model):
    phone = models.CharField(max_length=20, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def total_price(self):
        total = Decimal(0)
        for item in self.items.all():
            price = (
                item.final_price if item.final_price else item.product.discounted_price()
            )
            total += price * item.quantity
        return total

    def __str__(self) -> str:
        return f"Cart for {self.phone}"


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    final_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    def total_price(self):
        return (
            self.final_price if self.final_price else self.product.discounted_price()
        ) * self.quantity

    def __str__(self) -> str:
        return f"{self.product.name} x {self.quantity}"


class Order(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    phone = models.CharField(max_length=20)
    is_new = models.BooleanField(default=True)

    def __str__(self) -> str:
        return f"Order #{self.id} от {self.phone} на сумму {self.total}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self) -> str:
        return f"{self.product.name} x {self.quantity}"
