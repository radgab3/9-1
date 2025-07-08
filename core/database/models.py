"""
Модели базы данных VPN Bot System
"""

import enum
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Text, JSON, 
    ForeignKey, Enum, Numeric, BigInteger, Index
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func
from config.database import Base


# Перечисления для системы
class UserRole(enum.Enum):
    """Роли пользователей"""
    CLIENT = "client"
    ADMIN = "admin"
    SUPPORT = "support"


class SubscriptionStatus(enum.Enum):
    """Статусы подписок"""
    ACTIVE = "active"
    EXPIRED = "expired"
    SUSPENDED = "suspended"
    PENDING = "pending"


class VpnProtocol(enum.Enum):
    """VPN протоколы"""
    VLESS = "vless"
    OPENVPN = "openvpn"
    WIREGUARD = "wireguard"


class PaymentStatus(enum.Enum):
    """Статусы платежей"""
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"


class TicketStatus(enum.Enum):
    """Статусы тикетов поддержки"""
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    WAITING_CLIENT = "waiting_client"
    CLOSED = "closed"


class Priority(enum.Enum):
    """Приоритеты"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# Основные модели
class User(Base):
    """Модель пользователя"""
    __tablename__ = "users"
    
    # Основные поля
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Настройки пользователя
    language_code: Mapped[str] = mapped_column(String(10), default="ru")
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.CLIENT)
    
    # Статусы
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # VPN предпочтения
    preferred_protocol: Mapped[Optional[VpnProtocol]] = mapped_column(
        Enum(VpnProtocol), nullable=True
    )
    auto_select_protocol: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Метаданные
    registration_ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    country_code: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    
    # Временные метки
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    last_activity: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Отношения
    subscriptions: Mapped[List["Subscription"]] = relationship(
        "Subscription", back_populates="user", lazy="selectin"
    )
    payments: Mapped[List["Payment"]] = relationship(
        "Payment", back_populates="user", lazy="selectin"
    )
    support_tickets: Mapped[List["SupportTicket"]] = relationship(
        "SupportTicket", back_populates="user", lazy="selectin"
    )
    activities: Mapped[List["UserActivity"]] = relationship(
        "UserActivity", back_populates="user", lazy="selectin"
    )
    
    # Индексы
    __table_args__ = (
        Index("idx_user_telegram_id", "telegram_id"),
        Index("idx_user_role", "role"),
        Index("idx_user_country", "country_code"),
    )
    
    def __repr__(self):
        return f"<User(id={self.id}, telegram_id={self.telegram_id}, username={self.username})>"


class Server(Base):
    """Модель VPN сервера"""
    __tablename__ = "servers"
    
    # Основные поля
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Местоположение
    country: Mapped[str] = mapped_column(String(255), nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    city: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Сетевые настройки
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    domain: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Поддерживаемые протоколы
    supported_protocols: Mapped[List[str]] = mapped_column(JSON, default=["vless"])
    primary_protocol: Mapped[VpnProtocol] = mapped_column(
        Enum(VpnProtocol), default=VpnProtocol.VLESS
    )
    
    # Конфигурации протоколов
    vless_config: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    openvpn_config: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    wireguard_config: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    # Лимиты и метрики
    max_users: Mapped[int] = mapped_column(Integer, default=100)
    current_users: Mapped[int] = mapped_column(Integer, default=0)
    cpu_usage: Mapped[float] = mapped_column(Numeric(5, 2), default=0.0)
    memory_usage: Mapped[float] = mapped_column(Numeric(5, 2), default=0.0)
    disk_usage: Mapped[float] = mapped_column(Numeric(5, 2), default=0.0)
    
    # Статус
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_maintenance: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Временные метки
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    last_check: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Отношения
    subscriptions: Mapped[List["Subscription"]] = relationship(
        "Subscription", back_populates="server", lazy="selectin"
    )
    vpn_configs: Mapped[List["VpnConfig"]] = relationship(
        "VpnConfig", back_populates="server", lazy="selectin"
    )
    server_stats: Mapped[List["ServerStats"]] = relationship(
        "ServerStats", back_populates="server", lazy="selectin"
    )
    
    # Индексы
    __table_args__ = (
        Index("idx_server_country", "country_code"),
        Index("idx_server_active", "is_active"),
        Index("idx_server_protocol", "primary_protocol"),
    )
    
    def __repr__(self):
        return f"<Server(id={self.id}, name={self.name}, country={self.country})>"


class SubscriptionPlan(Base):
    """Модель тарифного плана"""
    __tablename__ = "subscription_plans"
    
    # Основные поля
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Параметры плана
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    
    # Лимиты
    traffic_limit_gb: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # null = безлимит
    device_limit: Mapped[int] = mapped_column(Integer, default=1)
    
    # Статус
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_popular: Mapped[bool] = mapped_column(Boolean, default=False)
    is_trial: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Порядок сортировки
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    
    # Временные метки
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    
    # Отношения
    subscriptions: Mapped[List["Subscription"]] = relationship(
        "Subscription", back_populates="plan", lazy="selectin"
    )
    
    def __repr__(self):
        return f"<SubscriptionPlan(id={self.id}, name={self.name}, price={self.price})>"


# Добавим недостающие модели для завершения
class Subscription(Base):
    """Модель подписки"""
    __tablename__ = "subscriptions"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    plan_id: Mapped[int] = mapped_column(Integer, ForeignKey("subscription_plans.id"), nullable=False)
    server_id: Mapped[int] = mapped_column(Integer, ForeignKey("servers.id"), nullable=False)
    
    status: Mapped[SubscriptionStatus] = mapped_column(Enum(SubscriptionStatus), default=SubscriptionStatus.PENDING)
    active_protocol: Mapped[VpnProtocol] = mapped_column(Enum(VpnProtocol), default=VpnProtocol.VLESS)
    
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    traffic_used_gb: Mapped[float] = mapped_column(Numeric(10, 2), default=0.0)
    traffic_limit_gb: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    
    # Отношения
    user: Mapped["User"] = relationship("User", back_populates="subscriptions")
    plan: Mapped["SubscriptionPlan"] = relationship("SubscriptionPlan", back_populates="subscriptions")
    server: Mapped["Server"] = relationship("Server", back_populates="subscriptions")
    vpn_configs: Mapped[List["VpnConfig"]] = relationship("VpnConfig", back_populates="subscription")


class VpnConfig(Base):
    """Модель VPN конфигурации"""
    __tablename__ = "vpn_configs"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subscription_id: Mapped[int] = mapped_column(Integer, ForeignKey("subscriptions.id"), nullable=False)
    server_id: Mapped[int] = mapped_column(Integer, ForeignKey("servers.id"), nullable=False)
    
    protocol: Mapped[VpnProtocol] = mapped_column(Enum(VpnProtocol), nullable=False)
    client_id: Mapped[str] = mapped_column(String(255), nullable=False)
    
    config_data: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    connection_string: Mapped[str] = mapped_column(Text, nullable=False)
    
    qr_code_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    qr_code_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    total_traffic_gb: Mapped[float] = mapped_column(Numeric(10, 2), default=0.0)
    
    last_used: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    
    # Отношения
    subscription: Mapped["Subscription"] = relationship("Subscription", back_populates="vpn_configs")
    server: Mapped["Server"] = relationship("Server", back_populates="vpn_configs")


class Payment(Base):
    """Модель платежа"""
    __tablename__ = "payments"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    plan_id: Mapped[int] = mapped_column(Integer, ForeignKey("subscription_plans.id"), nullable=False)
    
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(Enum(PaymentStatus), default=PaymentStatus.PENDING)
    
    external_payment_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    payment_method: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    
    # Отношения
    user: Mapped["User"] = relationship("User", back_populates="payments")


class SupportTicket(Base):
    """Модель тикета поддержки"""
    __tablename__ = "support_tickets"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    assigned_admin_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    
    status: Mapped[TicketStatus] = mapped_column(Enum(TicketStatus), default=TicketStatus.OPEN)
    priority: Mapped[Priority] = mapped_column(Enum(Priority), default=Priority.MEDIUM)
    
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    
    # Отношения
    user: Mapped["User"] = relationship("User", back_populates="support_tickets", foreign_keys=[user_id])
    assigned_admin: Mapped[Optional["User"]] = relationship("User", foreign_keys=[assigned_admin_id])


class UserActivity(Base):
    """Модель активности пользователя"""
    __tablename__ = "user_activities"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    
    # Отношения
    user: Mapped["User"] = relationship("User", back_populates="activities")


class ServerStats(Base):
    """Модель статистики сервера"""
    __tablename__ = "server_stats"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    server_id: Mapped[int] = mapped_column(Integer, ForeignKey("servers.id"), nullable=False)
    
    cpu_usage: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    memory_usage: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    disk_usage: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    
    active_connections: Mapped[int] = mapped_column(Integer, default=0)
    total_traffic_gb: Mapped[float] = mapped_column(Numeric(10, 2), default=0.0)
    
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    
    # Отношения
    server: Mapped["Server"] = relationship("Server", back_populates="server_stats")


class SystemSettings(Base):
    """Модель системных настроек"""
    __tablename__ = "system_settings"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(50), default="general")
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    
    def __repr__(self):
        return f"<SystemSettings(key={self.key}, value={self.value})>"