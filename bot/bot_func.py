from __future__ import annotations

import os
import re
import tempfile
from datetime import datetime
from tempfile import NamedTemporaryFile
from typing import TYPE_CHECKING

import aiohttp
import httpx
from aiogram import F, Router
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from fpdf import FPDF

from .utils import get_phone, get_user_lang, get_user_phone, save_phone

if TYPE_CHECKING:
    from aiogram.fsm.context import FSMContext

router_func = Router()
API_URL = "http://127.0.0.1:8001"

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEDIA_ROOT = os.path.join(BASE_DIR, "media")
DEFAULT_IMAGE_PATH = os.path.join(MEDIA_ROOT, "product_images/default.jpeg")
LOGO = os.path.join(MEDIA_ROOT, "logo.png")


class OrderState(StatesGroup):
    choosing_category = State()
    choosing_product = State()
    choosing_quantity = State()
    choosing_promotion = State()
    choosing_promotion_detail = State()  # ← Новое состояние


def get_main_keyboard_multilang(language: str = "ru") -> ReplyKeyboardMarkup:
    if language == "ru":
        keyboard = [
            [KeyboardButton(text="🍽 Меню")],
            [KeyboardButton(text="🧺 Моя корзина")],
            [KeyboardButton(text="📞 Контакты")],
            [KeyboardButton(text="⚙ Настройки")],
        ]
    elif language == "uz":
        keyboard = [
            [KeyboardButton(text="🍽 Menyu")],
            [KeyboardButton(text="🧺 Savatim")],
            [KeyboardButton(text="📞 Kontaktlar")],
            [KeyboardButton(text="⚙ Sozlamalar")],
        ]
    elif language == "en":
        keyboard = [
            [KeyboardButton(text="🍽 Menu")],
            [KeyboardButton(text="🧺 My cart")],
            [KeyboardButton(text="📞 Contacts")],
            [KeyboardButton(text="⚙ Settings")],
        ]
    else:
        # По умолчанию русский
        keyboard = [
            [KeyboardButton(text="🍽 Меню")],
            [KeyboardButton(text="🧺 Моя корзина")],
            [KeyboardButton(text="📞 Контакты")],
            [KeyboardButton(text="⚙ Настройки")],
        ]

    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


async def show_menu(message: Message, state: FSMContext = None) -> None:
    user_id = message.from_user.id

    # 1. Пробуем получить язык из FSM
    lang = None
    if state:
        data = await state.get_data()
        lang = data.get("language")

    # 2. Если нет в FSM — пробуем из файла
    if not lang:
        lang = get_language(user_id)

    # 3. Выбираем текст по языку
    if lang == "uz":
        text = "📋 Asosiy menyu"
    elif lang == "en":
        text = "📋 Main menu"
    else:
        text = "📋 Главное меню"

    # 4. Клавиатура
    keyboard = get_main_keyboard_multilang(lang)

    # 5. Ответ
    await message.answer(text, reply_markup=keyboard)


@router_func.message(F.text.in_(["🍽 Меню", "🍽 Menyu", "🍽 Menu"]))
async def handle_order(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id

    # 1. Получение языка из FSM или файла
    data = await state.get_data()
    lang = data.get("language") or get_language(user_id)

    # 2. Получаем категории
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{API_URL}/categories/")
        if response.status_code == 200:
            categories = response.json()
            if categories:
                keyboard = ReplyKeyboardMarkup(
                    keyboard=[[KeyboardButton(text=c["name"])] for c in categories]
                    + [
                        [
                            KeyboardButton(
                                text=(
                                    "⬅ Назад"
                                    if lang == "ru"
                                    else "⬅ Orqaga" if lang == "uz" else "⬅ Back"
                                ),
                            ),
                        ],
                    ],
                    resize_keyboard=True,
                )
                await state.update_data(categories=categories)
                await state.set_state(OrderState.choosing_category)

                # Мультиязычное сообщение
                if lang == "uz":
                    text = "📚 Kategoriyani tanlang:"
                elif lang == "en":
                    text = "📚 Choose a category:"
                else:
                    text = "📚 Выберите категорию:"

                await message.answer(text, reply_markup=keyboard)
            else:
                await message.answer(
                    (
                        "❗ Mavjud kategoriyalar yo‘q."
                        if lang == "uz"
                        else (
                            "❗ No categories available."
                            if lang == "en"
                            else "❗ Нет доступных категорий."
                        )
                    ),
                )
        else:
            await message.answer(
                (
                    "⚠️ Kategoriyalarni yuklashda xatolik."
                    if lang == "uz"
                    else (
                        "⚠️ Error loading categories."
                        if lang == "en"
                        else "⚠️ Ошибка при получении категорий."
                    )
                ),
            )


@router_func.message(OrderState.choosing_category)
async def choose_category(message: Message, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    lang = data.get("language") or get_language(user_id)

    # Проверка на "Назад"
    if message.text in ["⬅ Назад", "⬅ Orqaga", "⬅ Back"]:
        await state.clear()
        return await show_menu(message)

    categories = data.get("categories", [])
    selected = next((c for c in categories if c["name"] == message.text), None)

    if not selected:
        return await message.answer(
            (
                "❗ Noto‘g‘ri kategoriya. Ro‘yxatdan tanlang."
                if lang == "uz"
                else (
                    "❗ Invalid category. Please choose from the list."
                    if lang == "en"
                    else "❗ Неверная категория. Пожалуйста, выберите из списка."
                )
            ),
        )

    category_id = selected["id"]
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{API_URL}/products/{category_id}/")
        if response.status_code == 200:
            products = response.json()
            if not products:
                return await message.answer(
                    (
                        "📭 Bu kategoriyada mahsulotlar yo‘q."
                        if lang == "uz"
                        else (
                            "📭 No products in this category."
                            if lang == "en"
                            else "📭 Нет продуктов в этой категории."
                        )
                    ),
                )

            await state.update_data(products=products)
            await state.set_state(OrderState.choosing_product)

            back_text = (
                "⬅ Orqaga" if lang == "uz" else "⬅ Back" if lang == "en" else "⬅ Назад"
            )
            keyboard = ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text=p["name"])] for p in products]
                + [[KeyboardButton(text=back_text)]],
                resize_keyboard=True,
            )

            choose_text = (
                "📦 Mahsulotni tanlang:"
                if lang == "uz"
                else "📦 Choose a product:" if lang == "en" else "📦 Выберите продукт:"
            )

            await message.answer(choose_text, reply_markup=keyboard)
            return None
        return await message.answer(
            (
                "❌ Mahsulotlarni olishda xatolik."
                if lang == "uz"
                else (
                    "❌ Failed to fetch products."
                    if lang == "en"
                    else "❌ Ошибка при получении продуктов."
                )
            ),
        )


@router_func.message(OrderState.choosing_product)
async def choose_product(message: Message, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    lang = data.get("language") or get_language(user_id)

    if message.text in ["⬅ Назад", "⬅ Orqaga", "⬅ Back"]:
        await state.set_state(OrderState.choosing_category)
        return await handle_order(message, state)

    products = data.get("products", [])
    selected = next((p for p in products if p["name"] == message.text), None)

    if not selected:
        return await message.answer(
            (
                "❗ Noto‘g‘ri mahsulot. Ro‘yxatdan tanlang."
                if lang == "uz"
                else (
                    "❗ Invalid product. Please choose from the list."
                    if lang == "en"
                    else "❗ Неверный товар. Пожалуйста, выберите из списка."
                )
            ),
        )

    await state.update_data(selected_product=selected, quantity=1)

    # Удалить клавиатуру и сообщение
    temp = await message.answer("🔄", reply_markup=ReplyKeyboardRemove())
    await temp.delete()

    # Показать карточку товара
    await send_product_preview(message, selected, quantity=1, state=state)
    return None


async def send_product_preview(
    message: Message,
    product: dict,
    quantity: int,
    state: FSMContext,
) -> None:
    data = await state.get_data()
    user_id = message.from_user.id
    lang = data.get("language") or get_language(user_id)

    image_url_or_path = product.get("image")
    discount = product.get("discount_percent", 0)
    price = float(product["price"])

    if discount > 0:
        new_price = price * (1 - discount / 100)
        caption = {
            "ru": (
                f"<b>{product['name']}</b>\n"
                f"💥 <i>Скидка {discount}%</i>\n"
                f"💵 Цена: ~{price:.2f}~ → <b>{new_price:.2f}</b> сум\n"
                f"🧮 Кол-во: {quantity}"
            ),
            "uz": (
                f"<b>{product['name']}</b>\n"
                f"💥 <i>Chegirma {discount}%</i>\n"
                f"💵 Narx: ~{price:.2f}~ → <b>{new_price:.2f}</b> so‘m\n"
                f"🧮 Miqdor: {quantity}"
            ),
            "en": (
                f"<b>{product['name']}</b>\n"
                f"💥 <i>Discount {discount}%</i>\n"
                f"💵 Price: ~{price:.2f}~ → <b>{new_price:.2f}</b> UZS\n"
                f"🧮 Quantity: {quantity}"
            ),
        }.get(lang, "")
    else:
        caption = {
            "ru": (
                f"<b>{product['name']}</b>\n"
                f"💵 Цена: {price:.2f} сум\n"
                f"🧮 Кол-во: {quantity}"
            ),
            "uz": (
                f"<b>{product['name']}</b>\n"
                f"💵 Narx: {price:.2f} so‘m\n"
                f"🧮 Miqdor: {quantity}"
            ),
            "en": (
                f"<b>{product['name']}</b>\n"
                f"💵 Price: {price:.2f} UZS\n"
                f"🧮 Quantity: {quantity}"
            ),
        }.get(lang, "")

    # Фото
    try:
        if image_url_or_path and image_url_or_path.startswith("http"):
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url_or_path) as resp:
                    if resp.status == 200:
                        with NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
                            tmp.write(await resp.read())
                            photo_path = tmp.name
                    else:
                        photo_path = DEFAULT_IMAGE_PATH
        else:
            photo_path = (
                os.path.normpath(os.path.join(MEDIA_ROOT, image_url_or_path))
                if image_url_or_path
                else DEFAULT_IMAGE_PATH
            )
            if not os.path.isfile(photo_path):
                photo_path = DEFAULT_IMAGE_PATH

        photo = FSInputFile(photo_path)
    except Exception:
        photo = FSInputFile(DEFAULT_IMAGE_PATH)

    # Кнопки по языкам
    add_text = {"ru": "🛒 Добавить", "uz": "🛒 Qo‘shish", "en": "🛒 Add"}[lang]
    back_text = {"ru": "⬅ Назад", "uz": "⬅ Orqaga", "en": "⬅ Back"}[lang]

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="➖", callback_data="decrease"),
                InlineKeyboardButton(text=str(quantity), callback_data="noop"),
                InlineKeyboardButton(text="➕", callback_data="increase"),
            ],
            [InlineKeyboardButton(text=add_text, callback_data="addtocart")],
            [InlineKeyboardButton(text=back_text, callback_data="go_back")],
        ],
    )

    await message.answer_photo(
        photo=photo,
        caption=caption,
        reply_markup=keyboard,
        parse_mode="HTML",
    )


from .utils import get_language


@router_func.callback_query(F.data == "go_back")
async def go_back_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.delete()
    await state.set_state(OrderState.choosing_product)

    user_id = callback.from_user.id
    data = await state.get_data()
    products = data.get("products", [])
    lang = data.get("language") or get_language(user_id)

    # Переводы
    choose_text = {
        "ru": "📦 Выберите продукт:",
        "uz": "📦 Mahsulotni tanlang:",
        "en": "📦 Choose a product:",
    }.get(lang, "📦 Выберите продукт:")

    not_found_text = {
        "ru": "❌ Продукты не найдены.",
        "uz": "❌ Mahsulotlar topilmadi.",
        "en": "❌ Products not found.",
    }.get(lang, "❌ Продукты не найдены.")

    back_button_text = {"ru": "⬅ Назад", "uz": "⬅ Orqaga", "en": "⬅ Back"}.get(
        lang,
        "⬅ Назад",
    )

    if products:
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=p["name"])] for p in products]
            + [[KeyboardButton(text=back_button_text)]],
            resize_keyboard=True,
        )
        await callback.message.answer(choose_text, reply_markup=keyboard)
    else:
        await callback.message.answer(not_found_text)


@router_func.callback_query(F.data.in_(["increase", "decrease", "addtocart"]))
async def handle_quantity_buttons(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    product = data.get("selected_product")
    quantity = data.get("quantity", 1)
    lang = data.get("language") or get_language(call.from_user.id)

    # Переводы
    phone_missing = {
        "ru": "📱 Укажите номер в ⚙ Настройки",
        "uz": "📱 ⚙ Sozlamalardan raqamni kiriting",
        "en": "📱 Please enter your phone in ⚙ Settings",
    }.get(lang, "📱 Укажите номер в ⚙ Настройки")

    success_text = {
        "ru": "✅ Товар добавлен в корзину",
        "uz": "✅ Mahsulot savatga qo‘shildi",
        "en": "✅ Product added to cart",
    }.get(lang, "✅ Товар добавлен в корзину")

    error_text = {
        "ru": "❌ Ошибка при добавлении в корзину.",
        "uz": "❌ Savatga qo‘shishda xatolik yuz berdi.",
        "en": "❌ Error adding product to cart.",
    }.get(lang, "❌ Ошибка при добавлении в корзину.")

    if call.data == "increase":
        quantity += 1
    elif call.data == "decrease":
        quantity = max(1, quantity - 1)
    elif call.data == "addtocart":
        phone = await get_user_phone(call.message, state)
        if not phone:
            return await call.message.answer(phone_missing)

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{API_URL}/cart/add/",
                json={"phone": phone, "product_id": product["id"], "quantity": quantity},
            )

        if response.status_code == 200:
            await call.message.edit_reply_markup()
            await call.message.answer(
                success_text,
                reply_markup=get_main_keyboard_multilang(lang),
            )
        else:
            await call.message.answer(error_text)

        await state.clear()
        await state.update_data(language=lang, phone=phone)

        return None
    await state.update_data(quantity=quantity)
    await call.message.delete()
    await send_product_preview(call.message, product, quantity, state)
    await call.answer()
    return None


@router_func.message(F.text.in_(["🧺 Моя корзина", "🧺 Savatim", "🧺 My cart"]))
async def handle_cart(message: Message, state: FSMContext):
    phone = await get_user_phone(message, state)
    if not phone:
        return await message.answer(
            {
                "ru": "❗ Пожалуйста, укажите номер.",
                "uz": "❗ Iltimos, telefon raqamingizni kiriting.",
                "en": "❗ Please enter your phone number.",
            }.get(await get_user_lang(state, message.from_user.id), "❗ Ошибка"),
        )

    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(f"{API_URL}/cart/{phone}/")

    lang = await get_user_lang(state, message.from_user.id)

    if response.status_code != 200:
        return await message.answer(
            {
                "ru": "❌ Ошибка при получении корзины.",
                "uz": "❌ Savatchani yuklashda xatolik.",
                "en": "❌ Failed to load your cart.",
            }.get(lang, "❌ Ошибка"),
        )

    data = response.json()
    items = data.get("items", [])
    total = data.get("total_price", 0)

    if not items:
        return await message.answer(
            {
                "ru": "🧺 Ваша корзина пуста.",
                "uz": "🧺 Savatchangiz bo‘sh.",
                "en": "🧺 Your cart is empty.",
            }.get(lang, "🧺 Ваша корзина пуста."),
        )

    # Названия и оформление
    headers = {
        "ru": f"🧺 Ваша корзина ({phone}):\n",
        "uz": f"🧺 Savatchangiz ({phone}):\n",
        "en": f"🧺 Your cart ({phone}):\n",
    }

    currency = "so'm" if lang == "uz" else "сум"

    text = headers.get(lang, headers["ru"])

    for item in items:
        name = strip_emojis(item["name"])[:25]
        quantity = item["quantity"]
        price = float(item["price"])
        discount = float(item.get("discount_percent", 0))

        if discount > 0:
            discounted_price = price * (1 - discount / 100)
            subtotal = quantity * discounted_price
            text += (
                f"• {name} x{quantity} = {subtotal:.2f} {currency}\n"
                f"  <i>💥 {discount}% {price:.2f} → {discounted_price:.2f}</i>\n"
            )
        else:
            subtotal = quantity * price
            text += f"• {name} x{quantity} = {subtotal:.2f} {currency}\n"

    total_label = {
        "ru": "💰 <b>Итого:</b>",
        "uz": "💰 <b>Jami:</b>",
        "en": "💰 <b>Total:</b>",
    }.get(lang, "💰 <b>Итого:</b>")

    text += f"\n{total_label} <code>{total:.2f}</code> {currency}\n"

    order_button_text = {
        "ru": "🛒 Оформить заказ",
        "uz": "🛒 Buyurtma berish",
        "en": "🛒 Place Order",
    }.get(lang, "🛒 Оформить заказ")

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=order_button_text, callback_data="make_order")],
        ],
    )

    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    return None


ADMIN_CHAT_IDS = [7591006387]


class PDF(FPDF):
    def __init__(self) -> None:
        super().__init__(format=(80, 300))  # 80 мм ширина, высота авто
        font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        self.add_font("DejaVu", "", font_path, uni=True)
        self.set_font("DejaVu", "", 9)  # чуть меньше шрифт
        self.set_auto_page_break(auto=True, margin=10)
        self.add_page()

    def line_text(self, text: str, h=5) -> None:
        self.cell(0, h, text, ln=True, align="C")  # ВСЕГДА ПО ЦЕНТРУ


def strip_emojis(text: str) -> str:
    return re.sub(r"[^\w\s.,:;!?()%/\-+№\"\'=А-Яа-яёЁ]", "", text)


def split_message(text: str, max_length: int = 4000) -> list[str]:
    parts = []
    while len(text) > max_length:
        split_index = text.rfind("\n", 0, max_length)
        if split_index == -1:
            split_index = max_length
        parts.append(text[:split_index].strip())
        text = text[split_index:].strip()
    parts.append(text)
    return parts


async def restore_basic_context(state: FSMContext, lang: str, phone: str) -> None:
    await state.clear()
    await state.update_data(language=lang, phone=phone)


@router_func.callback_query(F.data == "make_order")
async def process_order(call: CallbackQuery, state: FSMContext):
    lang = await get_user_lang(state, call.from_user.id)
    phone = await get_user_phone(call.message, state)
    if not phone:
        return await call.message.answer(
            {
                "ru": "❗ Пожалуйста, укажите номер.",
                "uz": "❗ Iltimos, telefon raqamingizni kiriting.",
                "en": "❗ Please enter your phone number.",
            }.get(lang, "❗ Ошибка"),
        )

    async with httpx.AsyncClient(timeout=5.0) as client:
        order_response = await client.post(f"{API_URL}/order/", json={"phone": phone})
        if order_response.status_code != 200:
            try:
                error = order_response.json().get(
                    "error",
                    {
                        "ru": "Произошла ошибка.",
                        "uz": "Xatolik yuz berdi.",
                        "en": "An error occurred.",
                    }[lang],
                )
            except Exception:
                error = {
                    "ru": "Не удалось создать заказ. Попробуйте позже.",
                    "uz": "Buyurtma yaratilmadi. Keyinroq urinib ko‘ring.",
                    "en": "Could not create order. Try again later.",
                }[lang]
            return await call.message.answer(f"❌ {error}")

        order_data = order_response.json()
        order_id = order_data["order_id"]
        total = order_data["total"]
        items = order_data.get("items", [])

        company_response = await client.get("http://127.0.0.1:8000/company/1/")
        if company_response.status_code == 200:
            company = company_response.json()
            company_name = company.get(
                "name",
                {"ru": "Компания", "uz": "Kompaniya", "en": "Company"}[lang],
            )
            company_phone = company.get("phone", "N/A")
        else:
            company_name = {"ru": "Компания", "uz": "Kompaniya", "en": "Company"}[lang]
            company_phone = "N/A"

    # Чек — текст

    lines = [
        {"ru": "🧾 Ваш заказ\n", "uz": "🧾 Buyurtmangiz\n", "en": "🧾 Your order\n"}[
            lang
        ],
        f"🏢 {company_name}",
        f"📞 +998 {company_phone}",
        f"📱 Номер клиента {order_data.get('phone', phone)}",
        "-" * 30,
        {
            "ru": f"📦 Заказ №: {order_id}",
            "uz": f"📦 Buyurtma raqami: {order_id}",
            "en": f"📦 Order ID: {order_id}",
        }[lang],
        f"🕓 {datetime.now().strftime('%d.%m.%Y %H:%M')}",
        "-" * 30,
        {"ru": "🛍 Товары:", "uz": "🛍 Mahsulotlar:", "en": "🛍 Products:"}[lang],
    ]

    for item in items:
        name = item["name"]
        quantity = item["quantity"]
        price = float(item["price"])
        discount = float(item.get("discount_percent", 0))
        if discount > 0:
            new_price = price * (1 - discount / 100)
            subtotal = quantity * new_price
            lines.append(
                f"• {name} x{quantity} = {subtotal:.2f} сум\n  💥 {discount}%: {price:.2f} → {new_price:.2f}",
            )
        else:
            subtotal = quantity * price
            lines.append(f"• {name} x{quantity} = {subtotal:.2f} сум")

    lines.append("-" * 30)
    lines.append(
        {
            "ru": f"💰 Итого: {total:.2f} сум",
            "uz": f"💰 Jami: {total:.2f} so'm",
            "en": f"💰 Total: {total:.2f} sum",
        }[lang],
    )
    lines.append(
        {
            "ru": "🙏 Спасибо за заказ!",
            "uz": "🙏 Buyurtma uchun rahmat!",
            "en": "🙏 Thank you for your order!",
        }[lang],
    )

    # Удалить клавиатуру, если она есть
    if call.message.reply_markup:
        await call.message.edit_reply_markup(reply_markup=None)

    # Отправка чека
    for part in split_message("\n".join(lines)):
        await call.message.answer(part)

    # Подпись
    await call.message.answer(
        {
            "ru": "📋 Выше — ваш чек.",
            "uz": "📋 Yuqorida — chekingiz.",
            "en": "📋 Here's your receipt above.",
        }[lang],
        reply_markup=get_main_keyboard_multilang(lang),
    )

    # Генерация PDF чека
    pdf = PDF()
    logo = LOGO
    pdf.image(logo, x=(80 - 40) / 2, w=40)
    pdf.ln(3)
    pdf.line_text("КАССОВЫЙ ЧЕК / CHIQARILGAN CHEK / RECEIPT", 6)
    pdf.line_text("-" * 66)
    pdf.line_text(strip_emojis(company_name))
    pdf.line_text(f"Тел.: +998 {company_phone}")
    pdf.line_text(f"Клиент: {order_data.get('phone', phone)}")
    pdf.line_text(f"№: {order_id}")
    pdf.line_text(datetime.now().strftime("%d.%m.%Y %H:%M"))
    pdf.line_text("-" * 66)
    pdf.line_text("Товары / Mahsulotlar / Products:")

    for item in items:
        name = strip_emojis(item["name"])[:25]
        quantity = item["quantity"]
        price = float(item["price"])
        discount = float(item.get("discount_percent", 0))
        if discount > 0:
            new_price = price * (1 - discount / 100)
            subtotal = quantity * new_price
            pdf.line_text(f"{name} x{quantity} = {subtotal:.2f}")
            pdf.line_text(f"Скидка {discount}%: {price:.2f} → {new_price:.2f}")
        else:
            subtotal = quantity * price
            pdf.line_text(f"{name} x{quantity} = {subtotal:.2f}")

    pdf.line_text("-" * 66)
    pdf.line_text(f"ИТОГО: {total:.2f} сум")
    pdf.line_text("СПАСИБО ЗА ВНИМАНИЕ")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        pdf_path = tmp_file.name
        pdf.output(pdf_path)

    pdf_filename = f"order_{order_id}.pdf"
    pdf_path = os.path.join(tempfile.gettempdir(), pdf_filename)
    pdf.output(pdf_path)

    for admin_id in ADMIN_CHAT_IDS:
        try:
            await call.bot.send_document(
                admin_id,
                FSInputFile(pdf_path),
                caption="📥 Новый заказ (PDF чек)",
            )
        except Exception as e:
            print(f"Ошибка отправки PDF админу {admin_id}: {e}")

    os.remove(pdf_path)
    await restore_basic_context(state, lang, phone)
    return None


@router_func.message(F.text.in_(["📞 Контакты", "📞 Kontaktlar", "📞 Contacts"]))
async def handle_contacts(message: Message, state: FSMContext) -> None:
    lang = await get_user_lang(state, message.from_user.id)

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get("http://127.0.0.1:8000/company/1/")

        if response.status_code == 200:
            company = response.json()
            company_name = (
                company.get("name")
                or {"ru": "Компания", "uz": "Kompaniya", "en": "Company"}[lang]
            )
            company_phone = company.get("phone") or "N/A"
        else:
            print("Ошибка при получении компании: код", response.status_code)
            company_name = {"ru": "Компания", "uz": "Kompaniya", "en": "Company"}[lang]
            company_phone = "N/A"

    except Exception as e:
        print("❌ Ошибка запроса компании:", e)
        company_name = {"ru": "Компания", "uz": "Kompaniya", "en": "Company"}[lang]
        company_phone = "N/A"

    contact_texts = {
        "ru": (
            "📞 <b>Контактная информация</b>\n\n"
            f"🏢 <b>{company_name}</b>\n"
            f"📱 Телефон: <code>+998 {company_phone}</code>\n\n"
            "💬 Мы всегда на связи!"
        ),
        "uz": (
            "📞 <b>Aloqa ma'lumotlari</b>\n\n"
            f"🏢 <b>{company_name}</b>\n"
            f"📱 Telefon: <code>+998 {company_phone}</code>\n\n"
            "💬 Biz doimo aloqadamiz!"
        ),
        "en": (
            "📞 <b>Contact Information</b>\n\n"
            f"🏢 <b>{company_name}</b>\n"
            f"📱 Phone: <code>+998 {company_phone}</code>\n\n"
            "💬 We are always in touch!"
        ),
    }

    await message.answer(contact_texts[lang], parse_mode="HTML")


def get_settings_keyboard(lang: str) -> InlineKeyboardMarkup:
    texts = {
        "ru": {
            "lang": "🔄 Поменять язык",
            "phone": "☎️ Изменить номер",
            "back": "🔙 Назад",
        },
        "uz": {
            "lang": "🔄 Tilni o‘zgartirish",
            "phone": "☎️ Raqamni o‘zgartirish",
            "back": "🔙 Orqaga",
        },
        "en": {
            "lang": "🔄 Change language",
            "phone": "☎️ Change phone",
            "back": "🔙 Back",
        },
    }

    t = texts.get(lang, texts["ru"])
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t["lang"], callback_data="change_language")],
            [InlineKeyboardButton(text=t["phone"], callback_data="change_phone")],
            [InlineKeyboardButton(text=t["back"], callback_data="back_to_main")],
        ],
    )


@router_func.callback_query(F.data == "back_to_main")
async def back_to_main_menu(call: CallbackQuery, state: FSMContext) -> None:
    lang = await get_user_lang(state, call.from_user.id)
    await call.message.delete()
    await call.message.answer("🔙", reply_markup=get_main_keyboard_multilang(lang))
    await call.answer()


def get_language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru"),
                InlineKeyboardButton(text="🇺🇿 O‘zbek", callback_data="lang_uz"),
                InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en"),
            ],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_settings")],
        ],
    )


@router_func.callback_query(F.data == "back_to_settings")
async def back_to_settings(call: CallbackQuery, state: FSMContext) -> None:
    lang = await get_user_lang(state, call.from_user.id)

    await call.message.edit_text(
        {"ru": "⚙ Настройки", "uz": "⚙ Sozlamalar", "en": "⚙ Settings"}[lang],
        reply_markup=get_settings_keyboard(lang),
    )
    await call.answer()


@router_func.message(
    F.text.in_({"/settings", "⚙ Настройки", "⚙ Sozlamalar", "⚙ Settings"}),
)
async def settings_handler(msg: Message, state: FSMContext) -> None:
    lang = await get_user_lang(state, msg.from_user.id)

    # Удаляем клавиатуру (если нужно)
    await msg.answer(
        "Вы перешли в настройки",
        reply_markup=ReplyKeyboardRemove(),
    )  # скрывает обычную клавиатуру

    # Показываем настройки с инлайн-кнопками
    await msg.answer(
        {"ru": "⚙ Настройки", "uz": "⚙ Sozlamalar", "en": "⚙ Settings"}[lang],
        reply_markup=get_settings_keyboard(lang),
    )


@router_func.callback_query(F.data == "change_language")
async def change_language_handler(call: CallbackQuery, state: FSMContext) -> None:
    await call.message.edit_text(
        "🌐 Выберите язык / Tilni tanlang / Select language:",
        reply_markup=get_language_keyboard(),
    )
    await call.bot.send_chat_action(call.from_user.id, "typing")

    await call.answer()


@router_func.callback_query(F.data.startswith("lang_"))
async def set_language_handler(call: CallbackQuery, state: FSMContext) -> None:
    lang_code = call.data.split("_")[1]
    user_id = call.from_user.id
    phone = get_phone(user_id) or ""

    save_phone(user_id, phone, lang_code)
    await state.update_data(language=lang_code)

    confirmation = {
        "ru": "✅ Язык изменён на русский",
        "uz": "✅ Til o‘zbek tiliga o‘zgartirildi",
        "en": "✅ Language changed to English",
    }

    await call.message.edit_text(
        confirmation[lang_code],
        reply_markup=get_settings_keyboard(lang_code),
    )
    await call.answer()


@router_func.callback_query(F.data == "change_phone")
async def change_phone_handler(call: CallbackQuery, state: FSMContext) -> None:
    lang = await get_user_lang(state, call.from_user.id)

    text = {
        "ru": "📲 Пожалуйста, нажмите кнопку ниже, чтобы поделиться своим номером.",
        "uz": "📲 Iltimos, raqamingizni yuborish uchun tugmani bosing.",
        "en": "📲 Please tap the button below to share your phone number.",
    }[lang]

    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Поделиться номером", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

    await call.message.delete()
    await call.message.answer(text, reply_markup=keyboard)
    await call.answer()


@router_func.message(F.contact)
async def process_contact(msg: Message, state: FSMContext) -> None:
    contact = msg.contact
    user_id = msg.from_user.id
    phone = contact.phone_number

    lang = await get_user_lang(state, user_id)
    save_phone(user_id, phone, lang)
    await state.update_data(phone=phone)

    confirmation = {
        "ru": f"✅ Номер сохранён: {phone}",
        "uz": f"✅ Raqam saqlandi: {phone}",
        "en": f"✅ Phone saved: {phone}",
    }[lang]

    await msg.answer(confirmation, reply_markup=get_main_keyboard_multilang(lang))
