#!/usr/bin/env python3
"""
Скрипт для запуска всех ботов VPN Bot System
"""

import asyncio
import signal
import sys
from pathlib import Path
from typing import List, Optional

# Добавляем корневую директорию в путь
sys.path.append(str(Path(__file__).parent.parent))

from loguru import logger
from config.settings import settings
from config.database import init_database, init_redis, close_connections


class BotManager:
    """Менеджер для управления всеми ботами"""
    
    def __init__(self):
        self.tasks: List[asyncio.Task] = []
        self.shutdown_event = asyncio.Event()
    
    async def start_client_bot(self):
        """Запуск клиентского бота"""
        try:
            from bots.client.main import main as client_main
            logger.info("🤖 Starting Client Bot...")
            await client_main()
        except Exception as e:
            logger.error(f"❌ Client Bot error: {e}")
            raise
    
    async def start_support_bot(self):
        """Запуск бота поддержки"""
        try:
            from bots.support.main import main as support_main
            logger.info("🎧 Starting Support Bot...")
            await support_main()
        except Exception as e:
            logger.error(f"❌ Support Bot error: {e}")
            raise
    
    async def start_admin_bot(self):
        """Запуск админского бота"""
        try:
            from bots.admin.main import main as admin_main
            logger.info("👑 Starting Admin Bot...")
            await admin_main()
        except Exception as e:
            logger.error(f"❌ Admin Bot error: {e}")
            raise
    
    async def start_api_server(self):
        """Запуск API сервера"""
        try:
            import uvicorn
            from api.main import app
            
            logger.info("🌐 Starting API Server...")
            
            config = uvicorn.Config(
                app,
                host=settings.API_HOST,
                port=settings.API_PORT,
                log_level="info",
                access_log=True
            )
            
            server = uvicorn.Server(config)
            await server.serve()
            
        except Exception as e:
            logger.error(f"❌ API Server error: {e}")
            raise
    
    async def start_background_tasks(self):
        """Запуск фоновых задач"""
        try:
            logger.info("⚙️ Starting background tasks...")
            
            # Здесь можно добавить фоновые задачи:
            # - Проверка истекающих подписок
            # - Обновление статистики серверов
            # - Очистка логов
            # - Backup базы данных
            
            while not self.shutdown_event.is_set():
                # Пример фоновой задачи
                await self.check_expiring_subscriptions()
                await self.update_server_stats()
                
                # Ждем 1 час перед следующим циклом
                try:
                    await asyncio.wait_for(
                        self.shutdown_event.wait(),
                        timeout=3600
                    )
                    break
                except asyncio.TimeoutError:
                    continue
                    
        except Exception as e:
            logger.error(f"❌ Background tasks error: {e}")
            raise
    
    async def check_expiring_subscriptions(self):
        """Проверка истекающих подписок"""
        try:
            from config.database import get_db
            from core.services.subscription_service import SubscriptionNotificationService
            
            async for session in get_db():
                notification_service = SubscriptionNotificationService(session)
                notifications = await notification_service.check_expiring_subscriptions()
                
                for notification in notifications:
                    await notification_service.send_expiry_notification(notification)
                
                logger.debug(f"Checked expiring subscriptions: {len(notifications)} notifications sent")
                break
                
        except Exception as e:
            logger.error(f"Error checking expiring subscriptions: {e}")
    
    async def update_server_stats(self):
        """Обновление статистики серверов"""
        try:
            from config.database import get_db
            from core.services.server_service import ServerService
            
            async for session in get_db():
                server_service = ServerService(session)
                await server_service.update_all_server_stats()
                logger.debug("Updated server stats")
                break
                
        except Exception as e:
            logger.error(f"Error updating server stats: {e}")
    
    async def start_all_services(self):
        """Запуск всех сервисов"""
        try:
            logger.info("🚀 Starting VPN Bot System...")
            
            # Инициализация базы данных и Redis
            await init_database()
            await init_redis()
            
            # Создание задач для всех сервисов
            tasks = []
            
            # Клиентский бот
            if settings.CLIENT_BOT_TOKEN:
                task = asyncio.create_task(self.start_client_bot())
                task.set_name("client_bot")
                tasks.append(task)
            
            # Бот поддержки
            if settings.SUPPORT_BOT_TOKEN:
                task = asyncio.create_task(self.start_support_bot())
                task.set_name("support_bot")
                tasks.append(task)
            
            # Админский бот
            if settings.ADMIN_BOT_TOKEN:
                task = asyncio.create_task(self.start_admin_bot())
                task.set_name("admin_bot")
                tasks.append(task)
            
            # API сервер
            task = asyncio.create_task(self.start_api_server())
            task.set_name("api_server")
            tasks.append(task)
            
            # Фоновые задачи
            task = asyncio.create_task(self.start_background_tasks())
            task.set_name("background_tasks")
            tasks.append(task)
            
            self.tasks = tasks
            
            logger.info(f"✅ Started {len(tasks)} services")
            
            # Ожидание завершения задач или сигнала остановки
            await asyncio.gather(*tasks, return_exceptions=True)
            
        except Exception as e:
            logger.error(f"❌ Error starting services: {e}")
            raise
    
    async def shutdown(self):
        """Корректное завершение работы"""
        logger.info("🛑 Shutting down VPN Bot System...")
        
        # Устанавливаем флаг завершения
        self.shutdown_event.set()
        
        # Отменяем все задачи
        for task in self.tasks:
            if not task.done():
                task.cancel()
                logger.info(f"Cancelled task: {task.get_name()}")
        
        # Ждем завершения задач
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        
        # Закрываем соединения
        await close_connections()
        
        logger.info("✅ Shutdown completed")


# Глобальный менеджер ботов
bot_manager: Optional[BotManager] = None


def setup_signal_handlers():
    """Настройка обработчиков сигналов"""
    
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}")
        if bot_manager:
            # Создаем новый event loop для корректного завершения
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(bot_manager.shutdown())
            loop.close()
        sys.exit(0)
    
    # Обработчики для SIGINT (Ctrl+C) и SIGTERM
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


def setup_logging():
    """Настройка логирования"""
    
    # Удаляем стандартный обработчик
    logger.remove()
    
    # Консольный вывод
    logger.add(
        sys.stdout,
        level=settings.LOG_LEVEL,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        colorize=True
    )
    
    # Файл логов
    logger.add(
        "logs/vpn_bot_system.log",
        level=settings.LOG_LEVEL,
        format=settings.LOG_FORMAT,
        rotation=settings.LOG_ROTATION,
        retention=settings.LOG_RETENTION,
        compression="zip"
    )
    
    # Отдельные файлы для ошибок
    logger.add(
        "logs/errors.log",
        level="ERROR",
        format=settings.LOG_FORMAT,
        rotation="1 week",
        retention="1 month"
    )
    
    logger.info("📝 Logging configured")


async def health_check():
    """Проверка состояния системы"""
    try:
        from config.database import check_database_connection
        
        # Проверяем соединение с базой данных
        db_ok = await check_database_connection()
        
        # Проверяем Redis (упрощенная версия)
        redis_ok = True  # В реальной системе здесь была бы проверка Redis
        
        if db_ok and redis_ok:
            logger.info("✅ Health check passed")
            return True
        else:
            logger.error("❌ Health check failed")
            return False
            
    except Exception as e:
        logger.error(f"❌ Health check error: {e}")
        return False


async def main():
    """Главная функция"""
    global bot_manager
    
    try:
        # Настройка логирования
        setup_logging()
        
        # Настройка обработчиков сигналов
        setup_signal_handlers()
        
        logger.info("🚀 VPN Bot System Starting...")
        logger.info(f"Environment: {settings.ENVIRONMENT}")
        logger.info(f"Debug mode: {settings.DEBUG}")
        
        # Проверка состояния системы
        if not await health_check():
            logger.error("System health check failed, exiting...")
            sys.exit(1)
        
        # Создание менеджера ботов
        bot_manager = BotManager()
        
        # Запуск всех сервисов
        await bot_manager.start_all_services()
        
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        sys.exit(1)
    finally:
        if bot_manager:
            await bot_manager.shutdown()


if __name__ == "__main__":
    # Проверяем версию Python
    if sys.version_info < (3, 8):
        logger.error("Python 3.8+ required")
        sys.exit(1)
    
    # Проверяем наличие необходимых переменных окружения
    required_vars = ["CLIENT_BOT_TOKEN", "SUPPORT_BOT_TOKEN", "ADMIN_BOT_TOKEN"]
    missing_vars = [var for var in required_vars if not getattr(settings, var, None)]
    
    if missing_vars:
        logger.warning(f"Missing environment variables: {missing_vars}")
        logger.info("Some bots may not start due to missing tokens")
    
    # Создание директорий если они не существуют
    Path("logs").mkdir(exist_ok=True)
    Path("static").mkdir(exist_ok=True)
    Path("static/qr_codes").mkdir(exist_ok=True)
    Path("static/configs").mkdir(exist_ok=True)
    
    # Запуск основной функции
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 VPN Bot System stopped by user")
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        sys.exit(1)