"""
Конфигурация VPN Bot System
"""

import os
from typing import Optional, List
from pydantic import BaseSettings, validator
from pathlib import Path


class Settings(BaseSettings):
    """Основные настройки приложения"""
    
    # Основные настройки
    APP_NAME: str = "VPN Bot System"
    VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"
    
    # Пути проекта
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    LOGS_DIR: Path = BASE_DIR / "logs"
    STATIC_DIR: Path = BASE_DIR / "static"
    CONFIGS_DIR: Path = STATIC_DIR / "configs"
    QR_CODES_DIR: Path = STATIC_DIR / "qr_codes"
    
    # База данных PostgreSQL
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_USER: str = "vpn_user"
    DB_PASSWORD: str = "vpn_password"
    DB_NAME: str = "vpn_bot_db"
    
    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
    
    @property
    def SYNC_DATABASE_URL(self) -> str:
        return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
    
    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: Optional[str] = None
    REDIS_DB: int = 0
    
    @property
    def REDIS_URL(self) -> str:
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
    
    # Telegram боты
    CLIENT_BOT_TOKEN: str
    SUPPORT_BOT_TOKEN: str
    ADMIN_BOT_TOKEN: str
    
    # Администраторы
    ADMIN_TELEGRAM_IDS: List[int] = []
    SUPPORT_TELEGRAM_IDS: List[int] = []
    
    @validator('ADMIN_TELEGRAM_IDS', 'SUPPORT_TELEGRAM_IDS', pre=True)
    def parse_telegram_ids(cls, v):
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(',') if x.strip()]
        return v
    
    # Супергруппа поддержки
    SUPPORT_GROUP_ID: int
    
    # Webhook настройки
    WEBHOOK_DOMAIN: Optional[str] = None
    WEBHOOK_PATH: str = "/webhook"
    WEBHOOK_SECRET: Optional[str] = None
    
    # API настройки
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_SECRET_KEY: str = "your-secret-key-here"
    
    # Платежная система ЮKassa
    YOOKASSA_ACCOUNT_ID: Optional[str] = None
    YOOKASSA_SECRET_KEY: Optional[str] = None
    
    # Криптоплатежи
    CRYPTO_PAYMENT_API_KEY: Optional[str] = None
    
    # VPN серверы по умолчанию
    DEFAULT_VPN_PROTOCOL: str = "vless"
    VLESS_PROTOCOLS: List[str] = ["vless", "vmess"]
    
    # Настройки подписок
    DEFAULT_SUBSCRIPTION_DAYS: int = 30
    TRIAL_SUBSCRIPTION_DAYS: int = 3
    TRIAL_TRAFFIC_LIMIT_GB: int = 10
    
    # Лимиты и троттлинг
    RATE_LIMIT_REQUESTS: int = 30
    RATE_LIMIT_WINDOW: int = 60
    MAX_CONFIGS_PER_USER: int = 5
    
    # Уведомления
    NOTIFICATION_EXPIRE_DAYS: int = 3
    NOTIFICATION_EXPIRE_HOURS: int = 24
    
    # Мониторинг
    SENTRY_DSN: Optional[str] = None
    ENABLE_METRICS: bool = True
    
    # Логирование
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "{time} | {level} | {message}"
    LOG_ROTATION: str = "1 week"
    LOG_RETENTION: str = "1 month"
    
    # Безопасность
    ENCRYPTION_KEY: str = "your-encryption-key-32-chars!!"
    JWT_SECRET_KEY: str = "your-jwt-secret-key"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 30
    
    # Языки
    SUPPORTED_LANGUAGES: List[str] = ["ru", "en"]
    DEFAULT_LANGUAGE: str = "ru"
    
    # Региональные настройки
    TIMEZONE: str = "Europe/Moscow"
    CURRENCY: str = "RUB"
    
    # Настройки для российских пользователей
    RUSSIA_COUNTRY_CODES: List[str] = ["RU", "BY", "KZ"]
    PREFERRED_PROTOCOLS_RU: List[str] = ["vless", "vmess", "trojan"]
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


class DatabaseSettings(BaseSettings):
    """Настройки базы данных"""
    
    # Пул соединений
    POOL_SIZE: int = 10
    MAX_OVERFLOW: int = 20
    POOL_PRE_PING: bool = True
    POOL_RECYCLE: int = 3600
    
    # Настройки соединения
    CONNECT_TIMEOUT: int = 30
    COMMAND_TIMEOUT: int = 60
    
    class Config:
        env_file = ".env"
        env_prefix = "DB_"


class RedisSettings(BaseSettings):
    """Настройки Redis"""
    
    # Пул соединений
    MAX_CONNECTIONS: int = 10
    RETRY_ON_TIMEOUT: bool = True
    
    # TTL для кеша
    CACHE_TTL: int = 3600
    SESSION_TTL: int = 86400
    
    class Config:
        env_file = ".env"
        env_prefix = "REDIS_"


class VPNSettings(BaseSettings):
    """Настройки VPN серверов"""
    
    # 3X-UI настройки
    X3UI_DEFAULT_PORT: int = 54321
    X3UI_USERNAME: str = "admin"
    X3UI_PASSWORD: str = "admin"
    
    # VLESS настройки
    VLESS_DEFAULT_PORT: int = 443
    VLESS_ENCRYPTION: str = "none"
    VLESS_NETWORK: str = "tcp"
    VLESS_HEADER_TYPE: str = "none"
    
    # Reality настройки
    REALITY_SERVER_NAMES: List[str] = ["microsoft.com", "apple.com", "google.com"]
    REALITY_SHORT_IDS: List[str] = ["", "0123456789abcdef"]
    
    # OpenVPN настройки
    OPENVPN_PORT: int = 1194
    OPENVPN_PROTOCOL: str = "udp"
    OPENVPN_CIPHER: str = "AES-256-GCM"
    
    # WireGuard настройки
    WIREGUARD_PORT: int = 51820
    WIREGUARD_NETWORK: str = "10.0.0.0/24"
    
    class Config:
        env_file = ".env"
        env_prefix = "VPN_"


# Создаем глобальные экземпляры настроек
settings = Settings()
db_settings = DatabaseSettings()
redis_settings = RedisSettings()
vpn_settings = VPNSettings()


def get_settings() -> Settings:
    """Получить основные настройки"""
    return settings


def get_db_settings() -> DatabaseSettings:
    """Получить настройки базы данных"""
    return db_settings


def get_redis_settings() -> RedisSettings:
    """Получить настройки Redis"""
    return redis_settings


def get_vpn_settings() -> VPNSettings:
    """Получить настройки VPN"""
    return vpn_settings