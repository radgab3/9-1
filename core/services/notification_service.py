"""
Сервис уведомлений для VPN Bot System
"""

import asyncio
import json
from typing import Optional, List, Dict, Any, Union
from datetime import datetime, timedelta
from enum import Enum
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from core.database.models import (
    User, UserRole, Subscription, SubscriptionStatus, 
    Payment, PaymentStatus, Server, VpnConfig
)
from core.database.repositories import RepositoryManager
from core.services.user_service import UserService
from core.exceptions.custom_exceptions import NotificationError
from config.settings import settings


class NotificationType(Enum):
    """Типы уведомлений"""
    # Подписки
    SUBSCRIPTION_CREATED = "subscription_created"
    SUBSCRIPTION_ACTIVATED = "subscription_activated"
    SUBSCRIPTION_EXPIRED = "subscription_expired"
    SUBSCRIPTION_EXPIRING = "subscription_expiring"
    SUBSCRIPTION_SUSPENDED = "subscription_suspended"
    SUBSCRIPTION_RENEWED = "subscription_renewed"
    
    # Платежи
    PAYMENT_SUCCESS = "payment_success"
    PAYMENT_FAILED = "payment_failed"
    PAYMENT_PENDING = "payment_pending"
    PAYMENT_REFUNDED = "payment_refunded"
    
    # VPN конфигурации
    CONFIG_CREATED = "config_created"
    CONFIG_UPDATED = "config_updated"
    CONFIG_DELETED = "config_deleted"
    
    # Серверы
    SERVER_MAINTENANCE = "server_maintenance"
    SERVER_UNAVAILABLE = "server_unavailable"
    SERVER_RESTORED = "server_restored"
    
    # Система
    WELCOME = "welcome"
    SYSTEM_UPDATE = "system_update"
    SECURITY_ALERT = "security_alert"
    BROADCAST = "broadcast"
    
    # Поддержка
    TICKET_REPLY = "ticket_reply"
    TICKET_CLOSED = "ticket_closed"


class NotificationPriority(Enum):
    """Приоритеты уведомлений"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class NotificationChannel(Enum):
    """Каналы доставки уведомлений"""
    TELEGRAM = "telegram"
    EMAIL = "email"
    PUSH = "push"
    SMS = "sms"


class NotificationService:
    """Основной сервис уведомлений"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repos = RepositoryManager(session)
        self.user_service = UserService(session)
        
        # Настройки уведомлений
        self.enabled_channels = [NotificationChannel.TELEGRAM]
        self.rate_limits = {
            NotificationPriority.LOW: timedelta(minutes=5),
            NotificationPriority.NORMAL: timedelta(minutes=1),
            NotificationPriority.HIGH: timedelta(seconds=30),
            NotificationPriority.URGENT: timedelta(seconds=0)
        }
        
        # Кеш последних уведомлений для rate limiting
        self._last_notifications = {}
    
    async def send_notification(
        self,
        user_id: int,
        notification_type: NotificationType,
        title: str,
        message: str,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        channels: Optional[List[NotificationChannel]] = None,
        data: Optional[Dict[str, Any]] = None,
        scheduled_at: Optional[datetime] = None
    ) -> bool:
        """
        Отправить уведомление пользователю
        
        Args:
            user_id: ID пользователя
            notification_type: Тип уведомления
            title: Заголовок
            message: Текст сообщения
            priority: Приоритет
            channels: Каналы доставки
            data: Дополнительные данные
            scheduled_at: Время отправки (для отложенных уведомлений)
            
        Returns:
            bool: Успешность отправки
        """
        try:
            # Проверяем rate limiting
            if not await self._check_rate_limit(user_id, notification_type, priority):
                logger.info(f"Rate limit hit for user {user_id}, notification {notification_type.value}")
                return False
            
            # Получаем пользователя
            user = await self.repos.users.get_by_id(user_id)
            if not user:
                logger.error(f"User {user_id} not found")
                return False
            
            # Проверяем настройки уведомлений пользователя
            if not await self._check_user_preferences(user, notification_type):
                logger.info(f"User {user_id} disabled notifications for {notification_type.value}")
                return False
            
            # Используем каналы по умолчанию если не указаны
            if not channels:
                channels = self.enabled_channels
            
            # Форматируем сообщение
            formatted_message = await self._format_message(
                user, notification_type, title, message, data
            )
            
            # Отправляем через каждый канал
            success = False
            for channel in channels:
                try:
                    if channel == NotificationChannel.TELEGRAM:
                        sent = await self._send_telegram_notification(
                            user, formatted_message, priority, data
                        )
                        if sent:
                            success = True
                    
                    elif channel == NotificationChannel.EMAIL:
                        sent = await self._send_email_notification(
                            user, title, formatted_message, priority, data
                        )
                        if sent:
                            success = True
                    
                except Exception as e:
                    logger.error(f"Error sending via {channel.value}: {e}")
                    continue
            
            # Логируем уведомление
            if success:
                await self._log_notification(
                    user_id, notification_type, title, message, 
                    channels, priority, data
                )
                
                # Обновляем rate limiting
                self._update_rate_limit(user_id, notification_type)
            
            return success
            
        except Exception as e:
            logger.error(f"Error sending notification: {e}")
            return False
    
    async def send_bulk_notification(
        self,
        user_ids: List[int],
        notification_type: NotificationType,
        title: str,
        message: str,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        channels: Optional[List[NotificationChannel]] = None,
        data: Optional[Dict[str, Any]] = None,
        batch_size: int = 50
    ) -> Dict[str, int]:
        """
        Отправить уведомления группе пользователей
        
        Args:
            user_ids: Список ID пользователей
            notification_type: Тип уведомления
            title: Заголовок
            message: Текст сообщения
            priority: Приоритет
            channels: Каналы доставки
            data: Дополнительные данные
            batch_size: Размер пакета для отправки
            
        Returns:
            Dict[str, int]: Статистика отправки
        """
        try:
            sent_count = 0
            failed_count = 0
            total_users = len(user_ids)
            
            # Отправляем пакетами
            for i in range(0, total_users, batch_size):
                batch = user_ids[i:i + batch_size]
                
                # Создаем задачи для параллельной отправки
                tasks = []
                for user_id in batch:
                    task = asyncio.create_task(
                        self.send_notification(
                            user_id, notification_type, title, message,
                            priority, channels, data
                        )
                    )
                    tasks.append(task)
                
                # Выполняем пакет
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Подсчитываем результаты
                for result in results:
                    if isinstance(result, bool) and result:
                        sent_count += 1
                    else:
                        failed_count += 1
                
                # Пауза между пакетами
                if i + batch_size < total_users:
                    await asyncio.sleep(0.1)
            
            logger.info(f"Bulk notification sent: {sent_count}/{total_users} successful")
            
            return {
                "total": total_users,
                "sent": sent_count,
                "failed": failed_count,
                "success_rate": (sent_count / total_users) * 100 if total_users > 0 else 0
            }
            
        except Exception as e:
            logger.error(f"Error sending bulk notifications: {e}")
            return {"total": len(user_ids), "sent": 0, "failed": len(user_ids), "success_rate": 0}
    
    async def send_admin_notification(
        self,
        title: str,
        message: str,
        priority: NotificationPriority = NotificationPriority.HIGH,
        data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Отправить уведомление всем администраторам
        
        Args:
            title: Заголовок
            message: Текст сообщения
            priority: Приоритет
            data: Дополнительные данные
            
        Returns:
            bool: Успешность отправки
        """
        try:
            # Получаем всех администраторов
            admins = await self.repos.users.get_admins()
            admin_ids = [admin.id for admin in admins]
            
            if not admin_ids:
                logger.warning("No administrators found for notification")
                return False
            
            # Отправляем уведомления
            results = await self.send_bulk_notification(
                user_ids=admin_ids,
                notification_type=NotificationType.SYSTEM_UPDATE,
                title=f"🔧 Admin: {title}",
                message=message,
                priority=priority,
                data=data
            )
            
            return results["sent"] > 0
            
        except Exception as e:
            logger.error(f"Error sending admin notification: {e}")
            return False
    
    async def _check_rate_limit(
        self,
        user_id: int,
        notification_type: NotificationType,
        priority: NotificationPriority
    ) -> bool:
        """Проверить rate limiting"""
        try:
            rate_limit = self.rate_limits.get(priority, timedelta(minutes=1))
            if rate_limit.total_seconds() == 0:
                return True  # Urgent notifications bypass rate limiting
            
            key = f"{user_id}_{notification_type.value}"
            last_sent = self._last_notifications.get(key)
            
            if last_sent:
                time_passed = datetime.utcnow() - last_sent
                if time_passed < rate_limit:
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking rate limit: {e}")
            return True  # Default to allowing notification
    
    def _update_rate_limit(self, user_id: int, notification_type: NotificationType):
        """Обновить rate limiting"""
        key = f"{user_id}_{notification_type.value}"
        self._last_notifications[key] = datetime.utcnow()
        
        # Очищаем старые записи
        cutoff = datetime.utcnow() - timedelta(hours=1)
        self._last_notifications = {
            k: v for k, v in self._last_notifications.items()
            if v > cutoff
        }
    
    async def _check_user_preferences(
        self,
        user: User,
        notification_type: NotificationType
    ) -> bool:
        """Проверить настройки уведомлений пользователя"""
        try:
            # В полной реализации здесь была бы проверка настроек из БД
            # Пока разрешаем все уведомления кроме низкоприоритетных
            
            # Всегда отправляем критичные уведомления
            critical_types = [
                NotificationType.PAYMENT_SUCCESS,
                NotificationType.PAYMENT_FAILED,
                NotificationType.SUBSCRIPTION_EXPIRED,
                NotificationType.SECURITY_ALERT
            ]
            
            if notification_type in critical_types:
                return True
            
            # Проверяем, не заблокирован ли пользователь
            if user.is_banned or not user.is_active:
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking user preferences: {e}")
            return True
    
    async def _format_message(
        self,
        user: User,
        notification_type: NotificationType,
        title: str,
        message: str,
        data: Optional[Dict[str, Any]] = None
    ) -> str:
        """Форматировать сообщение для пользователя"""
        try:
            # Персонализация сообщения
            formatted_message = message
            
            # Заменяем переменные
            replacements = {
                "{name}": user.first_name or user.username or "Пользователь",
                "{username}": user.username or "неизвестно",
                "{user_id}": str(user.telegram_id)
            }
            
            # Добавляем данные из контекста
            if data:
                for key, value in data.items():
                    replacements[f"{{{key}}}"] = str(value)
            
            # Применяем замены
            for old, new in replacements.items():
                formatted_message = formatted_message.replace(old, new)
            
            # Добавляем эмодзи в зависимости от типа
            emoji_map = {
                NotificationType.PAYMENT_SUCCESS: "✅",
                NotificationType.PAYMENT_FAILED: "❌",
                NotificationType.SUBSCRIPTION_ACTIVATED: "🎉",
                NotificationType.SUBSCRIPTION_EXPIRED: "⏰",
                NotificationType.SUBSCRIPTION_EXPIRING: "⚠️",
                NotificationType.SERVER_MAINTENANCE: "🔧",
                NotificationType.WELCOME: "👋",
                NotificationType.SECURITY_ALERT: "🚨"
            }
            
            emoji = emoji_map.get(notification_type, "📢")
            formatted_message = f"{emoji} {formatted_message}"
            
            return formatted_message
            
        except Exception as e:
            logger.error(f"Error formatting message: {e}")
            return message
    
    async def _send_telegram_notification(
        self,
        user: User,
        message: str,
        priority: NotificationPriority,
        data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Отправить Telegram уведомление"""
        try:
            # В реальной реализации здесь был бы вызов Telegram Bot API
            # Пока просто логируем
            
            logger.info(f"Telegram notification to {user.telegram_id}: {message[:100]}...")
            
            # Эмуляция отправки
            await asyncio.sleep(0.01)  # Имитация network delay
            
            return True
            
        except Exception as e:
            logger.error(f"Error sending Telegram notification: {e}")
            return False
    
    async def _send_email_notification(
        self,
        user: User,
        title: str,
        message: str,
        priority: NotificationPriority,
        data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Отправить Email уведомление"""
        try:
            # В реальной реализации здесь была бы отправка email
            logger.info(f"Email notification to {user.telegram_id}: {title}")
            
            # Эмуляция отправки
            await asyncio.sleep(0.02)
            
            return True
            
        except Exception as e:
            logger.error(f"Error sending email notification: {e}")
            return False
    
    async def _log_notification(
        self,
        user_id: int,
        notification_type: NotificationType,
        title: str,
        message: str,
        channels: List[NotificationChannel],
        priority: NotificationPriority,
        data: Optional[Dict[str, Any]] = None
    ):
        """Логировать отправленное уведомление"""
        try:
            await self.user_service.log_user_action(
                user_id=user_id,
                action="notification_sent",
                details={
                    "notification_type": notification_type.value,
                    "title": title,
                    "channels": [c.value for c in channels],
                    "priority": priority.value,
                    "data": data
                }
            )
        except Exception as e:
            logger.error(f"Error logging notification: {e}")


class SubscriptionNotificationService:
    """Сервис уведомлений о подписках"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.notification_service = NotificationService(session)
        self.repos = RepositoryManager(session)
    
    async def notify_subscription_created(
        self,
        subscription_id: int
    ) -> bool:
        """Уведомление о создании подписки"""
        try:
            subscription = await self.repos.subscriptions.get_by_id(subscription_id)
            if not subscription:
                return False
            
            message = (
                f"Подписка успешно создана!\n\n"
                f"📦 План: {subscription.plan.name}\n"
                f"🌍 Сервер: {subscription.server.name}\n"
                f"⏱ Срок действия: {subscription.plan.duration_days} дней\n\n"
                f"После оплаты подписка будет автоматически активирована."
            )
            
            return await self.notification_service.send_notification(
                user_id=subscription.user_id,
                notification_type=NotificationType.SUBSCRIPTION_CREATED,
                title="Подписка создана",
                message=message,
                priority=NotificationPriority.NORMAL,
                data={
                    "subscription_id": subscription_id,
                    "plan_name": subscription.plan.name,
                    "server_name": subscription.server.name
                }
            )
            
        except Exception as e:
            logger.error(f"Error sending subscription created notification: {e}")
            return False
    
    async def notify_subscription_activated(
        self,
        subscription_id: int
    ) -> bool:
        """Уведомление об активации подписки"""
        try:
            subscription = await self.repos.subscriptions.get_by_id(subscription_id)
            if not subscription:
                return False
            
            expires_text = "Бессрочно"
            if subscription.expires_at:
                expires_text = subscription.expires_at.strftime("%d.%m.%Y")
            
            message = (
                f"Поздравляем! Ваша подписка активирована! 🎉\n\n"
                f"📦 План: {subscription.plan.name}\n"
                f"🌍 Сервер: {subscription.server.name}\n"
                f"📅 Действует до: {expires_text}\n"
                f"🔗 Протокол: {subscription.active_protocol.value.upper()}\n\n"
                f"Теперь вы можете скачать конфигурацию VPN в разделе 'Мои подписки'."
            )
            
            return await self.notification_service.send_notification(
                user_id=subscription.user_id,
                notification_type=NotificationType.SUBSCRIPTION_ACTIVATED,
                title="Подписка активирована",
                message=message,
                priority=NotificationPriority.HIGH,
                data={
                    "subscription_id": subscription_id,
                    "plan_name": subscription.plan.name,
                    "expires_at": subscription.expires_at.isoformat() if subscription.expires_at else None
                }
            )
            
        except Exception as e:
            logger.error(f"Error sending subscription activated notification: {e}")
            return False
    
    async def notify_subscription_expiring(
        self,
        subscription_id: int,
        days_left: int
    ) -> bool:
        """Уведомление о скором истечении подписки"""
        try:
            subscription = await self.repos.subscriptions.get_by_id(subscription_id)
            if not subscription:
                return False
            
            urgency = "скоро истекает" if days_left > 1 else "истекает завтра"
            
            message = (
                f"Ваша подписка {urgency}! ⚠️\n\n"
                f"📦 План: {subscription.plan.name}\n"
                f"🌍 Сервер: {subscription.server.name}\n"
                f"⏰ Осталось дней: {days_left}\n\n"
                f"Не забудьте продлить подписку, чтобы не потерять доступ к VPN!"
            )
            
            priority = NotificationPriority.HIGH if days_left <= 1 else NotificationPriority.NORMAL
            
            return await self.notification_service.send_notification(
                user_id=subscription.user_id,
                notification_type=NotificationType.SUBSCRIPTION_EXPIRING,
                title=f"Подписка истекает через {days_left} дн.",
                message=message,
                priority=priority,
                data={
                    "subscription_id": subscription_id,
                    "days_left": days_left,
                    "expires_at": subscription.expires_at.isoformat() if subscription.expires_at else None
                }
            )
            
        except Exception as e:
            logger.error(f"Error sending subscription expiring notification: {e}")
            return False
    
    async def notify_subscription_expired(
        self,
        subscription_id: int
    ) -> bool:
        """Уведомление об истечении подписки"""
        try:
            subscription = await self.repos.subscriptions.get_by_id(subscription_id)
            if not subscription:
                return False
            
            message = (
                f"Ваша подписка истекла ⏰\n\n"
                f"📦 План: {subscription.plan.name}\n"
                f"🌍 Сервер: {subscription.server.name}\n\n"
                f"Доступ к VPN заблокирован. Для восстановления доступа оформите новую подписку."
            )
            
            return await self.notification_service.send_notification(
                user_id=subscription.user_id,
                notification_type=NotificationType.SUBSCRIPTION_EXPIRED,
                title="Подписка истекла",
                message=message,
                priority=NotificationPriority.HIGH,
                data={
                    "subscription_id": subscription_id,
                    "plan_name": subscription.plan.name
                }
            )
            
        except Exception as e:
            logger.error(f"Error sending subscription expired notification: {e}")
            return False
    
    async def check_and_notify_expiring_subscriptions(self) -> int:
        """Проверить и уведомить о истекающих подписках"""
        try:
            # Проверяем подписки, истекающие в ближайшие дни
            notification_days = [1, 3, 7]  # За сколько дней уведомлять
            notified_count = 0
            
            for days in notification_days:
                expiring_subscriptions = await self.repos.subscriptions.get_expiring_subscriptions(
                    hours=days * 24
                )
                
                for subscription in expiring_subscriptions:
                    # Проверяем, не отправляли ли уже уведомление
                    last_notification = await self._get_last_expiry_notification(
                        subscription.id, days
                    )
                    
                    if not last_notification:
                        success = await self.notify_subscription_expiring(
                            subscription.id, days
                        )
                        if success:
                            notified_count += 1
                            await self._record_expiry_notification(subscription.id, days)
            
            if notified_count > 0:
                logger.info(f"Sent {notified_count} expiry notifications")
            
            return notified_count
            
        except Exception as e:
            logger.error(f"Error checking expiring subscriptions: {e}")
            return 0
    
    async def _get_last_expiry_notification(
        self,
        subscription_id: int,
        days_left: int
    ) -> Optional[datetime]:
        """Получить время последнего уведомления об истечении"""
        # В реальной реализации здесь был бы запрос к БД
        return None
    
    async def _record_expiry_notification(
        self,
        subscription_id: int,
        days_left: int
    ):
        """Записать отправку уведомления об истечении"""
        # В реальной реализации здесь была бы запись в БД
        pass


class PaymentNotificationService:
    """Сервис уведомлений о платежах"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.notification_service = NotificationService(session)
        self.repos = RepositoryManager(session)
    
    async def notify_payment_success(
        self,
        payment_id: int
    ) -> bool:
        """Уведомление об успешном платеже"""
        try:
            payment = await self.repos.payments.get_by_id(payment_id)
            if not payment:
                return False
            
            plan_name = "Unknown"
            if payment.subscription_plan:
                plan_name = payment.subscription_plan.name
            
            message = (
                f"Платеж успешно обработан! ✅\n\n"
                f"💰 Сумма: {payment.amount} {payment.currency}\n"
                f"📦 План: {plan_name}\n"
                f"💳 Способ оплаты: {payment.payment_method.value}\n"
                f"📅 Дата: {payment.paid_at.strftime('%d.%m.%Y %H:%M') if payment.paid_at else 'Неизвестно'}\n\n"
                f"Ваша подписка будет активирована в течение нескольких минут."
            )
            
            return await self.notification_service.send_notification(
                user_id=payment.user_id,
                notification_type=NotificationType.PAYMENT_SUCCESS,
                title="Платеж успешен",
                message=message,
                priority=NotificationPriority.HIGH,
                data={
                    "payment_id": payment_id,
                    "amount": float(payment.amount),
                    "currency": payment.currency,
                    "plan_name": plan_name
                }
            )
            
        except Exception as e:
            logger.error(f"Error sending payment success notification: {e}")
            return False
    
    async def notify_payment_failed(
        self,
        payment_id: int,
        reason: Optional[str] = None
    ) -> bool:
        """Уведомление о неуспешном платеже"""
        try:
            payment = await self.repos.payments.get_by_id(payment_id)
            if not payment:
                return False
            
            reason_text = f"\n\nПричина: {reason}" if reason else ""
            
            message = (
                f"Платеж не удался ❌\n\n"
                f"💰 Сумма: {payment.amount} {payment.currency}\n"
                f"💳 Способ оплаты: {payment.payment_method.value}\n"
                f"📅 Дата: {payment.created_at.strftime('%d.%m.%Y %H:%M')}"
                f"{reason_text}\n\n"
                f"Попробуйте повторить платеж или выберите другой способ оплаты."
            )
            
            return await self.notification_service.send_notification(
                user_id=payment.user_id,
                notification_type=NotificationType.PAYMENT_FAILED,
                title="Платеж не удался",
                message=message,
                priority=NotificationPriority.HIGH,
                data={
                    "payment_id": payment_id,
                    "amount": float(payment.amount),
                    "currency": payment.currency,
                    "reason": reason
                }
            )
            
        except Exception as e:
            logger.error(f"Error sending payment failed notification: {e}")
            return False
    
    async def notify_payment_pending(
        self,
        payment_id: int
    ) -> bool:
        """Уведомление об ожидании платежа"""
        try:
            payment = await self.repos.payments.get_by_id(payment_id)
            if not payment:
                return False
            
            timeout_minutes = 15  # Таймаут для большинства платежных систем
            
            message = (
                f"Ожидаем подтверждение платежа ⏳\n\n"
                f"💰 Сумма: {payment.amount} {payment.currency}\n"
                f"💳 Способ оплаты: {payment.payment_method.value}\n"
                f"⏰ Время ожидания: {timeout_minutes} минут\n\n"
                f"Платеж будет обработан автоматически после подтверждения."
            )
            
            return await self.notification_service.send_notification(
                user_id=payment.user_id,
                notification_type=NotificationType.PAYMENT_PENDING,
                title="Платеж в обработке",
                message=message,
                priority=NotificationPriority.NORMAL,
                data={
                    "payment_id": payment_id,
                    "amount": float(payment.amount),
                    "currency": payment.currency,
                    "timeout_minutes": timeout_minutes
                }
            )
            
        except Exception as e:
            logger.error(f"Error sending payment pending notification: {e}")
            return False


class ServerNotificationService:
    """Сервис уведомлений о серверах"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.notification_service = NotificationService(session)
        self.repos = RepositoryManager(session)
    
    async def notify_server_maintenance(
        self,
        server_id: int,
        maintenance_start: datetime,
        estimated_duration: Optional[int] = None
    ) -> int:
        """Уведомление о техническом обслуживании сервера"""
        try:
            server = await self.repos.servers.get_by_id(server_id)
            if not server:
                return 0
            
            # Получаем пользователей с активными подписками на этом сервере
            affected_users = await self._get_server_users(server_id)
            
            if not affected_users:
                return 0
            
            duration_text = f" (примерно {estimated_duration} мин.)" if estimated_duration else ""
            start_time = maintenance_start.strftime("%d.%m.%Y в %H:%M")
            
            message = (
                f"Запланированы технические работы 🔧\n\n"
                f"🌍 Сервер: {server.name}\n"
                f"📅 Время начала: {start_time}{duration_text}\n\n"
                f"Во время технических работ доступ к VPN будет временно ограничен. "
                f"Приносим извинения за неудобства."
            )
            
            user_ids = [user.id for user in affected_users]
            results = await self.notification_service.send_bulk_notification(
                user_ids=user_ids,
                notification_type=NotificationType.SERVER_MAINTENANCE,
                title=f"Техработы на {server.name}",
                message=message,
                priority=NotificationPriority.NORMAL,
                data={
                    "server_id": server_id,
                    "server_name": server.name,
                    "maintenance_start": maintenance_start.isoformat(),
                    "estimated_duration": estimated_duration
                }
            )
            
            return results["sent"]
            
        except Exception as e:
            logger.error(f"Error sending server maintenance notification: {e}")
            return 0
    
    async def notify_server_unavailable(
        self,
        server_id: int,
        reason: Optional[str] = None
    ) -> int:
        """Уведомление о недоступности сервера"""
        try:
            server = await self.repos.servers.get_by_id(server_id)
            if not server:
                return 0
            
            affected_users = await self._get_server_users(server_id)
            if not affected_users:
                return 0
            
            reason_text = f"\n\nПричина: {reason}" if reason else ""
            
            message = (
                f"Сервер временно недоступен ⚠️\n\n"
                f"🌍 Сервер: {server.name}\n"
                f"📍 Расположение: {server.city}, {server.country}"
                f"{reason_text}\n\n"
                f"Мы работаем над устранением проблемы. Вы можете использовать другие доступные серверы."
            )
            
            user_ids = [user.id for user in affected_users]
            results = await self.notification_service.send_bulk_notification(
                user_ids=user_ids,
                notification_type=NotificationType.SERVER_UNAVAILABLE,
                title=f"Сервер {server.name} недоступен",
                message=message,
                priority=NotificationPriority.HIGH,
                data={
                    "server_id": server_id,
                    "server_name": server.name,
                    "reason": reason
                }
            )
            
            return results["sent"]
            
        except Exception as e:
            logger.error(f"Error sending server unavailable notification: {e}")
            return 0
    
    async def notify_server_restored(
        self,
        server_id: int
    ) -> int:
        """Уведомление о восстановлении сервера"""
        try:
            server = await self.repos.servers.get_by_id(server_id)
            if not server:
                return 0
            
            affected_users = await self._get_server_users(server_id)
            if not affected_users:
                return 0
            
            message = (
                f"Сервер восстановлен! ✅\n\n"
                f"🌍 Сервер: {server.name}\n"
                f"📍 Расположение: {server.city}, {server.country}\n\n"
                f"Все сервисы работают в штатном режиме. Спасибо за терпение!"
            )
            
            user_ids = [user.id for user in affected_users]
            results = await self.notification_service.send_bulk_notification(
                user_ids=user_ids,
                notification_type=NotificationType.SERVER_RESTORED,
                title=f"Сервер {server.name} восстановлен",
                message=message,
                priority=NotificationPriority.NORMAL,
                data={
                    "server_id": server_id,
                    "server_name": server.name
                }
            )
            
            return results["sent"]
            
        except Exception as e:
            logger.error(f"Error sending server restored notification: {e}")
            return 0
    
    async def _get_server_users(self, server_id: int) -> List[User]:
        """Получить пользователей с активными подписками на сервере"""
        try:
            # В реальной реализации здесь был бы запрос через subscriptions
            return []
        except Exception as e:
            logger.error(f"Error getting server users: {e}")
            return []


class VpnConfigNotificationService:
    """Сервис уведомлений о VPN конфигурациях"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.notification_service = NotificationService(session)
        self.repos = RepositoryManager(session)
    
    async def notify_config_created(
        self,
        config_id: int
    ) -> bool:
        """Уведомление о создании конфигурации"""
        try:
            config = await self.repos.vpn_configs.get_by_id(config_id)
            if not config:
                return False
            
            message = (
                f"VPN конфигурация готова! 🔗\n\n"
                f"🌍 Сервер: {config.server.name}\n"
                f"🔐 Протокол: {config.protocol.value.upper()}\n"
                f"📱 ID конфигурации: {config.client_id}\n\n"
                f"Конфигурация доступна для скачивания в разделе 'Мои подписки'."
            )
            
            return await self.notification_service.send_notification(
                user_id=config.subscription.user_id,
                notification_type=NotificationType.CONFIG_CREATED,
                title="Конфигурация готова",
                message=message,
                priority=NotificationPriority.NORMAL,
                data={
                    "config_id": config_id,
                    "server_name": config.server.name,
                    "protocol": config.protocol.value,
                    "client_id": config.client_id
                }
            )
            
        except Exception as e:
            logger.error(f"Error sending config created notification: {e}")
            return False


class WelcomeNotificationService:
    """Сервис приветственных уведомлений"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.notification_service = NotificationService(session)
    
    async def send_welcome_message(
        self,
        user_id: int
    ) -> bool:
        """Отправить приветственное сообщение"""
        try:
            message = (
                f"Добро пожаловать в VPN Bot! 👋\n\n"
                f"🔐 Безопасный и быстрый VPN\n"
                f"🌍 Серверы по всему миру\n"
                f"⚡ Простая настройка\n"
                f"🔧 Техподдержка 24/7\n\n"
                f"Для начала работы выберите тарифный план в главном меню. "
                f"Если у вас есть вопросы - обращайтесь в поддержку!"
            )
            
            return await self.notification_service.send_notification(
                user_id=user_id,
                notification_type=NotificationType.WELCOME,
                title="Добро пожаловать!",
                message=message,
                priority=NotificationPriority.NORMAL
            )
            
        except Exception as e:
            logger.error(f"Error sending welcome message: {e}")
            return False


class BroadcastNotificationService:
    """Сервис массовых рассылок"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.notification_service = NotificationService(session)
        self.repos = RepositoryManager(session)
    
    async def send_broadcast(
        self,
        title: str,
        message: str,
        target_users: str = "all",
        priority: NotificationPriority = NotificationPriority.LOW,
        schedule_at: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Отправить массовую рассылку
        
        Args:
            title: Заголовок
            message: Текст сообщения
            target_users: Целевая аудитория (all, active, premium, etc.)
            priority: Приоритет
            schedule_at: Время отправки (для отложенных рассылок)
            
        Returns:
            Dict[str, Any]: Результаты рассылки
        """
        try:
            # Получаем список пользователей
            user_ids = await self._get_target_users(target_users)
            
            if not user_ids:
                return {"error": "No target users found"}
            
            # Отправляем рассылку
            results = await self.notification_service.send_bulk_notification(
                user_ids=user_ids,
                notification_type=NotificationType.BROADCAST,
                title=title,
                message=message,
                priority=priority,
                data={
                    "broadcast_target": target_users,
                    "scheduled_at": schedule_at.isoformat() if schedule_at else None
                }
            )
            
            # Логируем рассылку
            logger.info(f"Broadcast sent: {results['sent']}/{results['total']} users")
            
            return {
                "success": True,
                "target_users": target_users,
                "total_recipients": results["total"],
                "sent": results["sent"],
                "failed": results["failed"],
                "success_rate": results["success_rate"]
            }
            
        except Exception as e:
            logger.error(f"Error sending broadcast: {e}")
            return {"error": str(e)}
    
    async def _get_target_users(self, target: str) -> List[int]:
        """Получить список пользователей для рассылки"""
        try:
            if target == "all":
                users = await self.repos.users.get_all_active()
                return [user.id for user in users]
            
            elif target == "active":
                # Пользователи с активными подписками
                # В реальной реализации здесь был бы сложный запрос
                users = await self.repos.users.get_all_active()
                return [user.id for user in users]
            
            elif target == "admins":
                admins = await self.repos.users.get_admins()
                return [admin.id for admin in admins]
            
            else:
                logger.warning(f"Unknown target: {target}")
                return []
                
        except Exception as e:
            logger.error(f"Error getting target users: {e}")
            return []


class NotificationScheduler:
    """Планировщик уведомлений"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.subscription_notifier = SubscriptionNotificationService(session)
        self.repos = RepositoryManager(session)
    
    async def run_scheduled_notifications(self):
        """Запустить запланированные уведомления"""
        try:
            # Проверяем истекающие подписки
            await self.subscription_notifier.check_and_notify_expiring_subscriptions()
            
            # Проверяем просроченные платежи
            await self._check_expired_payments()
            
            # Проверяем неактивных пользователей
            await self._check_inactive_users()
            
            logger.info("Scheduled notifications completed")
            
        except Exception as e:
            logger.error(f"Error running scheduled notifications: {e}")
    
    async def _check_expired_payments(self):
        """Проверить просроченные платежи"""
        try:
            # Получаем платежи в статусе PENDING старше 24 часов
            cutoff_time = datetime.utcnow() - timedelta(hours=24)
            
            # В реальной реализации здесь был бы запрос к БД
            # expired_payments = await self.repos.payments.get_expired_pending(cutoff_time)
            
            logger.info("Checked expired payments")
            
        except Exception as e:
            logger.error(f"Error checking expired payments: {e}")
    
    async def _check_inactive_users(self):
        """Проверить неактивных пользователей"""
        try:
            # Находим пользователей, которые давно не заходили
            cutoff_time = datetime.utcnow() - timedelta(days=30)
            
            # В реальной реализации здесь был бы запрос к БД
            # inactive_users = await self.repos.users.get_inactive_since(cutoff_time)
            
            logger.info("Checked inactive users")
            
        except Exception as e:
            logger.error(f"Error checking inactive users: {e}")


class NotificationTemplateService:
    """Сервис шаблонов уведомлений"""
    
    def __init__(self):
        self.templates = {
            NotificationType.PAYMENT_SUCCESS: {
                "title": "Платеж успешен ✅",
                "template": (
                    "Ваш платеж успешно обработан!\n\n"
                    "💰 Сумма: {amount} {currency}\n"
                    "📦 План: {plan_name}\n"
                    "📅 Дата: {payment_date}\n\n"
                    "Подписка активируется автоматически."
                )
            },
            NotificationType.PAYMENT_FAILED: {
                "title": "Ошибка платежа ❌",
                "template": (
                    "К сожалению, платеж не удался.\n\n"
                    "💰 Сумма: {amount} {currency}\n"
                    "📅 Дата: {payment_date}\n"
                    "❗ Причина: {error_reason}\n\n"
                    "Попробуйте повторить платеж."
                )
            },
            NotificationType.SUBSCRIPTION_EXPIRING: {
                "title": "Подписка истекает ⚠️",
                "template": (
                    "Ваша подписка скоро истекает!\n\n"
                    "📦 План: {plan_name}\n"
                    "⏰ Осталось: {days_left} дн.\n"
                    "📅 Истекает: {expires_date}\n\n"
                    "Не забудьте продлить подписку!"
                )
            }
        }
    
    def get_template(
        self,
        notification_type: NotificationType,
        data: Dict[str, Any]
    ) -> Dict[str, str]:
        """
        Получить шаблон уведомления
        
        Args:
            notification_type: Тип уведомления
            data: Данные для подстановки
            
        Returns:
            Dict[str, str]: Заголовок и текст сообщения
        """
        template_data = self.templates.get(notification_type)
        
        if not template_data:
            return {
                "title": "Уведомление",
                "message": "У вас новое уведомление."
            }
        
        try:
            # Форматируем шаблон
            formatted_message = template_data["template"].format(**data)
            
            return {
                "title": template_data["title"],
                "message": formatted_message
            }
            
        except KeyError as e:
            logger.error(f"Missing template variable: {e}")
            return {
                "title": template_data["title"],
                "message": template_data["template"]
            }


class NotificationMetricsService:
    """Сервис метрик уведомлений"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repos = RepositoryManager(session)
    
    async def get_notification_stats(self, days: int = 7) -> Dict[str, Any]:
        """
        Получить статистику уведомлений
        
        Args:
            days: Количество дней для анализа
            
        Returns:
            Dict[str, Any]: Статистика уведомлений
        """
        try:
            # В реальной реализации здесь были бы запросы к БД
            return {
                "period_days": days,
                "total_sent": 0,
                "delivery_rate": 0.0,
                "by_type": {},
                "by_priority": {},
                "by_channel": {},
                "errors": 0
            }
            
        except Exception as e:
            logger.error(f"Error getting notification stats: {e}")
            return {}


# Глобальные экземпляры сервисов
_notification_services = {}


def get_notification_service(session: AsyncSession) -> NotificationService:
    """Получить экземпляр NotificationService"""
    return NotificationService(session)


def get_subscription_notifier(session: AsyncSession) -> SubscriptionNotificationService:
    """Получить экземпляр SubscriptionNotificationService"""
    return SubscriptionNotificationService(session)


def get_payment_notifier(session: AsyncSession) -> PaymentNotificationService:
    """Получить экземпляр PaymentNotificationService"""
    return PaymentNotificationService(session)


def get_broadcast_service(session: AsyncSession) -> BroadcastNotificationService:
    """Получить экземпляр BroadcastNotificationService"""
    return BroadcastNotificationService(session)


# Функции-хелперы для быстрого использования
async def send_quick_notification(
    session: AsyncSession,
    user_id: int,
    title: str,
    message: str,
    priority: NotificationPriority = NotificationPriority.NORMAL
) -> bool:
    """
    Быстрая отправка уведомления
    
    Args:
        session: Сессия базы данных
        user_id: ID пользователя
        title: Заголовок
        message: Сообщение
        priority: Приоритет
        
    Returns:
        bool: Успешность отправки
    """
    service = NotificationService(session)
    return await service.send_notification(
        user_id=user_id,
        notification_type=NotificationType.SYSTEM_UPDATE,
        title=title,
        message=message,
        priority=priority
    )


async def notify_payment_result(
    session: AsyncSession,
    payment_id: int,
    success: bool,
    reason: Optional[str] = None
) -> bool:
    """
    Уведомить о результате платежа
    
    Args:
        session: Сессия базы данных
        payment_id: ID платежа
        success: Успешность платежа
        reason: Причина неудачи (для неуспешных платежей)
        
    Returns:
        bool: Успешность отправки уведомления
    """
    service = PaymentNotificationService(session)
    
    if success:
        return await service.notify_payment_success(payment_id)
    else:
        return await service.notify_payment_failed(payment_id, reason)


async def notify_subscription_change(
    session: AsyncSession,
    subscription_id: int,
    change_type: str,
    **kwargs
) -> bool:
    """
    Уведомить об изменении подписки
    
    Args:
        session: Сессия базы данных
        subscription_id: ID подписки
        change_type: Тип изменения (created, activated, expired, etc.)
        **kwargs: Дополнительные параметры
        
    Returns:
        bool: Успешность отправки уведомления
    """
    service = SubscriptionNotificationService(session)
    
    if change_type == "created":
        return await service.notify_subscription_created(subscription_id)
    elif change_type == "activated":
        return await service.notify_subscription_activated(subscription_id)
    elif change_type == "expired":
        return await service.notify_subscription_expired(subscription_id)
    elif change_type == "expiring":
        days_left = kwargs.get("days_left", 1)
        return await service.notify_subscription_expiring(subscription_id, days_left)
    
    return False


async def send_admin_alert(
    session: AsyncSession,
    title: str,
    message: str,
    priority: NotificationPriority = NotificationPriority.HIGH
) -> bool:
    """
    Отправить алерт администраторам
    
    Args:
        session: Сессия базы данных
        title: Заголовок
        message: Сообщение
        priority: Приоритет
        
    Returns:
        bool: Успешность отправки
    """
    service = NotificationService(session)
    return await service.send_admin_notification(title, message, priority)


# Константы для уведомлений
class NotificationConstants:
    """Константы для системы уведомлений"""
    
    # Лимиты rate limiting (в секундах)
    RATE_LIMITS = {
        NotificationPriority.LOW: 300,      # 5 минут
        NotificationPriority.NORMAL: 60,    # 1 минута
        NotificationPriority.HIGH: 30,      # 30 секунд
        NotificationPriority.URGENT: 0      # Без лимита
    }
    
    # Максимальная длина сообщений
    MAX_TITLE_LENGTH = 100
    MAX_MESSAGE_LENGTH = 4000
    
    # Размеры пакетов для массовой отправки
    BULK_BATCH_SIZE = 50
    ADMIN_BATCH_SIZE = 10
    
    # Таймауты
    TELEGRAM_TIMEOUT = 30
    EMAIL_TIMEOUT = 60
    
    # Повторные попытки
    MAX_RETRIES = 3
    RETRY_DELAY = 1


# Исключения для системы уведомлений
class NotificationRateLimitError(NotificationError):
    """Превышен лимит частоты отправки"""
    pass


class NotificationChannelError(NotificationError):
    """Ошибка канала доставки"""
    pass


class NotificationTemplateError(NotificationError):
    """Ошибка шаблона уведомления"""
    pass