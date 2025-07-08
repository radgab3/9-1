#!/usr/bin/env python3
"""
Скрипт инициализации базы данных VPN Bot System
"""

import asyncio
import sys
from pathlib import Path

# Добавляем корневую директорию в путь
sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy import text
from loguru import logger

from config.database import db_manager, init_database
from core.database.models import *
from core.database.repositories import RepositoryManager
from config.settings import settings, vpn_settings


async def create_default_data():
    """Создание начальных данных"""
    
    async with db_manager.get_async_session() as session:
        repos = RepositoryManager(session)
        
        try:
            logger.info("Creating default subscription plans...")
            
            # Создаем пробный план
            trial_plan = SubscriptionPlan(
                name="Пробный период",
                description="Бесплатный пробный доступ на 3 дня",
                duration_days=settings.TRIAL_SUBSCRIPTION_DAYS,
                price=0.0,
                currency="RUB",
                traffic_limit_gb=settings.TRIAL_TRAFFIC_LIMIT_GB,
                device_limit=1,
                is_trial=True,
                is_active=True,
                sort_order=1
            )
            session.add(trial_plan)
            
            # Создаем основные планы
            plans_data = [
                {
                    "name": "Месячный",
                    "description": "Доступ на 30 дней",
                    "duration_days": 30,
                    "price": 199.0,
                    "traffic_limit_gb": None,  # Безлимит
                    "device_limit": 3,
                    "sort_order": 2
                },
                {
                    "name": "3 месяца",
                    "description": "Доступ на 90 дней со скидкой",
                    "duration_days": 90,
                    "price": 499.0,
                    "traffic_limit_gb": None,
                    "device_limit": 5,
                    "is_popular": True,
                    "sort_order": 3
                },
                {
                    "name": "Полгода",
                    "description": "Доступ на 180 дней с большой скидкой",
                    "duration_days": 180,
                    "price": 899.0,
                    "traffic_limit_gb": None,
                    "device_limit": 10,
                    "sort_order": 4
                },
                {
                    "name": "Год",
                    "description": "Максимальная выгода - доступ на 365 дней",
                    "duration_days": 365,
                    "price": 1599.0,
                    "traffic_limit_gb": None,
                    "device_limit": 10,
                    "sort_order": 5
                }
            ]
            
            for plan_data in plans_data:
                plan = SubscriptionPlan(
                    name=plan_data["name"],
                    description=plan_data["description"],
                    duration_days=plan_data["duration_days"],
                    price=plan_data["price"],
                    currency="RUB",
                    traffic_limit_gb=plan_data["traffic_limit_gb"],
                    device_limit=plan_data["device_limit"],
                    is_popular=plan_data.get("is_popular", False),
                    is_active=True,
                    sort_order=plan_data["sort_order"]
                )
                session.add(plan)
            
            logger.info("Creating default servers...")
            
            # Создаем серверы по умолчанию (убрали vmess и trojan из supported_protocols)
            servers_data = [
                {
                    "name": "Netherlands-1",
                    "description": "Высокоскоростной сервер в Нидерландах",
                    "country": "Netherlands",
                    "country_code": "NL",
                    "city": "Amsterdam",
                    "ip_address": "185.162.131.85",
                    "domain": "nl1.vpnservice.com",
                    "supported_protocols": ["vless", "openvpn"],
                    "primary_protocol": VpnProtocol.VLESS,
                    "vless_config": {
                        "port": 443,
                        "encryption": "none",
                        "network": "tcp",
                        "header_type": "none",
                        "reality": {
                            "enabled": True,
                            "server_names": ["microsoft.com", "apple.com"],
                            "short_ids": ["", "0123456789abcdef"]
                        }
                    },
                    "max_users": 1000,
                    "is_active": True
                },
                {
                    "name": "Germany-1", 
                    "description": "Надежный сервер в Германии",
                    "country": "Germany",
                    "country_code": "DE",
                    "city": "Frankfurt",
                    "ip_address": "194.36.55.230",
                    "domain": "de1.vpnservice.com",
                    "supported_protocols": ["vless", "openvpn", "wireguard"],
                    "primary_protocol": VpnProtocol.VLESS,
                    "vless_config": {
                        "port": 443,
                        "encryption": "none",
                        "network": "tcp",
                        "header_type": "none",
                        "reality": {
                            "enabled": True,
                            "server_names": ["google.com", "cloudflare.com"],
                            "short_ids": ["", "fedcba9876543210"]
                        }
                    },
                    "max_users": 800,
                    "is_active": True
                },
                {
                    "name": "Finland-1",
                    "description": "Быстрый сервер в Финляндии",
                    "country": "Finland", 
                    "country_code": "FI",
                    "city": "Helsinki",
                    "ip_address": "95.216.216.34",
                    "domain": "fi1.vpnservice.com",
                    "supported_protocols": ["vless"],
                    "primary_protocol": VpnProtocol.VLESS,
                    "vless_config": {
                        "port": 443,
                        "encryption": "none",
                        "network": "tcp",
                        "header_type": "none",
                        "reality": {
                            "enabled": True,
                            "server_names": ["github.com", "telegram.org"],
                            "short_ids": ["", "abcdef0123456789"]
                        }
                    },
                    "max_users": 500,
                    "is_active": True
                }
            ]
            
            for server_data in servers_data:
                server = Server(**server_data)
                session.add(server)
            
            logger.info("Creating system settings...")
            
            # Создаем системные настройки
            system_settings = [
                {
                    "key": "maintenance_mode",
                    "value": "false",
                    "description": "Режим технического обслуживания",
                    "category": "system"
                },
                {
                    "key": "registration_enabled",
                    "value": "true", 
                    "description": "Разрешить регистрацию новых пользователей",
                    "category": "system"
                },
                {
                    "key": "trial_enabled",
                    "value": "true",
                    "description": "Разрешить пробный период",
                    "category": "subscription"
                },
                {
                    "key": "max_trial_per_user",
                    "value": "1",
                    "description": "Максимальное количество пробных периодов на пользователя",
                    "category": "subscription"
                },
                {
                    "key": "support_enabled",
                    "value": "true",
                    "description": "Включить систему поддержки",
                    "category": "support"
                },
                {
                    "key": "auto_server_selection",
                    "value": "true",
                    "description": "Автоматический выбор сервера",
                    "category": "vpn"
                },
                {
                    "key": "welcome_message",
                    "value": "Добро пожаловать в VPN Bot! 🚀\n\nВыберите тариф для начала работы.",
                    "description": "Приветственное сообщение для новых пользователей",
                    "category": "messages"
                }
            ]
            
            for setting_data in system_settings:
                setting = SystemSettings(**setting_data)
                session.add(setting)
            
            # Сохраняем все изменения
            await session.commit()
            logger.info("✅ Default data created successfully!")
            
        except Exception as e:
            await session.rollback()
            logger.error(f"❌ Error creating default data: {e}")
            raise


async def create_admin_user():
    """Создание администратора по умолчанию"""
    
    if not settings.ADMIN_TELEGRAM_IDS:
        logger.warning("No admin Telegram IDs configured, skipping admin creation")
        return
    
    async with db_manager.get_async_session() as session:
        repos = RepositoryManager(session)
        
        try:
            admin_id = settings.ADMIN_TELEGRAM_IDS[0]
            
            # Проверяем, существует ли уже администратор
            existing_admin = await repos.users.get_by_telegram_id(admin_id)
            if existing_admin:
                logger.info(f"Admin user {admin_id} already exists")
                return
            
            # Создаем администратора
            admin_user = await repos.users.create(
                telegram_id=admin_id,
                username="admin",
                first_name="System",
                last_name="Administrator",
                role=UserRole.ADMIN,
                is_active=True,
                language_code="ru"
            )
            
            await repos.commit()
            logger.info(f"✅ Admin user created: {admin_user.telegram_id}")
            
        except Exception as e:
            await session.rollback()
            logger.error(f"❌ Error creating admin user: {e}")
            raise


async def check_database_connection():
    """Проверка соединения с базой данных"""
    try:
        async with db_manager.async_engine.begin() as conn:
            result = await conn.execute(text("SELECT 1"))
            row = result.fetchone()
            if row and row[0] == 1:
                logger.info("✅ Database connection successful")
                return True
            else:
                logger.error("❌ Database connection failed")
                return False
    except Exception as e:
        logger.error(f"❌ Database connection error: {e}")
        return False


async def main():
    """Главная функция инициализации"""
    
    logger.info("🚀 Starting VPN Bot System database initialization...")
    
    try:
        # Проверяем соединение с базой данных
        if not await check_database_connection():
            logger.error("Failed to connect to database")
            sys.exit(1)
        
        logger.info("📋 Creating database tables...")
        await init_database()
        
        logger.info("📊 Creating default data...")
        await create_default_data()
        
        logger.info("👑 Creating admin user...")
        await create_admin_user()
        
        logger.info("✅ Database initialization completed successfully!")
        
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        sys.exit(1)
    
    finally:
        await db_manager.close()


if __name__ == "__main__":
    # Настройка логирования
    logger.add(
        "logs/init_db.log",
        level="INFO",
        rotation="1 week",
        retention="1 month",
        format="{time} | {level} | {message}"
    )
    
    # Запуск инициализации
    asyncio.run(main())