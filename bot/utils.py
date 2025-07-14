from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aiogram.fsm.context import FSMContext

PHONE_STORAGE_FILE = "phone_numbers.json"


def load_phones():
    if os.path.exists(PHONE_STORAGE_FILE):
        with open(PHONE_STORAGE_FILE) as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                print(
                    "[LOAD_PHONES] JSON файл повреждён или пуст — возвращаем пустой словарь",
                )
                return {}
    return {}


def save_phone(user_id: int, phone: str, language: str = "ru") -> None:
    phones = load_phones()
    phones[str(user_id)] = {"phone": phone, "language": language}
    with open(PHONE_STORAGE_FILE, "w") as f:
        json.dump(phones, f, ensure_ascii=False, indent=2)


def get_phone(user_id: int):
    phones = load_phones()
    entry = phones.get(str(user_id))
    if entry:
        return entry.get("phone")
    print(f"[GET_PHONE] Not found for user {user_id}")
    return None


def get_language(user_id: int):
    phones = load_phones()
    entry = phones.get(str(user_id))
    if entry:
        return entry.get("language", "ru")
    print(f"[GET_LANG] Not found for user {user_id}, defaulting to 'ru'")
    return "ru"


async def get_user_phone(source, state: FSMContext):
    data = await state.get_data()
    phone = data.get("phone")
    if phone:
        return phone

    try:
        user_id = source.from_user.id
    except AttributeError:
        user_id = source.message.from_user.id

    return get_phone(user_id)


async def get_user_lang(state: FSMContext, user_id: int):
    data = await state.get_data()
    return data.get("language") or get_language(user_id) or "ru"
