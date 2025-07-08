"""
Главный файл клиентского бота VPN Bot System
"""

import asyncio
import sys
from pathlib import Path

# Добавляем корневую директорию в путь
sys.path.append(str(Path(__file__).parent.parent.parent))

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from loguru import logger

from config.settings import settings
from config.database import init_database, init_redis, close_connections
from bots.shared.middleware.database import DatabaseMiddleware
from bots.shared.middleware.logging import LoggingMiddleware
from bots.client.middleware.auth import AuthMiddleware
from bots.client.middleware.subscription import SubscriptionMiddleware
from bots.client.middleware.throttling import ThrottlingMiddleware

# Импорт хэндлеров
from bots.client.handlers import (
    start, subscription, profile, servers, 
    support, payment, configs
)


class ClientBot:
    """Класс клиентского бота"""
    
    def __init__(self):
        self.bot = None
        self.dp = None
        self.storage = None
    
    async def setup_bot(self):
        """Настройка бота"""
        try:
            # Создаем бота
            self.bot = Bot(
                token=settings.CLIENT_BOT_TOKEN,
                default=DefaultBotProperties(parse_mode=ParseMode.HTML)
            )
            
            # Настраиваем Redis storage для FSM
            redis_url = settings.REDIS_URL
            self.storage = RedisStorage.from_url(redis_url)
            
            # Создаем диспетчер
            self.dp = Dispatcher(storage=self.storage)
            
            logger.info("Client bot configured successfully")
            
        except Exception as e:
            logger.error(f"Error setting up client bot: {e}")
            raise
    
    async def setup_middleware(self):
        """Настройка middleware"""
        try:
            # Middleware для логирования (первым)
            self.dp.update.middleware(LoggingMiddleware())
            
            # Middleware для базы данных
            self.dp.update.middleware(DatabaseMiddleware())
            
            # Middleware для аутентификации
            self.dp.message.middleware(AuthMiddleware())
            self.dp.callback_query.middleware(AuthMiddleware())
            
            # Middleware для проверки подписки
            self.dp.message.middleware(SubscriptionMiddleware())
            self.dp.callback_query.middleware(SubscriptionMiddleware())
            
            # Middleware для защиты от спама
            self.dp.message.middleware(ThrottlingMiddleware())
            self.dp.callback_query.middleware(ThrottlingMiddleware())
            
            logger.info("Client bot middleware configured")
            
        except Exception as e:
            logger.error(f"Error setting up middleware: {e}")
            raise
    
    async def setup_handlers(self):
        """Настройка обработчиков"""
        try:
            # Регистрируем роутеры в правильном порядке
            
            # Стартовые команды (высший приоритет)
            self.dp.include_router(start.router)
            
            # Основные функции
            self.dp.include_router(subscription.router)
            self.dp.include_router(profile.router)
            self.dp.include_router(servers.router)
            self.dp.include_router(configs.router)
            self.dp.include_router(payment.router)
            self.dp.include_router(support.router)
            
            logger.info("Client bot handlers configured")
            
        except Exception as e:
            logger.error(f"Error setting up handlers: {e}")
            raise
    
    async def on_startup(self):
        """Действия при запуске бота"""
        try:
            # Инициализация базы данных и Redis
            await init_database()
            await init_redis()
            
            # Получаем информацию о боте
            bot_info = await self.bot.get_me()
            logger.info(f"Client bot started: @{bot_info.username}")
            
            # Устанавливаем команды меню
            await self.set_bot_commands()
            
            # Уведомляем администраторов о запуске
            await self.notify_admins_startup()
            
        except Exception as e:
            logger.error(f"Error during bot startup: {e}")
            raise
    
    async def on_shutdown(self):
        """Действия при остановке бота"""
        try:
            logger.info("Client bot shutting down...")
            
            # Закрываем соединения
            await close_connections()
            
            # Закрываем storage
            if self.storage:
                await self.storage.close()
            
            # Закрываем сессию бота
            if self.bot:
                await self.bot.session.close()
            
            logger.info("Client bot shutdown completed")
            
        except Exception as e:
            logger.error(f"Error during bot shutdown: {e}")
    
    async def set_bot_commands(self):
        """Установка команд бота"""
        try:
            from aiogram.types import BotCommand
            
            commands = [
                BotCommand(command="start", description="🚀 Начать работу"),
                BotCommand(command="profile", description="👤 Мой профиль"),
                BotCommand(command="subscription", description="📦 Подписки"),
                BotCommand(command="servers", description="🌍 Серверы"),
                BotCommand(command="configs", description="⚙️ Конфигурации"),
                BotCommand(command="support", description="🎧 Поддержка"),
                BotCommand(command="help", description="❓ Помощь"),
            ]
            
            await self.bot.set_my_commands(commands)
            logger.info("Bot commands set successfully")
            
        except Exception as e:
            logger.error(f"Error setting bot commands: {e}")
    
    async def notify_admins_startup(self):
        """Уведомление администраторов о запуске"""
        try:
            if not settings.ADMIN_TELEGRAM_IDS:
                return
            
            startup_message = (
                "🚀 <b>Client Bot запущен!</b>\n\n"
                f"📅 Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"🌍 Окружение: {settings.ENVIRONMENT}\n"
                f"🔧 Версия: {settings.VERSION}"
            )
            
            for admin_id in settings.ADMIN_TELEGRAM_IDS:
                try:
                    await self.bot.send_message(
                        chat_id=admin_id,
                        text=startup_message
                    )
                except Exception as e:
                    logger.warning(f"Failed to notify admin {admin_id}: {e}")
            
        except Exception as e:
            logger.error(f"Error notifying admins: {e}")
    
    async def start_polling(self):
        """Запуск бота в режиме polling"""
        try:
            logger.info("Starting client bot polling...")
            
            # Запускаем polling
            await self.dp.start_polling(
                self.bot,
                on_startup=self.on_startup,
                on_shutdown=self.on_shutdown,
                allowed_updates=['message', 'callback_query', 'inline_query']
            )
            
        except Exception as e:
            logger.error(f"Error during polling: {e}")
            raise
    
    async def start_webhook(self, webhook_url: str, webhook_path: str = "/webhook"):
        """Запуск бота в режиме webhook"""
        try:
            from aiohttp import web
            from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
            
            logger.info(f"Starting client bot webhook: {webhook_url}")
            
            # Устанавливаем webhook
            await self.bot.set_webhook(
                url=webhook_url,
                secret_token=settings.WEBHOOK_SECRET
            )
            
            # Создаем веб-приложение
            app = web.Application()
            
            # Настраиваем webhook handler
            SimpleRequestHandler(
                dispatcher=self.dp,
                bot=self.bot,
                secret_token=settings.WEBHOOK_SECRET
            ).register(app, path=webhook_path)
            
            # Настраиваем приложение
            setup_application(app, self.dp, bot=self.bot)
            
            # Запускаем сервер
            runner = web.AppRunner(app)
            await runner.setup()
            
            site = web.TCPSite(runner, host="0.0.0.0", port=8001)
            await site.start()
            
            # Выполняем startup
            await self.on_startup()
            
            logger.info("Client bot webhook started successfully")
            
            # Ждем бесконечно
            await asyncio.Event().wait()
            
        except Exception as e:
            logger.error(f"Error during webhook: {e}")
            raise


async def main():
    """Главная функция запуска клиентского бота"""
    
    # Настройка логирования
    logger.add(
        "logs/client_bot.log",
        level=settings.LOG_LEVEL,
        rotation=settings.LOG_ROTATION,
        retention=settings.LOG_RETENTION,
        format=settings.LOG_FORMAT
    )
    
    # Проверяем наличие токена
    if not settings.CLIENT_BOT_TOKEN:
        logger.error("CLIENT_BOT_TOKEN not found in settings")
        sys.exit(1)
    
    # Создаем и настраиваем бота
    client_bot = ClientBot()
    
    try:
        await client_bot.setup_bot()
        await client_bot.setup_middleware()
        await client_bot.setup_handlers()
        
        # Запускаем в зависимости от режима
        if settings.WEBHOOK_DOMAIN:
            webhook_url = f"{settings.WEBHOOK_DOMAIN}/client/webhook"
            await client_bot.start_webhook(webhook_url)
        else:
            await client_bot.start_polling()
            
    except KeyboardInterrupt:
        logger.info("Client bot stopped by user")
    except Exception as e:
        logger.error(f"Client bot crashed: {e}")
        sys.exit(1)
    finally:
        await client_bot.on_shutdown()


if __name__ == "__main__":
    # Исправляем отсутствующий импорт
    from datetime import datetime
    
    # Запускаем бота
    asyncio.run(main())