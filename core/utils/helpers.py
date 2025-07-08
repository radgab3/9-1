"""
Вспомогательные функции для VPN Bot System
"""

import re
import asyncio
import aiohttp
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from loguru import logger

from config.settings import settings


async def get_country_by_ip(ip_address: str) -> Optional[str]:
    """
    Определить страну по IP адресу
    
    Args:
        ip_address: IP адрес
        
    Returns:
        Optional[str]: Код страны или None
    """
    try:
        # Используем бесплатный API для определения страны
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"http://ip-api.com/json/{ip_address}?fields=countryCode",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("countryCode")
                
        return None
        
    except Exception as e:
        logger.error(f"Error getting country by IP {ip_address}: {e}")
        return None


def detect_language(language_code: Optional[str]) -> str:
    """
    Определить язык пользователя
    
    Args:
        language_code: Код языка от Telegram
        
    Returns:
        str: Поддерживаемый код языка
    """
    if not language_code:
        return settings.DEFAULT_LANGUAGE
    
    # Нормализуем код языка
    lang = language_code.lower()[:2]
    
    if lang in settings.SUPPORTED_LANGUAGES:
        return lang
    
    return settings.DEFAULT_LANGUAGE


def format_bytes(bytes_count: int) -> str:
    """
    Форматировать размер в байтах
    
    Args:
        bytes_count: Количество байт
        
    Returns:
        str: Отформатированный размер
    """
    if bytes_count == 0:
        return "0 B"
    
    units = ["B", "KB", "MB", "GB", "TB"]
    size = bytes_count
    unit_index = 0
    
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    
    if unit_index == 0:
        return f"{int(size)} {units[unit_index]}"
    else:
        return f"{size:.1f} {units[unit_index]}"


def format_duration(seconds: int) -> str:
    """
    Форматировать длительность в секундах
    
    Args:
        seconds: Количество секунд
        
    Returns:
        str: Отформатированная длительность
    """
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        minutes = seconds // 60
        return f"{minutes}m"
    elif seconds < 86400:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}h {minutes}m"
    else:
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        return f"{days}d {hours}h"


def format_datetime(dt: datetime, user_timezone: str = "UTC") -> str:
    """
    Форматировать дату и время
    
    Args:
        dt: Объект datetime
        user_timezone: Часовой пояс пользователя
        
    Returns:
        str: Отформатированная дата
    """
    try:
        import pytz
        
        # Преобразуем в нужный часовой пояс
        if dt.tzinfo is None:
            dt = pytz.UTC.localize(dt)
        
        user_tz = pytz.timezone(user_timezone)
        local_dt = dt.astimezone(user_tz)
        
        return local_dt.strftime("%Y-%m-%d %H:%M")
        
    except Exception:
        return dt.strftime("%Y-%m-%d %H:%M")


def validate_email(email: str) -> bool:
    """
    Валидация email адреса
    
    Args:
        email: Email адрес
        
    Returns:
        bool: Валидность email
    """
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def validate_phone(phone: str) -> bool:
    """
    Валидация номера телефона
    
    Args:
        phone: Номер телефона
        
    Returns:
        bool: Валидность номера
    """
    # Простая валидация - только цифры и знак +
    pattern = r'^\+?[1-9]\d{1,14}$'
    return re.match(pattern, phone) is not None


def generate_random_string(length: int = 8) -> str:
    """
    Генерировать случайную строку
    
    Args:
        length: Длина строки
        
    Returns:
        str: Случайная строка
    """
    import random
    import string
    
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(length))


def mask_sensitive_data(data: str, visible_chars: int = 4) -> str:
    """
    Маскировать чувствительные данные
    
    Args:
        data: Данные для маскировки
        visible_chars: Количество видимых символов
        
    Returns:
        str: Замаскированные данные
    """
    if len(data) <= visible_chars * 2:
        return "*" * len(data)
    
    start = data[:visible_chars]
    end = data[-visible_chars:]
    middle = "*" * (len(data) - visible_chars * 2)
    
    return f"{start}{middle}{end}"


def calculate_percentage(part: float, total: float) -> float:
    """
    Вычислить процент
    
    Args:
        part: Часть
        total: Целое
        
    Returns:
        float: Процент
    """
    if total == 0:
        return 0.0
    return (part / total) * 100


def chunks(lst: List, chunk_size: int) -> List[List]:
    """
    Разбить список на чанки
    
    Args:
        lst: Исходный список
        chunk_size: Размер чанка
        
    Returns:
        List[List]: Список чанков
    """
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]


def safe_get(dictionary: Dict, key: str, default=None, converter=None):
    """
    Безопасно получить значение из словаря с конвертацией типа
    
    Args:
        dictionary: Словарь
        key: Ключ
        default: Значение по умолчанию
        converter: Функция конвертации
        
    Returns:
        Значение из словаря или default
    """
    try:
        value = dictionary.get(key, default)
        if converter and value is not None:
            return converter(value)
        return value
    except Exception:
        return default


class RateLimiter:
    """Ограничитель частоты запросов"""
    
    def __init__(self, max_requests: int, time_window: int):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = {}
    
    def is_allowed(self, identifier: str) -> bool:
        """
        Проверить, разрешен ли запрос
        
        Args:
            identifier: Идентификатор (IP, user_id и т.д.)
            
        Returns:
            bool: Разрешен ли запрос
        """
        now = datetime.utcnow()
        
        # Очищаем старые записи
        self._cleanup_old_requests(now)
        
        # Проверяем лимит для идентификатора
        if identifier not in self.requests:
            self.requests[identifier] = []
        
        user_requests = self.requests[identifier]
        
        # Удаляем запросы вне временного окна
        user_requests[:] = [req_time for req_time in user_requests 
                           if (now - req_time).total_seconds() < self.time_window]
        
        # Проверяем лимит
        if len(user_requests) >= self.max_requests:
            return False
        
        # Добавляем текущий запрос
        user_requests.append(now)
        return True
    
    def _cleanup_old_requests(self, now: datetime):
        """Очистить старые запросы"""
        cutoff_time = now - timedelta(seconds=self.time_window * 2)
        
        for identifier in list(self.requests.keys()):
            self.requests[identifier] = [
                req_time for req_time in self.requests[identifier]
                if req_time > cutoff_time
            ]
            
            # Удаляем пустые записи
            if not self.requests[identifier]:
                del self.requests[identifier]


class CircuitBreaker:
    """Автоматический выключатель для предотвращения каскадных сбоев"""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "closed"  # closed, open, half-open
    
    async def call(self, func, *args, **kwargs):
        """
        Вызвать функцию через автоматический выключатель
        
        Args:
            func: Функция для вызова
            *args: Позиционные аргументы
            **kwargs: Именованные аргументы
            
        Returns:
            Результат выполнения функции
        """
        if self.state == "open":
            if self._should_attempt_reset():
                self.state = "half-open"
            else:
                raise Exception("Circuit breaker is open")
        
        try:
            result = await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise e
    
    def _should_attempt_reset(self) -> bool:
        """Проверить, стоит ли попытаться сбросить выключатель"""
        if self.last_failure_time is None:
            return True
        
        time_since_failure = (datetime.utcnow() - self.last_failure_time).total_seconds()
        return time_since_failure >= self.recovery_timeout
    
    def _on_success(self):
        """Обработать успешный вызов"""
        self.failure_count = 0
        self.state = "closed"
    
    def _on_failure(self):
        """Обработать неудачный вызов"""
        self.failure_count += 1
        self.last_failure_time = datetime.utcnow()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "open"


class AsyncRetry:
    """Повторитель для асинхронных операций"""
    
    def __init__(self, max_attempts: int = 3, delay: float = 1.0, backoff: float = 2.0):
        self.max_attempts = max_attempts
        self.delay = delay
        self.backoff = backoff
    
    async def execute(self, func, *args, **kwargs):
        """
        Выполнить функцию с повторными попытками
        
        Args:
            func: Асинхронная функция
            *args: Позиционные аргументы
            **kwargs: Именованные аргументы
            
        Returns:
            Результат выполнения функции
        """
        last_exception = None
        current_delay =