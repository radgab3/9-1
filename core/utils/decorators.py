"""
Декораторы для VPN Bot System
"""

import asyncio
import time
from functools import wraps
from typing import Any, Callable, Optional, Dict
from datetime import datetime, timedelta
from loguru import logger

from core.utils.helpers import RateLimiter
from core.exceptions.custom_exceptions import (
    RateLimitExceededError, AuthenticationError, 
    TooManyRequestsError, MaintenanceModeError
)


def async_retry(max_attempts: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """
    Декоратор для повторных попыток асинхронных функций
    
    Args:
        max_attempts: Максимальное количество попыток
        delay: Задержка между попытками
        backoff: Множитель задержки
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay
            
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    logger.warning(f"Attempt {attempt + 1} failed for {func.__name__}: {e}")
                    
                    if attempt < max_attempts - 1:
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff
            
            logger.error(f"All {max_attempts} attempts failed for {func.__name__}")
            raise last_exception
        
        return wrapper
    return decorator


def rate_limit(max_requests: int = 10, time_window: int = 60):
    """
    Декоратор ограничения частоты запросов
    
    Args:
        max_requests: Максимальное количество запросов
        time_window: Временное окно в секундах
    """
    limiter = RateLimiter(max_requests, time_window)
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Извлекаем идентификатор (обычно user_id)
            identifier = kwargs.get('user_id') or (args[0] if args else 'unknown')
            
            if not limiter.is_allowed(str(identifier)):
                raise RateLimitExceededError(
                    f"Rate limit exceeded: {max_requests} requests per {time_window} seconds"
                )
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator


def log_execution_time(log_level: str = "INFO"):
    """
    Декоратор для логирования времени выполнения
    
    Args:
        log_level: Уровень логирования
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                execution_time = time.time() - start_time
                logger.log(log_level, f"{func.__name__} executed in {execution_time:.3f}s")
                return result
            except Exception as e:
                execution_time = time.time() - start_time
                logger.error(f"{func.__name__} failed after {execution_time:.3f}s: {e}")
                raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                execution_time = time.time() - start_time
                logger.log(log_level, f"{func.__name__} executed in {execution_time:.3f}s")
                return result
            except Exception as e:
                execution_time = time.time() - start_time
                logger.error(f"{func.__name__} failed after {execution_time:.3f}s: {e}")
                raise
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator


def cache_result(ttl: int = 3600):
    """
    Декоратор для кеширования результатов функций
    
    Args:
        ttl: Время жизни кеша в секундах
    """
    cache: Dict[str, tuple] = {}
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Создаем ключ кеша
            cache_key = f"{func.__name__}:{hash(str(args) + str(sorted(kwargs.items())))}"
            
            # Проверяем кеш
            if cache_key in cache:
                result, timestamp = cache[cache_key]
                if time.time() - timestamp < ttl:
                    logger.debug(f"Cache hit for {func.__name__}")
                    return result
                else:
                    del cache[cache_key]
            
            # Выполняем функцию и кешируем результат
            result = await func(*args, **kwargs)
            cache[cache_key] = (result, time.time())
            logger.debug(f"Cache miss for {func.__name__}, result cached")
            
            return result
        
        return wrapper
    return decorator


def require_admin(func: Callable) -> Callable:
    """
    Декоратор для проверки прав администратора
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # Ищем user_id в аргументах
        user_id = kwargs.get('user_id')
        if not user_id and args:
            # Пытаемся найти в первом аргументе (обычно это user_id)
            user_id = args[0] if isinstance(args[0], int) else None
        
        if not user_id:
            raise AuthenticationError("User ID required for admin check")
        
        # Здесь должна быть проверка через UserService
        # Упрощенная версия - проверяем через настройки
        from config.settings import settings
        if user_id not in settings.ADMIN_TELEGRAM_IDS:
            raise AuthenticationError("Admin access required")
        
        return await func(*args, **kwargs)
    
    return wrapper


def handle_errors(error_message: str = "Operation failed", log_errors: bool = True):
    """
    Декоратор для обработки ошибок
    
    Args:
        error_message: Сообщение об ошибке по умолчанию
        log_errors: Логировать ли ошибки
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                if log_errors:
                    logger.error(f"Error in {func.__name__}: {e}")
                
                # Возвращаем None или пустой результат вместо исключения
                if hasattr(func, '__annotations__'):
                    return_type = func.__annotations__.get('return', None)
                    if return_type == bool:
                        return False
                    elif return_type == list:
                        return []
                    elif return_type == dict:
                        return {}
                
                return None
        
        return wrapper
    return decorator


def validate_input(**validators):
    """
    Декоратор для валидации входных параметров
    
    Args:
        **validators: Словарь валидаторов для каждого параметра
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Валидируем именованные аргументы
            for param_name, validator in validators.items():
                if param_name in kwargs:
                    value = kwargs[param_name]
                    if not validator(value):
                        raise ValueError(f"Invalid value for parameter {param_name}: {value}")
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator


def maintenance_check(func: Callable) -> Callable:
    """
    Декоратор для проверки режима технического обслуживания
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # Проверяем настройки технического обслуживания
        try:
            from config.database import get_cache
            cache = await get_cache()
            maintenance_mode = await cache.get("maintenance_mode")
            
            if maintenance_mode == "true":
                raise MaintenanceModeError("System is under maintenance")
        except Exception:
            # Если не можем проверить - продолжаем работу
            pass
        
        return await func(*args, **kwargs)
    
    return wrapper


def singleton(cls):
    """
    Декоратор Singleton для классов
    """
    instances = {}
    
    def get_instance(*args, **kwargs):
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]
    
    return get_instance


def deprecated(reason: str = "This function is deprecated"):
    """
    Декоратор для помечания устаревших функций
    
    Args:
        reason: Причина устаревания
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            logger.warning(f"DEPRECATED: {func.__name__} - {reason}")
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator


class MetricsCollector:
    """Коллектор метрик для декораторов"""
    
    def __init__(self):
        self.metrics = {}
    
    def record_execution(self, func_name: str, execution_time: float, success: bool):
        """Записать метрику выполнения"""
        if func_name not in self.metrics:
            self.metrics[func_name] = {
                'total_calls': 0,
                'successful_calls': 0,
                'failed_calls': 0,
                'total_time': 0.0,
                'avg_time': 0.0
            }
        
        self.metrics[func_name]['total_calls'] += 1
        self.metrics[func_name]['total_time'] += execution_time
        
        if success:
            self.metrics[func_name]['successful_calls'] += 1
        else:
            self.metrics[func_name]['failed_calls'] += 1
        
        self.metrics[func_name]['avg_time'] = (
            self.metrics[func_name]['total_time'] / 
            self.metrics[func_name]['total_calls']
        )


# Глобальный коллектор метрик
metrics_collector = MetricsCollector()


def collect_metrics(func: Callable) -> Callable:
    """
    Декоратор для сбора метрик выполнения
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        success = True
        
        try:
            result = await func(*args, **kwargs)
            return result
        except Exception as e:
            success = False
            raise
        finally:
            execution_time = time.time() - start_time
            metrics_collector.record_execution(func.__name__, execution_time, success)
    
    return wrapper