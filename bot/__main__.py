from __future__ import annotations

import asyncio
import logging.config
import sys
from datetime import datetime, time

import httpx
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import BotCommand

from bot.config.bot import RUNNING_MODE, TELEGRAM_API_TOKEN, RunningMode
from bot.handlers import router

from .bot_func import router_func

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)
logging.getLogger("aiogram").setLevel(logging.WARNING)
logging.getLogger("django").setLevel(logging.WARNING)


logger = logging.getLogger(__name__)

bot = Bot(TELEGRAM_API_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))

dispatcher = Dispatcher()
dispatcher.include_router(router)
dispatcher.include_router(router_func)

is_bot_active = True


async def set_bot_commands() -> None:
    await bot.set_my_commands(
        [
            BotCommand(command="/start", description="Запустить бота"),
        ],
    )


async def monitor_bot_activity() -> None:
    global is_bot_active

    while True:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get("http://127.0.0.1:8000/company/1/")
                if response.status_code == 200:
                    data = response.json()
                    is_active = (
                        data.get("subscription_expires_at") > datetime.now().isoformat()
                    )

                    work_start_str = data.get("work_start")
                    work_end_str = data.get("work_end")

                    now_time = datetime.now().time()

                    # Преобразуем строки времени в объекты time
                    if work_start_str and work_end_str:
                        work_start = time.fromisoformat(work_start_str)
                        work_end = time.fromisoformat(work_end_str)

                        in_working_hours = work_start <= now_time <= work_end
                    else:
                        in_working_hours = (
                            True  # если не указано — считаем всегда рабочим
                        )

                    if not (is_active and in_working_hours):
                        if is_bot_active:
                            logger.warning(
                                "🚫 Бот отключён: подписка неактивна или вне рабочего времени.",
                            )
                            is_bot_active = False
                            await asyncio.sleep(
                                60,
                            )  # 1 минута ожидания перед повторной проверкой
                    elif not is_bot_active:
                        logger.info("✅ Бот снова активен.")
                        is_bot_active = True
                else:
                    logger.warning(
                        f"⚠️ Ошибка запроса к /company/1/: статус {response.status_code}",
                    )
        except Exception as e:
            logger.exception(f"Ошибка при проверке активности: {e}")

        await asyncio.sleep(300)


# Middleware для блокировки событий при отключении
from typing import TYPE_CHECKING, Any, Callable

from aiogram.dispatcher.middlewares.base import BaseMiddleware
from aiogram.types import TelegramObject

if TYPE_CHECKING:
    from collections.abc import Awaitable


class BotActiveMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not is_bot_active:
            logger.info("⛔ Обработка события отклонена: бот временно отключён.")
            return None  # Ничего не делаем
        return await handler(event, data)


dispatcher.message.middleware(BotActiveMiddleware())
dispatcher.callback_query.middleware(BotActiveMiddleware())


@dispatcher.startup()
async def on_startup() -> None:
    await set_bot_commands()
    logger.info("✅ Бот запущен.")
    asyncio.create_task(monitor_bot_activity())
    # asyncio.create_task(notify_admins_new_orders(bot))


def run_polling() -> None:
    loop = asyncio.get_event_loop()
    loop.create_task(monitor_bot_activity())  # запускаем мониторинг до polling
    dispatcher.run_polling(bot)


def run_webhook() -> None:
    msg = "Webhook mode is not implemented yet"
    raise NotImplementedError(msg)


if __name__ == "__main__":
    if RUNNING_MODE == RunningMode.LONG_POLLING:
        run_polling()
    elif RUNNING_MODE == RunningMode.WEBHOOK:
        run_webhook()
    else:
        logger.error("Unknown running mode")
        sys.exit(1)
