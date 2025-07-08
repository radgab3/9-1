"""
Сервис для управления подписками
"""

import asyncio
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from core.database.models import (
    User, Server, SubscriptionPlan, Subscription, VpnConfig,
    SubscriptionStatus, VpnProtocol
)
from core.database.repositories import RepositoryManager
from core.services.user_service import UserService
from core.exceptions.custom_exceptions import (
    SubscriptionNotFoundError, InsufficientFundsError, 
    ServerNotAvailableError, SubscriptionExpiredError
)
from config.settings import settings


class SubscriptionService:
    """Сервис для управления подписками"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repos = RepositoryManager(session)
        self.user_service = UserService(session)
    
    async def create_subscription(
        self,
        user_id: int,
        plan_id: int,
        server_id: Optional[int] = None,
        protocol: Optional[VpnProtocol] = None,
        payment_id: Optional[int] = None
    ) -> Subscription:
        """
        Создать новую подписку
        """
        try:
            # Получаем пользователя и план
            user = await self.repos.users.get_by_id(user_id)
            if not user:
                raise ValueError(f"User {user_id} not found")
            
            plan = await self.repos.subscription_plans.get_by_id(plan_id)
            if not plan:
                raise ValueError(f"Plan {plan_id} not found")
            
            # Выбираем сервер автоматически если не указан
            if not server_id:
                server = await self._select_best_server(user, protocol)
                if not server:
                    raise ServerNotAvailableError("No available servers")
                server_id = server.id
            else:
                server = await self.repos.servers.get_by_id(server_id)
                if not server or not server.is_active:
                    raise ServerNotAvailableError(f"Server {server_id} not available")
            
            # Определяем протокол
            if not protocol:
                protocol = await self._select_optimal_protocol(user, server)
            
            # Проверяем, есть ли активная подписка
            active_subscription = await self.repos.subscriptions.get_active_subscription(user_id)
            if active_subscription:
                # Если есть активная подписка, расширяем её или создаем новую
                logger.info(f"User {user_id} already has active subscription")
            
            # Создаем подписку
            subscription_data = {
                "user_id": user_id,
                "server_id": server_id,
                "plan_id": plan_id,
                "active_protocol": protocol,
                "status": SubscriptionStatus.PENDING,
                "traffic_limit_gb": plan.traffic_limit_gb,
                "auto_renewal": False
            }
            
            subscription = await self.repos.subscriptions.create(**subscription_data)
            
            # Логируем создание
            await self.repos.user_activities.log_activity(
                user_id=user_id,
                action="subscription_created",
                details={
                    "subscription_id": subscription.id,
                    "plan_name": plan.name,
                    "server_name": server.name,
                    "protocol": protocol.value,
                    "payment_id": payment_id
                }
            )
            
            await self.repos.commit()
            logger.info(f"Subscription created: {subscription.id} for user {user_id}")
            
            return subscription
            
        except Exception as e:
            await self.repos.rollback()
            logger.error(f"Error creating subscription: {e}")
            raise
    
    async def activate_subscription(self, subscription_id: int) -> bool:
        """
        Активировать подписку после успешной оплаты
        """
        try:
            subscription = await self.repos.subscriptions.get_by_id(subscription_id)
            if not subscription:
                raise SubscriptionNotFoundError(f"Subscription {subscription_id} not found")
            
            # Рассчитываем даты
            now = datetime.utcnow()
            plan = subscription.plan
            expires_at = now + timedelta(days=plan.duration_days)
            
            # Обновляем подписку
            await self.repos.subscriptions.update(
                subscription_id,
                status=SubscriptionStatus.ACTIVE,
                started_at=now,
                expires_at=expires_at
            )
            
            # Логируем активацию
            await self.repos.user_activities.log_activity(
                user_id=subscription.user_id,
                action="subscription_activated",
                details={
                    "subscription_id": subscription_id,
                    "expires_at": expires_at.isoformat(),
                    "plan_duration": plan.duration_days
                }
            )
            
            await self.repos.commit()
            logger.info(f"Subscription {subscription_id} activated")
            
            return True
            
        except Exception as e:
            await self.repos.rollback()
            logger.error(f"Error activating subscription {subscription_id}: {e}")
            return False
    
    async def extend_subscription(
        self,
        subscription_id: int,
        additional_days: int,
        reason: str = "payment"
    ) -> bool:
        """
        Продлить подписку
        """
        try:
            subscription = await self.repos.subscriptions.get_by_id(subscription_id)
            if not subscription:
                raise SubscriptionNotFoundError(f"Subscription {subscription_id} not found")
            
            # Рассчитываем новую дату окончания
            current_expires = subscription.expires_at or datetime.utcnow()
            new_expires = current_expires + timedelta(days=additional_days)
            
            # Обновляем подписку
            await self.repos.subscriptions.update(
                subscription_id,
                expires_at=new_expires,
                status=SubscriptionStatus.ACTIVE if subscription.status == SubscriptionStatus.EXPIRED else subscription.status
            )
            
            # Логируем продление
            await self.repos.user_activities.log_activity(
                user_id=subscription.user_id,
                action="subscription_extended",
                details={
                    "subscription_id": subscription_id,
                    "additional_days": additional_days,
                    "new_expires_at": new_expires.isoformat(),
                    "reason": reason
                }
            )
            
            await self.repos.commit()
            logger.info(f"Subscription {subscription_id} extended by {additional_days} days")
            
            return True
            
        except Exception as e:
            await self.repos.rollback()
            logger.error(f"Error extending subscription {subscription_id}: {e}")
            return False
    
    async def suspend_subscription(
        self,
        subscription_id: int,
        reason: str = "manual",
        admin_id: Optional[int] = None
    ) -> bool:
        """
        Приостановить подписку
        """
        try:
            success = await self.repos.subscriptions.update_status(
                subscription_id, SubscriptionStatus.SUSPENDED
            )
            
            if success:
                subscription = await self.repos.subscriptions.get_by_id(subscription_id)
                await self.repos.user_activities.log_activity(
                    user_id=subscription.user_id,
                    action="subscription_suspended",
                    details={
                        "subscription_id": subscription_id,
                        "reason": reason,
                        "admin_id": admin_id,
                        "suspended_at": datetime.utcnow().isoformat()
                    }
                )
                await self.repos.commit()
                logger.info(f"Subscription {subscription_id} suspended")
            
            return success
            
        except Exception as e:
            await self.repos.rollback()
            logger.error(f"Error suspending subscription {subscription_id}: {e}")
            return False
    
    async def resume_subscription(
        self,
        subscription_id: int,
        admin_id: Optional[int] = None
    ) -> bool:
        """
        Возобновить приостановленную подписку
        """
        try:
            subscription = await self.repos.subscriptions.get_by_id(subscription_id)
            if not subscription:
                return False
            
            # Проверяем, не истекла ли подписка
            if subscription.expires_at and subscription.expires_at <= datetime.utcnow():
                new_status = SubscriptionStatus.EXPIRED
            else:
                new_status = SubscriptionStatus.ACTIVE
            
            success = await self.repos.subscriptions.update_status(subscription_id, new_status)
            
            if success:
                await self.repos.user_activities.log_activity(
                    user_id=subscription.user_id,
                    action="subscription_resumed",
                    details={
                        "subscription_id": subscription_id,
                        "new_status": new_status.value,
                        "admin_id": admin_id,
                        "resumed_at": datetime.utcnow().isoformat()
                    }
                )
                await self.repos.commit()
                logger.info(f"Subscription {subscription_id} resumed")
            
            return success
            
        except Exception as e:
            await self.repos.rollback()
            logger.error(f"Error resuming subscription {subscription_id}: {e}")
            return False
    
    async def get_user_subscriptions(self, user_id: int) -> List[Subscription]:
        """
        Получить все подписки пользователя
        """
        return await self.repos.subscriptions.get_user_subscriptions(user_id)
    
    async def get_active_subscription(self, user_id: int) -> Optional[Subscription]:
        """
        Получить активную подписку пользователя
        """
        return await self.repos.subscriptions.get_active_subscription(user_id)
    
    async def check_subscription_expiry(self, user_id: int) -> Dict[str, Any]:
        """
        Проверить истечение подписки пользователя
        """
        try:
            subscription = await self.get_active_subscription(user_id)
            
            if not subscription:
                return {
                    "has_subscription": False,
                    "is_active": False,
                    "expires_at": None,
                    "days_left": 0,
                    "expired": True
                }
            
            now = datetime.utcnow()
            expires_at = subscription.expires_at
            
            if not expires_at:
                return {
                    "has_subscription": True,
                    "is_active": True,
                    "expires_at": None,
                    "days_left": float('inf'),
                    "expired": False
                }
            
            days_left = (expires_at - now).days
            expired = expires_at <= now
            
            # Если подписка истекла, обновляем статус
            if expired and subscription.status == SubscriptionStatus.ACTIVE:
                await self.repos.subscriptions.update_status(
                    subscription.id, SubscriptionStatus.EXPIRED
                )
                await self.repos.commit()
            
            return {
                "has_subscription": True,
                "is_active": subscription.status == SubscriptionStatus.ACTIVE and not expired,
                "expires_at": expires_at,
                "days_left": max(0, days_left),
                "expired": expired,
                "status": subscription.status.value
            }
            
        except Exception as e:
            logger.error(f"Error checking subscription expiry for user {user_id}: {e}")
            return {
                "has_subscription": False,
                "is_active": False,
                "expires_at": None,
                "days_left": 0,
                "expired": True
            }
    
    async def update_traffic_usage(self, subscription_id: int, traffic_gb: float) -> bool:
        """
        Обновить использование трафика
        """
        try:
            subscription = await self.repos.subscriptions.get_by_id(subscription_id)
            if not subscription:
                return False
            
            new_traffic = subscription.traffic_used_gb + traffic_gb
            
            # Проверяем лимит трафика
            if subscription.traffic_limit_gb and new_traffic >= subscription.traffic_limit_gb:
                # Приостанавливаем подписку при превышении лимита
                await self.suspend_subscription(
                    subscription_id, 
                    reason="traffic_limit_exceeded"
                )
                
                await self.repos.user_activities.log_activity(
                    user_id=subscription.user_id,
                    action="traffic_limit_exceeded",
                    details={
                        "subscription_id": subscription_id,
                        "traffic_used": new_traffic,
                        "traffic_limit": subscription.traffic_limit_gb
                    }
                )
            
            success = await self.repos.subscriptions.update(
                subscription_id,
                traffic_used_gb=new_traffic
            )
            
            if success:
                await self.repos.commit()
            
            return success
            
        except Exception as e:
            await self.repos.rollback()
            logger.error(f"Error updating traffic usage {subscription_id}: {e}")
            return False
    
    async def get_expiring_subscriptions(self, hours: int = 24) -> List[Subscription]:
        """
        Получить подписки, истекающие в ближайшее время
        """
        return await self.repos.subscriptions.get_expiring_subscriptions(hours)
    
    async def _select_best_server(self, user: User, protocol: Optional[VpnProtocol] = None) -> Optional[Server]:
        """
        Выбрать лучший сервер для пользователя
        """
        try:
            # Получаем серверы, поддерживающие нужный протокол
            if protocol:
                servers = await self.repos.servers.get_by_protocol(protocol)
            else:
                servers = await self.repos.servers.get_all_active()
            
            if not servers:
                return None
            
            # Для российских пользователей предпочитаем серверы ближайших стран
            if user.country_code in settings.RUSSIA_COUNTRY_CODES:
                # Ищем серверы в приоритетных странах
                preferred_countries = ["NL", "DE", "FI", "LV", "EE"]
                for country in preferred_countries:
                    country_servers = [s for s in servers if s.country_code == country]
                    if country_servers:
                        # Выбираем сервер с наименьшей нагрузкой
                        return min(country_servers, key=lambda s: s.current_users / s.max_users)
            
            # Выбираем сервер с наименьшей нагрузкой
            return min(servers, key=lambda s: s.current_users / s.max_users)
            
        except Exception as e:
            logger.error(f"Error selecting best server: {e}")
            return None
    
    async def _select_optimal_protocol(self, user: User, server: Server) -> VpnProtocol:
        """
        Выбрать оптимальный протокол для пользователя и сервера
        """
        try:
            # Если у пользователя есть предпочтения и автовыбор отключен
            if user.preferred_protocol and not user.auto_select_protocol:
                if user.preferred_protocol.value in server.supported_protocols:
                    return user.preferred_protocol
            
            # Для российских пользователей приоритет VLESS
            if user.country_code in settings.RUSSIA_COUNTRY_CODES:
                for protocol in [VpnProtocol.VLESS, VpnProtocol.VMESS, VpnProtocol.TROJAN]:
                    if protocol.value in server.supported_protocols:
                        return protocol
            
            # По умолчанию выбираем первый доступный протокол
            supported = server.supported_protocols
            if "vless" in supported:
                return VpnProtocol.VLESS
            elif "openvpn" in supported:
                return VpnProtocol.OPENVPN
            elif "wireguard" in supported:
                return VpnProtocol.WIREGUARD
            
            # Если ничего не найдено, используем основной протокол сервера
            return server.primary_protocol
            
        except Exception as e:
            logger.error(f"Error selecting optimal protocol: