from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

from .bot_func import show_menu  # меню одно, и само проверяет язык
from .utils import get_language, get_phone, save_phone  # ← функции для хранения

if TYPE_CHECKING:
    from aiogram.fsm.context import FSMContext

router = Router()


# --- FSM состояния
class RegState(StatesGroup):
    choosing_language = State()
    waiting_for_phone = State()


# --- /start


@router.message(Command("start"))
async def start_registration(message: Message, state: FSMContext):
    user_id = message.from_user.id
    phone = get_phone(user_id)
    lang = get_language(user_id)

    if phone and lang:
        await state.update_data(phone=phone)
        await state.update_data(language=lang)

        return await show_menu(message)  # ← просто один вызов

    # Если язык не выбран — предложим выбрать
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🇷🇺 Русский"), KeyboardButton(text="🇺🇿 O‘zbek")],
            [KeyboardButton(text="🇬🇧 English")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

    await message.answer(
        "🌐 Пожалуйста, выберите язык:\n"
        "🌐 Iltimos, tilni tanlang:\n"
        "🌐 Please choose your language:",
        reply_markup=keyboard,
    )
    await state.set_state(RegState.choosing_language)
    return None


# --- Обработка выбора языка
@router.message(RegState.choosing_language)
async def handle_language_choice(message: Message, state: FSMContext):
    lang_map = {"🇷🇺 Русский": "ru", "🇺🇿 O‘zbek": "uz", "🇬🇧 English": "en"}

    lang_code = lang_map.get(message.text)
    if not lang_code:
        return await message.answer(
            "❗ Пожалуйста, выберите язык из списка.\n"
            "❗ Iltimos, roʻyxatdan tanlang.\n"
            "❗ Please choose from the list.",
        )

    await state.update_data(language=lang_code)

    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📲 Отправить номер", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

    if lang_code == "ru":
        text = "📲 Пожалуйста, отправьте ваш номер телефона:"
    elif lang_code == "uz":
        text = "📲 Iltimos, telefon raqamingizni yuboring:"
    else:
        text = "📲 Please send your phone number:"

    await message.answer(text, reply_markup=keyboard)
    await state.set_state(RegState.waiting_for_phone)
    return None


@router.message(F.contact, RegState.waiting_for_phone)
async def handle_contact(message: Message, state: FSMContext):
    user_id = message.from_user.id
    phone = message.contact.phone_number
    data = await state.get_data()
    language = data.get("language", "ru")  # ← language, не lang

    save_phone(user_id, phone, language)
    await state.update_data(phone=phone)
    await state.update_data(language=language)
    await state.clear()

    return await show_menu(message)  # просто вызываем общее меню
