"""
Конфигурация базы данных
"""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy import create_engine
from contextlib import asynccontextmanager
from typing import AsyncGenerator
import redis.asyncio as redis
from loguru import logger

from config.settings import settings, redis_settings


class Base(DeclarativeBase):
    """Базовый класс для всех моделей"""
    pass


class DatabaseManager:
    """Менеджер базы данных"""
    
    def __init__(self):
        # Асинхронный движок
        self.async_engine = create_async_engine(
            settings.DATABASE_URL,
            echo=settings.DEBUG,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=3600,
            future=True
        )
        
        # Синхронный движок (для миграций)
        self.sync_engine = create_engine(
            settings.SYNC_DATABASE_URL,
            echo=settings.DEBUG,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=3600,
            future=True
        )
        
        # Фабрика сессий
        self.async_session_factory = async_sessionmaker(
            bind=self.async_engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
        
        self.sync_session_factory = sessionmaker(
            bind=self.sync_engine,
            expire_on_commit=False
        )
    
    async def close(self):
        """Закрыть соединения"""
        await self.async_engine.dispose()
        self.sync_engine.dispose()
    
    @asynccontextmanager
    async def get_async_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Получить асинхронную сессию"""
        async with self.async_session_factory() as session:
            try:
                yield session
            except Exception as e:
                await session.rollback()
                logger.error(f"Database session error: {e}")
                raise
            finally:
                await session.close()
    
    def get_sync_session(self):
        """Получить синхронную сессию"""
        return self.sync_session_factory()


class RedisManager:
    """Менеджер Redis"""
    
    def __init__(self):
        self.redis_client = None
        self.connection_pool = None
    
    async def init_redis(self) -> redis.Redis:
        """Инициализация Redis"""
        try:
            self.connection_pool = redis.ConnectionPool.from_url(
                settings.REDIS_URL,
                max_connections=redis_settings.MAX_CONNECTIONS,
                retry_on_timeout=redis_settings.RETRY_ON_TIMEOUT,
                decode_responses=True
            )
            
            self.redis_client = redis.Redis(
                connection_pool=self.connection_pool
            )
            
            # Проверка соединения
            await self.redis_client.ping()
            logger.info("Redis connection established")
            
            return self.redis_client
            
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
    
    async def close(self):
        """Закрыть соединение с Redis"""
        if self.redis_client:
            await self.redis_client.close()
        if self.connection_pool:
            await self.connection_pool.disconnect()
    
    async def get_redis(self) -> redis.Redis:
        """Получить Redis клиент"""
        if not self.redis_client:
            await self.init_redis()
        return self.redis_client


# Глобальные экземпляры менеджеров
db_manager = DatabaseManager()
redis_manager = RedisManager()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency для получения сессии базы данных"""
    async with db_manager.get_async_session() as session:
        yield session


async def get_redis() -> redis.Redis:
    """Dependency для получения Redis клиента"""
    return await redis_manager.get_redis()


async def init_database():
    """Инициализация базы данных"""
    try:
        # Создание таблиц
        async with db_manager.async_engine.begin() as conn:
            # Импортируем все модели
            from core.database.models import *
            
            # Создаем таблицы
            await conn.run_sync(Base.metadata.create_all)
            
        logger.info("Database initialized successfully")
        
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


async def init_redis():
    """Инициализация Redis"""
    try:
        await redis_manager.init_redis()
        logger.info("Redis initialized successfully")
        
    except Exception as e:
        logger.error(f"Failed to initialize Redis: {e}")
        raise


async def close_connections():
    """Закрытие всех соединений"""
    await db_manager.close()
    await redis_manager.close()
    logger.info("All database connections closed")


# Middleware для автоматического управления сессиями
class DatabaseMiddleware:
    """Middleware для управления сессиями базы данных"""
    
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            async with db_manager.get_async_session() as session:
                scope["db"] = session
                await self.app(scope, receive, send)
        else:
            await self.app(scope, receive, send)


# Утилиты для работы с кешем
class CacheManager:
    """Менеджер кеширования"""
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
    
    async def get(self, key: str) -> str | None:
        """Получить значение из кеша"""
        try:
            return await self.redis.get(key)
        except Exception as e:
            logger.error(f"Cache get error: {e}")
            return None
    
    async def set(self, key: str, value: str, ttl: int = redis_settings.CACHE_TTL):
        """Установить значение в кеш"""
        try:
            await self.redis.setex(key, ttl, value)
        except Exception as e:
            logger.error(f"Cache set error: {e}")
    
    async def delete(self, key: str):
        """Удалить значение из кеша"""
        try:
            await self.redis.delete(key)
        except Exception as e:
            logger.error(f"Cache delete error: {e}")
    
    async def exists(self, key: str) -> bool:
        """Проверить существование ключа"""
        try:
            return await self.redis.exists(key)
        except Exception as e:
            logger.error(f"Cache exists error: {e}")
            return False
    
    async def clear_pattern(self, pattern: str):
        """Очистить кеш по шаблону"""
        try:
            keys = await self.redis.keys(pattern)
            if keys:
                await self.redis.delete(*keys)
        except Exception as e:
            logger.error(f"Cache clear pattern error: {e}")


async def get_cache() -> CacheManager:
    """Получить менеджер кеша"""
    redis_client = await get_redis()
    return CacheManager(redis_client)