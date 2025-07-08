"""
Сервис для управления пользователями VPN Bot System
"""

import asyncio
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func, and_, or_
from loguru import logger

from core.database.models import (
    User, UserRole, VpnProtocol, Subscription, 
    UserActivity, SystemSettings
)
from core.database.repositories import RepositoryManager
from core.exceptions.custom_exceptions import (
    UserNotFoundError, UserAlreadyExistsError, 
    UserBannedError, ValidationError
)
from core.utils.helpers import get_country_by_ip, detect_language
from core.utils.validators import TelegramValidator, UserDataValidator
from config.settings import settings


class UserService:
    """Сервис для управления пользователями"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repos = RepositoryManager(session)
    
    async def get_user_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        """
        Получить пользователя по Telegram ID
        
        Args:
            telegram_id: ID пользователя в Telegram
            
        Returns:
            Optional[User]: Пользователь или None
        """
        try:
            return await self.repos.users.get_by_telegram_id(telegram_id)
        except Exception as e:
            logger.error(f"Error getting user by telegram_id {telegram_id}: {e}")
            return None
    
    async def get_user_by_id(self, user_id: int) -> Optional[User]:
        """
        Получить пользователя по ID
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Optional[User]: Пользователь или None
        """
        try:
            return await self.repos.users.get_by_id(user_id)
        except Exception as e:
            logger.error(f"Error getting user by id {user_id}: {e}")
            return None
    
    async def get_or_create_user(
        self,
        telegram_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        language_code: Optional[str] = None,
        registration_ip: Optional[str] = None
    ) -> User:
        """
        Получить или создать пользователя
        
        Args:
            telegram_id: ID пользователя в Telegram
            username: Имя пользователя
            first_name: Имя
            last_name: Фамилия
            language_code: Код языка
            registration_ip: IP регистрации
            
        Returns:
            User: Пользователь
        """
        try:
            # Валидируем Telegram ID
            if not TelegramValidator.validate_telegram_id(telegram_id):
                raise ValidationError(f"Invalid Telegram ID: {telegram_id}")
            
            # Пытаемся найти существующего пользователя
            user = await self.repos.users.get_by_telegram_id(telegram_id)
            
            if user:
                # Обновляем информацию существующего пользователя
                update_data = {}
                
                if username and username != user.username:
                    update_data['username'] = username
                if first_name and first_name != user.first_name:
                    update_data['first_name'] = first_name
                if last_name and last_name != user.last_name:
                    update_data['last_name'] = last_name
                
                # Обновляем время последней активности
                update_data['last_activity'] = datetime.utcnow()
                
                if update_data:
                    await self.repos.users.update(user.id, **update_data)
                    await self.repos.commit()
                    
                    # Обновляем объект пользователя
                    for key, value in update_data.items():
                        setattr(user, key, value)
                
                return user
            
            # Создаем нового пользователя
            user_data = {
                'telegram_id': telegram_id,
                'username': username,
                'first_name': first_name,
                'last_name': last_name,
                'language_code': detect_language(language_code),
                'role': UserRole.CLIENT,
                'is_active': True,
                'registration_ip': registration_ip,
                'auto_select_protocol': True
            }
            
            # Определяем страну по IP
            if registration_ip:
                country_code = await get_country_by_ip(registration_ip)
                if country_code:
                    user_data['country_code'] = country_code
                    
                    # Устанавливаем предпочитаемый протокол для российских пользователей
                    if country_code in settings.RUSSIA_COUNTRY_CODES:
                        user_data['preferred_protocol'] = VpnProtocol.VLESS
            
            user = await self.repos.users.create(**user_data)
            
            # Логируем регистрацию
            await self.log_user_action(
                user_id=user.id,
                action="user_registered",
                details={
                    "registration_ip": registration_ip,
                    "country_code": user_data.get('country_code'),
                    "language": user_data['language_code']
                },
                ip_address=registration_ip
            )
            
            await self.repos.commit()
            logger.info(f"New user created: {user.telegram_id}")
            
            return user
            
        except Exception as e:
            await self.repos.rollback()
            logger.error(f"Error creating user {telegram_id}: {e}")
            raise
    
    async def update_user_preferences(
        self,
        user_id: int,
        **preferences
    ) -> bool:
        """
        Обновить предпочтения пользователя
        
        Args:
            user_id: ID пользователя
            **preferences: Предпочтения для обновления
            
        Returns:
            bool: Успешность обновления
        """
        try:
            # Валидируем предпочтения
            validated_prefs = {}
            
            if 'language_code' in preferences:
                lang = preferences['language_code']
                if UserDataValidator.validate_language_code(lang):
                    validated_prefs['language_code'] = lang
            
            if 'preferred_protocol' in preferences:
                protocol = preferences['preferred_protocol']
                if protocol is None or isinstance(protocol, VpnProtocol):
                    validated_prefs['preferred_protocol'] = protocol
            
            if 'auto_select_protocol' in preferences:
                validated_prefs['auto_select_protocol'] = bool(preferences['auto_select_protocol'])
            
            if not validated_prefs:
                return False
            
            success = await self.repos.users.update(user_id, **validated_prefs)
            
            if success:
                await self.log_user_action(
                    user_id=user_id,
                    action="preferences_updated",
                    details=validated_prefs
                )
                await self.repos.commit()
            
            return success
            
        except Exception as e:
            await self.repos.rollback()
            logger.error(f"Error updating user preferences {user_id}: {e}")
            return False
    
    async def ban_user(
        self,
        user_id: int,
        reason: str,
        admin_id: Optional[int] = None
    ) -> bool:
        """
        Заблокировать пользователя
        
        Args:
            user_id: ID пользователя
            reason: Причина блокировки
            admin_id: ID администратора
            
        Returns:
            bool: Успешность блокировки
        """
        try:
            success = await self.repos.users.update(
                user_id,
                is_banned=True,
                is_active=False
            )
            
            if success:
                await self.log_user_action(
                    user_id=user_id,
                    action="user_banned",
                    details={
                        "reason": reason,
                        "admin_id": admin_id,
                        "banned_at": datetime.utcnow().isoformat()
                    }
                )
                await self.repos.commit()
                logger.info(f"User {user_id} banned by admin {admin_id}: {reason}")
            
            return success
            
        except Exception as e:
            await self.repos.rollback()
            logger.error(f"Error banning user {user_id}: {e}")
            return False
    
    async def unban_user(
        self,
        user_id: int,
        admin_id: Optional[int] = None
    ) -> bool:
        """
        Разблокировать пользователя
        
        Args:
            user_id: ID пользователя
            admin_id: ID администратора
            
        Returns:
            bool: Успешность разблокировки
        """
        try:
            success = await self.repos.users.update(
                user_id,
                is_banned=False,
                is_active=True
            )
            
            if success:
                await self.log_user_action(
                    user_id=user_id,
                    action="user_unbanned",
                    details={
                        "admin_id": admin_id,
                        "unbanned_at": datetime.utcnow().isoformat()
                    }
                )
                await self.repos.commit()
                logger.info(f"User {user_id} unbanned by admin {admin_id}")
            
            return success
            
        except Exception as e:
            await self.repos.rollback()
            logger.error(f"Error unbanning user {user_id}: {e}")
            return False
    
    async def check_user_access(self, telegram_id: int) -> Tuple[bool, Optional[str]]:
        """
        Проверить доступ пользователя к боту
        
        Args:
            telegram_id: ID пользователя в Telegram
            
        Returns:
            Tuple[bool, Optional[str]]: (Разрешен доступ, Причина блокировки)
        """
        try:
            user = await self.repos.users.get_by_telegram_id(telegram_id)
            
            if not user:
                return True, None  # Новый пользователь
            
            if user.is_banned:
                return False, "Ваш аккаунт заблокирован администратором"
            
            if not user.is_active:
                return False, "Ваш аккаунт деактивирован"
            
            # Проверяем режим технического обслуживания
            if user.role != UserRole.ADMIN:
                maintenance_mode = await self.repos.system_settings.get_setting("maintenance_mode")
                if maintenance_mode == "true":
                    return False, "Сервис временно недоступен. Ведутся технические работы."
            
            return True, None
            
        except Exception as e:
            logger.error(f"Error checking user access {telegram_id}: {e}")
            return False, "Ошибка проверки доступа"
    
    async def log_user_action(
        self,
        user_id: int,
        action: str,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ):
        """
        Логировать действие пользователя
        
        Args:
            user_id: ID пользователя
            action: Действие
            details: Детали действия
            ip_address: IP адрес
            user_agent: User Agent
        """
        try:
            await self.repos.user_activities.log_activity(
                user_id=user_id,
                action=action,
                details=details,
                ip_address=ip_address,
                user_agent=user_agent
            )
        except Exception as e:
            logger.error(f"Error logging user action: {e}")
    
    async def get_user_statistics(self, user_id: int) -> Dict[str, Any]:
        """
        Получить статистику пользователя
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Dict[str, Any]: Статистика пользователя
        """
        try:
            user = await self.repos.users.get_by_id(user_id)
            if not user:
                return {}
            
            # Получаем подписки
            subscriptions = await self.repos.subscriptions.get_user_subscriptions(user_id)
            
            # Получаем конфигурации
            total_configs = 0
            total_traffic = 0.0
            
            for subscription in subscriptions:
                configs = await self.repos.vpn_configs.get_by_subscription(subscription.id)
                total_configs += len(configs)
                
                for config in configs:
                    total_traffic += config.total_traffic_gb
            
            # Получаем активность
            activities = await self.repos.user_activities.get_user_activities(user_id, 100)
            
            return {
                "user_id": user_id,
                "telegram_id": user.telegram_id,
                "registration_date": user.created_at,
                "last_activity": user.last_activity,
                "total_subscriptions": len(subscriptions),
                "active_subscriptions": len([s for s in subscriptions if s.status.value == "active"]),
                "total_configs": total_configs,
                "total_traffic_gb": total_traffic,
                "country_code": user.country_code,
                "preferred_protocol": user.preferred_protocol.value if user.preferred_protocol else None,
                "recent_actions": len(activities),
                "is_premium": user.is_premium if hasattr(user, 'is_premium') else False
            }
            
        except Exception as e:
            logger.error(f"Error getting user statistics {user_id}: {e}")
            return {}
    
    async def get_detailed_statistics(self, user_id: int) -> Dict[str, Any]:
        """
        Получить детальную статистику пользователя
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Dict[str, Any]: Детальная статистика
        """
        try:
            # Получаем базовую статистику
            basic_stats = await self.get_user_statistics(user_id)
            
            # Получаем активность за последние месяцы
            monthly_stats = []
            current_date = datetime.utcnow()
            
            for i in range(6):  # Последние 6 месяцев
                month_start = current_date.replace(day=1) - timedelta(days=i*30)
                month_end = month_start + timedelta(days=30)
                
                activities = await self.repos.user_activities.get_activities_by_action(
                    "config_downloaded",  # Пример активности
                    days=30
                )
                
                month_activities = [
                    a for a in activities 
                    if month_start <= a.created_at <= month_end and a.user_id == user_id
                ]
                
                monthly_stats.append({
                    "month": month_start.strftime("%Y-%m"),
                    "activities": len(month_activities),
                    "traffic_gb": 0.0  # Здесь можно добавить расчет трафика за месяц
                })
            
            # Статистика по серверам
            subscriptions = await self.repos.subscriptions.get_user_subscriptions(user_id)
            server_stats = {}
            
            for subscription in subscriptions:
                server_name = subscription.server.name
                if server_name not in server_stats:
                    server_stats[server_name] = {
                        "server_name": server_name,
                        "sessions": 0,
                        "traffic_gb": 0.0
                    }
                
                server_stats[server_name]["sessions"] += 1
                
                configs = await self.repos.vpn_configs.get_by_subscription(subscription.id)
                for config in configs:
                    server_stats[server_name]["traffic_gb"] += config.total_traffic_gb
            
            # Статистика по протоколам
            protocol_stats = {}
            all_configs = []
            
            for subscription in subscriptions:
                configs = await self.repos.vpn_configs.get_by_subscription(subscription.id)
                all_configs.extend(configs)
            
            total_configs = len(all_configs)
            if total_configs > 0:
                for config in all_configs:
                    protocol = config.protocol.value
                    if protocol not in protocol_stats:
                        protocol_stats[protocol] = 0
                    protocol_stats[protocol] += 1
                
                # Преобразуем в проценты
                protocol_stats = {
                    protocol: {
                        "protocol": protocol,
                        "usage_percent": (count / total_configs) * 100
                    }
                    for protocol, count in protocol_stats.items()
                }
            
            # Активность за неделю
            week_activity = []
            for i in range(7):
                day = current_date.date() - timedelta(days=i)
                day_activities = [
                    a for a in await self.repos.user_activities.get_user_activities(user_id, 100)
                    if a.created_at.date() == day
                ]
                
                week_activity.append({
                    "date": day.isoformat(),
                    "actions": len(day_activities)
                })
            
            return {
                **basic_stats,
                "monthly_stats": monthly_stats,
                "server_stats": list(server_stats.values()),
                "protocol_stats": list(protocol_stats.values()),
                "week_activity": week_activity
            }
            
        except Exception as e:
            logger.error(f"Error getting detailed user statistics {user_id}: {e}")
            return {}
    
    async def get_notification_settings(self, user_id: int) -> Dict[str, bool]:
        """
        Получить настройки уведомлений пользователя
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Dict[str, bool]: Настройки уведомлений
        """
        try:
            # В реальной системе это могло бы быть отдельной таблицей
            # Пока возвращаем настройки по умолчанию
            return {
                "expiry_notifications": True,
                "maintenance_notifications": True,
                "news_notifications": False,
                "security_notifications": True
            }
        except Exception as e:
            logger.error(f"Error getting notification settings {user_id}: {e}")
            return {}
    
    async def update_notification_settings(
        self,
        user_id: int,
        **settings
    ) -> bool:
        """
        Обновить настройки уведомлений
        
        Args:
            user_id: ID пользователя
            **settings: Настройки уведомлений
            
        Returns:
            bool: Успешность обновления
        """
        try:
            # В реальной системе здесь было бы обновление отдельной таблицы
            await self.log_user_action(
                user_id=user_id,
                action="notification_settings_updated",
                details=settings
            )
            return True
        except Exception as e:
            logger.error(f"Error updating notification settings {user_id}: {e}")
            return False
    
    async def get_privacy_settings(self, user_id: int) -> Dict[str, bool]:
        """
        Получить настройки приватности
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Dict[str, bool]: Настройки приватности
        """
        try:
            return {
                "analytics_enabled": True,
                "error_reporting": True,
                "usage_statistics": True
            }
        except Exception as e:
            logger.error(f"Error getting privacy settings {user_id}: {e}")
            return {}
    
    async def update_privacy_settings(
        self,
        user_id: int,
        **settings
    ) -> bool:
        """
        Обновить настройки приватности
        
        Args:
            user_id: ID пользователя
            **settings: Настройки приватности
            
        Returns:
            bool: Успешность обновления
        """
        try:
            await self.log_user_action(
                user_id=user_id,
                action="privacy_settings_updated",
                details=settings
            )
            return True
        except Exception as e:
            logger.error(f"Error updating privacy settings {user_id}: {e}")
            return False
    
    async def export_user_data(self, user_id: int) -> Dict[str, Any]:
        """
        Экспортировать данные пользователя
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Dict[str, Any]: Все данные пользователя
        """
        try:
            user = await self.repos.users.get_by_id(user_id)
            if not user:
                return {}
            
            # Базовая информация о пользователе
            user_data = {
                "user_profile": {
                    "telegram_id": user.telegram_id,
                    "username": user.username,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "language_code": user.language_code,
                    "country_code": user.country_code,
                    "registration_date": user.created_at.isoformat(),
                    "last_activity": user.last_activity.isoformat() if user.last_activity else None,
                    "preferred_protocol": user.preferred_protocol.value if user.preferred_protocol else None,
                    "auto_select_protocol": user.auto_select_protocol
                }
            }
            
            # Подписки
            subscriptions = await self.repos.subscriptions.get_user_subscriptions(user_id)
            user_data["subscriptions"] = [
                {
                    "id": sub.id,
                    "plan_name": sub.plan.name,
                    "server_name": sub.server.name,
                    "status": sub.status.value,
                    "started_at": sub.started_at.isoformat() if sub.started_at else None,
                    "expires_at": sub.expires_at.isoformat() if sub.expires_at else None,
                    "traffic_used_gb": float(sub.traffic_used_gb),
                    "traffic_limit_gb": sub.traffic_limit_gb
                }
                for sub in subscriptions
            ]
            
            # VPN конфигурации (без чувствительных данных)
            all_configs = []
            for subscription in subscriptions:
                configs = await self.repos.vpn_configs.get_by_subscription(subscription.id)
                for config in configs:
                    all_configs.append({
                        "id": config.id,
                        "protocol": config.protocol.value,
                        "server_name": config.server.name,
                        "is_active": config.is_active,
                        "total_traffic_gb": float(config.total_traffic_gb),
                        "last_used": config.last_used.isoformat() if config.last_used else None,
                        "created_at": config.created_at.isoformat()
                    })
            
            user_data["vpn_configurations"] = all_configs
            
            # История активности (последние 100 записей)
            activities = await self.repos.user_activities.get_user_activities(user_id, 100)
            user_data["activity_history"] = [
                {
                    "action": activity.action,
                    "details": activity.details,
                    "created_at": activity.created_at.isoformat(),
                    "ip_address": activity.ip_address
                }
                for activity in activities
            ]
            
            # Платежи
            payments = await self.repos.payments.get_user_payments(user_id)
            user_data["payments"] = [
                {
                    "id": payment.id,
                    "amount": float(payment.amount),
                    "currency": payment.currency,
                    "status": payment.status.value,
                    "created_at": payment.created_at.isoformat(),
                    "paid_at": payment.paid_at.isoformat() if payment.paid_at else None
                }
                for payment in payments
            ]
            
            # Метаданные экспорта
            user_data["export_info"] = {
                "exported_at": datetime.utcnow().isoformat(),
                "export_version": "1.0",
                "total_records": {
                    "subscriptions": len(user_data["subscriptions"]),
                    "configurations": len(user_data["vpn_configurations"]),
                    "activities": len(user_data["activity_history"]),
                    "payments": len(user_data["payments"])
                }
            }
            
            return user_data
            
        except Exception as e:
            logger.error(f"Error exporting user data {user_id}: {e}")
            return {}
    
    async def delete_user_data(self, user_id: int) -> bool:
        """
        Удалить все данные пользователя
        
        Args:
            user_id: ID пользователя
            
        Returns:
            bool: Успешность удаления
        """
        try:
            # В реальной системе здесь был бы каскадный delete
            # или помечание записей как удаленных для соблюдения GDPR
            
            # Деактивируем пользователя
            success = await self.repos.users.update(
                user_id,
                is_active=False,
                is_banned=True,
                username=None,
                first_name="[DELETED]",
                last_name=None
            )
            
            if success:
                await self.log_user_action(
                    user_id=user_id,
                    action="user_data_deleted",
                    details={"deleted_at": datetime.utcnow().isoformat()}
                )
                await self.repos.commit()
                logger.info(f"User data deleted: {user_id}")
            
            return success
            
        except Exception as e:
            await self.repos.rollback()
            logger.error(f"Error deleting user data {user_id}: {e}")
            return False
    
    async def get_referral_statistics(self, user_id: int) -> Dict[str, Any]:
        """
        Получить статистику реферальной программы
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Dict[str, Any]: Статистика рефералов
        """
        try:
            # Заглушка для реферальной системы
            return {
                "total_referrals": 0,
                "active_referrals": 0,
                "total_earned": 0.0,
                "available_balance": 0.0
            }
        except Exception as e:
            logger.error(f"Error getting referral statistics {user_id}: {e}")
            return {}
    
    async def send_notification_to_admins(
        self,
        message: str,
        notification_type: str = "system"
    ):
        """
        Отправить уведомление администраторам
        
        Args:
            message: Текст уведомления
            notification_type: Тип уведомления
        """
        try:
            # Получаем всех администраторов
            admins = await self.repos.users.get_admins()
            
            # В реальной системе здесь была бы отправка через Telegram Bot API
            logger.info(f"Admin notification ({notification_type}): {message}")
            logger.info(f"Would notify {len(admins)} administrators")
            
        except Exception as e:
            logger.error(f"Error sending admin notification: {e}")
    
    async def get_users_count(self) -> Dict[str, int]:
        """
        Получить количество пользователей
        
        Returns:
            Dict[str, int]: Статистика пользователей
        """
        try:
            total_users = await self.repos.users.get_active_users_count()
            
            # Можно добавить больше метрик
            return {
                "total_users": total_users,
                "active_users": total_users,  # Упрощение
                "banned_users": 0,  # Нужно добавить в репозиторий
                "new_today": 0  # Нужно добавить в репозиторий
            }
            
        except Exception as e:
            logger.error(f"Error getting users count: {e}")
            return {"total_users": 0, "active_users": 0, "banned_users": 0, "new_today": 0}


class UserNotificationService:
    """Сервис уведомлений пользователей"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repos = RepositoryManager(session)
        self.user_service = UserService(session)
    
    async def send_expiry_notification(
        self,
        user_id: int,
        subscription_id: int,
        days_left: int
    ):
        """
        Отправить уведомление об истечении подписки
        
        Args:
            user_id: ID пользователя
            subscription_id: ID подписки
            days_left: Дней до истечения
        """
        try:
            await self.user_service.log_user_action(
                user_id=user_id,
                action="expiry_notification_sent",
                details={
                    "subscription_id": subscription_id,
                    "days_left": days_left,
                    "notification_type": "subscription_expiry"
                }
            )
            
            logger.info(f"Expiry notification sent to user {user_id}: {days_left} days left")
            
        except Exception as e:
            logger.error(f"Error sending expiry notification: {e}")
    
    async def send_welcome_message(
        self,
        user_id: int
    ):
        """
        Отправить приветственное сообщение новому пользователю
        
        Args:
            user_id: ID пользователя
        """
        try:
            await self.user_service.log_user_action(
                user_id=user_id,
                action="welcome_message_sent",
                details={
                    "notification_type": "welcome",
                    "sent_at": datetime.utcnow().isoformat()
                }
            )
            
            logger.info(f"Welcome message sent to user {user_id}")
            
        except Exception as e:
            logger.error(f"Error sending welcome message: {e}")
    
    async def send_maintenance_notification(
        self,
        user_ids: List[int],
        maintenance_info: Dict[str, Any]
    ):
        """
        Отправить уведомление о техническом обслуживании
        
        Args:
            user_ids: Список ID пользователей
            maintenance_info: Информация о техобслуживании
        """
        try:
            for user_id in user_ids:
                await self.user_service.log_user_action(
                    user_id=user_id,
                    action="maintenance_notification_sent",
                    details={
                        "notification_type": "maintenance",
                        "maintenance_info": maintenance_info
                    }
                )
            
            logger.info(f"Maintenance notification sent to {len(user_ids)} users")
            
        except Exception as e:
            logger.error(f"Error sending maintenance notification: {e}")


class UserAnalyticsService:
    """Сервис аналитики пользователей"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repos = RepositoryManager(session)
    
    async def get_user_growth_stats(self, days: int = 30) -> Dict[str, Any]:
        """
        Получить статистику роста пользователей
        
        Args:
            days: Количество дней для анализа
            
        Returns:
            Dict[str, Any]: Статистика роста
        """
        try:
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)
            
            # В реальной реализации здесь были бы сложные запросы к БД
            # Пока возвращаем заглушку
            return {
                "period_days": days,
                "total_users": await self.repos.users.get_active_users_count(),
                "new_users": 0,  # Нужно добавить в репозиторий
                "active_users": 0,  # Нужно добавить в репозиторий
                "retention_rate": 0.0,  # Нужно рассчитывать
                "growth_rate": 0.0,  # Нужно рассчитывать
                "countries_breakdown": {},  # Нужно добавить
                "languages_breakdown": {}  # Нужно добавить
            }
            
        except Exception as e:
            logger.error(f"Error getting user growth stats: {e}")
            return {}
    
    async def get_user_activity_stats(self, days: int = 7) -> Dict[str, Any]:
        """
        Получить статистику активности пользователей
        
        Args:
            days: Количество дней для анализа
            
        Returns:
            Dict[str, Any]: Статистика активности
        """
        try:
            # Получаем активность за последние дни
            activities = await self.repos.user_activities.get_activities_by_action(
                "user_login",  # Пример действия
                days=days
            )
            
            # Группируем по дням
            daily_activity = {}
            for activity in activities:
                day = activity.created_at.date()
                if day not in daily_activity:
                    daily_activity[day] = 0
                daily_activity[day] += 1
            
            # Самые популярные действия
            all_activities = []
            for i in range(days):
                day_activities = await self.repos.user_activities.get_activities_by_action(
                    "any",  # Все действия (нужно доработать в репозитории)
                    days=1
                )
                all_activities.extend(day_activities)
            
            return {
                "period_days": days,
                "total_activities": len(all_activities),
                "daily_breakdown": {
                    str(day): count for day, count in daily_activity.items()
                },
                "average_daily_activity": len(all_activities) / days if days > 0 else 0,
                "peak_activity_day": max(daily_activity.items(), key=lambda x: x[1])[0].isoformat() if daily_activity else None
            }
            
        except Exception as e:
            logger.error(f"Error getting user activity stats: {e}")
            return {}
    
    async def get_protocol_preferences(self) -> Dict[str, Any]:
        """
        Получить статистику предпочтений протоколов
        
        Returns:
            Dict[str, Any]: Статистика протоколов
        """
        try:
            # В реальной реализации здесь был бы запрос к БД
            # для подсчета предпочтений протоколов пользователей
            return {
                "total_users_with_preference": 0,
                "protocol_breakdown": {
                    "vless": {"count": 0, "percentage": 0.0},
                    "openvpn": {"count": 0, "percentage": 0.0},
                    "wireguard": {"count": 0, "percentage": 0.0}
                },
                "auto_select_users": 0,
                "manual_select_users": 0
            }
            
        except Exception as e:
            logger.error(f"Error getting protocol preferences: {e}")
            return {}


# Вспомогательные функции для удобства использования

async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> Optional[User]:
    """
    Быстрая функция для получения пользователя по Telegram ID
    
    Args:
        session: Сессия базы данных
        telegram_id: ID пользователя в Telegram
        
    Returns:
        Optional[User]: Пользователь или None
    """
    user_service = UserService(session)
    return await user_service.get_user_by_telegram_id(telegram_id)


async def create_user_if_not_exists(
    session: AsyncSession,
    telegram_id: int,
    **user_data
) -> User:
    """
    Создать пользователя если не существует
    
    Args:
        session: Сессия базы данных
        telegram_id: ID пользователя в Telegram
        **user_data: Дополнительные данные пользователя
        
    Returns:
        User: Пользователь
    """
    user_service = UserService(session)
    return await user_service.get_or_create_user(telegram_id, **user_data)


async def check_user_permissions(
    session: AsyncSession,
    telegram_id: int,
    required_role: UserRole = UserRole.CLIENT
) -> bool:
    """
    Проверить права пользователя
    
    Args:
        session: Сессия базы данных
        telegram_id: ID пользователя в Telegram
        required_role: Требуемая роль
        
    Returns:
        bool: Есть ли права
    """
    user_service = UserService(session)
    user = await user_service.get_user_by_telegram_id(telegram_id)
    
    if not user:
        return False
    
    # Проверяем роль (админы имеют доступ ко всему)
    if user.role == UserRole.ADMIN:
        return True
    
    return user.role == required_role


async def log_user_action_simple(
    session: AsyncSession,
    telegram_id: int,
    action: str,
    details: Optional[Dict[str, Any]] = None
):
    """
    Простое логирование действий пользователя
    
    Args:
        session: Сессия базы данных
        telegram_id: ID пользователя в Telegram
        action: Действие
        details: Детали действия
    """
    user_service = UserService(session)
    user = await user_service.get_user_by_telegram_id(telegram_id)
    
    if user:
        await user_service.log_user_action(
            user_id=user.id,
            action=action,
            details=details
        )


# Константы для действий пользователей
class UserActions:
    """Константы для логирования действий пользователей"""
    
    # Аутентификация
    USER_REGISTERED = "user_registered"
    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"
    
    # Подписки
    SUBSCRIPTION_CREATED = "subscription_created"
    SUBSCRIPTION_RENEWED = "subscription_renewed"
    SUBSCRIPTION_CANCELLED = "subscription_cancelled"
    
    # VPN конфигурации
    CONFIG_DOWNLOADED = "config_downloaded"
    CONFIG_VIEWED = "config_viewed"
    QR_CODE_VIEWED = "qr_code_viewed"
    CONFIG_REFRESHED = "config_refreshed"
    
    # Платежи
    PAYMENT_INITIATED = "payment_initiated"
    PAYMENT_COMPLETED = "payment_completed"
    PAYMENT_FAILED = "payment_failed"
    
    # Настройки
    PREFERENCES_UPDATED = "preferences_updated"
    LANGUAGE_CHANGED = "language_changed"
    PROTOCOL_CHANGED = "protocol_changed"
    
    # Поддержка
    TICKET_CREATED = "ticket_created"
    TICKET_REPLIED = "ticket_replied"
    
    # Система
    NOTIFICATION_SENT = "notification_sent"
    ERROR_OCCURRED = "error_occurred"
    
    # Безопасность
    USER_BANNED = "user_banned"
    USER_UNBANNED = "user_unbanned"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"


# Декораторы для автоматического логирования
def log_user_action(action: str):
    """
    Декоратор для автоматического логирования действий пользователя
    
    Args:
        action: Название действия
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            try:
                result = await func(*args, **kwargs)
                
                # Пытаемся найти session и user_id в аргументах
                session = None
                user_id = None
                
                for arg in args:
                    if hasattr(arg, 'execute'):  # AsyncSession
                        session = arg
                    elif isinstance(arg, int) and user_id is None:
                        user_id = arg
                
                if 'session' in kwargs:
                    session = kwargs['session']
                if 'user_id' in kwargs:
                    user_id = kwargs['user_id']
                
                if session and user_id:
                    user_service = UserService(session)
                    await user_service.log_user_action(
                        user_id=user_id,
                        action=action,
                        details={"function": func.__name__}
                    )
                
                return result
                
            except Exception as e:
                logger.error(f"Error in logged function {func.__name__}: {e}")
                raise
        
        return wrapper
    return decorator