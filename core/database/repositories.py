"""
Репозитории для работы с базой данных
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func, and_, or_
from sqlalchemy.orm import selectinload, joinedload
from loguru import logger

from core.database.models import (
    User, Server, SubscriptionPlan, Subscription, VpnConfig,
    Payment, SupportTicket, SupportMessage, UserActivity,
    ServerStats, SystemSettings, UserRole, SubscriptionStatus,
    VpnProtocol, PaymentStatus, TicketStatus
)


class BaseRepository:
    """Базовый репозиторий"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def commit(self):
        """Зафиксировать изменения"""
        await self.session.commit()
    
    async def rollback(self):
        """Откатить изменения"""
        await self.session.rollback()


class UserRepository(BaseRepository):
    """Репозиторий для работы с пользователями"""
    
    async def get_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        """Получить пользователя по Telegram ID"""
        try:
            result = await self.session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error getting configs by subscription {subscription_id}: {e}")
            return []
    
    async def get_by_id(self, config_id: int) -> Optional[VpnConfig]:
        """Получить конфигурацию по ID"""
        try:
            result = await self.session.execute(
                select(VpnConfig)
                .where(VpnConfig.id == config_id)
                .options(
                    selectinload(VpnConfig.server),
                    selectinload(VpnConfig.subscription)
                )
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error getting config by id {config_id}: {e}")
            return None
    
    async def create(self, **kwargs) -> VpnConfig:
        """Создать VPN конфигурацию"""
        try:
            config = VpnConfig(**kwargs)
            self.session.add(config)
            await self.session.flush()
            await self.session.refresh(config)
            return config
        except Exception as e:
            logger.error(f"Error creating VPN config: {e}")
            await self.session.rollback()
            raise
    
    async def update_usage(self, config_id: int, traffic_gb: float) -> bool:
        """Обновить статистику использования"""
        try:
            result = await self.session.execute(
                update(VpnConfig)
                .where(VpnConfig.id == config_id)
                .values(
                    total_traffic_gb=traffic_gb,
                    last_used=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
            )
            return result.rowcount > 0
        except Exception as e:
            logger.error(f"Error updating config usage {config_id}: {e}")
            return False
    
    async def deactivate(self, config_id: int) -> bool:
        """Деактивировать конфигурацию"""
        try:
            result = await self.session.execute(
                update(VpnConfig)
                .where(VpnConfig.id == config_id)
                .values(is_active=False, updated_at=datetime.utcnow())
            )
            return result.rowcount > 0
        except Exception as e:
            logger.error(f"Error deactivating config {config_id}: {e}")
            return False


class PaymentRepository(BaseRepository):
    """Репозиторий для работы с платежами"""
    
    async def get_by_external_id(self, external_id: str) -> Optional[Payment]:
        """Получить платеж по внешнему ID"""
        try:
            result = await self.session.execute(
                select(Payment).where(Payment.external_payment_id == external_id)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error getting payment by external_id {external_id}: {e}")
            return None
    
    async def get_user_payments(self, user_id: int) -> List[Payment]:
        """Получить платежи пользователя"""
        try:
            result = await self.session.execute(
                select(Payment)
                .where(Payment.user_id == user_id)
                .order_by(Payment.created_at.desc())
            )
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error getting user payments {user_id}: {e}")
            return []
    
    async def create(self, **kwargs) -> Payment:
        """Создать платеж"""
        try:
            payment = Payment(**kwargs)
            self.session.add(payment)
            await self.session.flush()
            await self.session.refresh(payment)
            return payment
        except Exception as e:
            logger.error(f"Error creating payment: {e}")
            await self.session.rollback()
            raise
    
    async def update_status(self, payment_id: int, status: PaymentStatus, **kwargs) -> bool:
        """Обновить статус платежа"""
        try:
            update_data = {"status": status}
            if status == PaymentStatus.COMPLETED:
                update_data["paid_at"] = datetime.utcnow()
            
            update_data.update(kwargs)
            
            result = await self.session.execute(
                update(Payment)
                .where(Payment.id == payment_id)
                .values(**update_data)
            )
            return result.rowcount > 0
        except Exception as e:
            logger.error(f"Error updating payment status {payment_id}: {e}")
            return False
    
    async def get_pending_payments(self) -> List[Payment]:
        """Получить ожидающие платежи"""
        try:
            result = await self.session.execute(
                select(Payment)
                .where(Payment.status == PaymentStatus.PENDING)
                .options(selectinload(Payment.user))
            )
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error getting pending payments: {e}")
            return []


class SupportTicketRepository(BaseRepository):
    """Репозиторий для работы с тикетами поддержки"""
    
    async def create(self, **kwargs) -> SupportTicket:
        """Создать тикет"""
        try:
            ticket = SupportTicket(**kwargs)
            self.session.add(ticket)
            await self.session.flush()
            await self.session.refresh(ticket)
            return ticket
        except Exception as e:
            logger.error(f"Error creating support ticket: {e}")
            await self.session.rollback()
            raise
    
    async def get_by_id(self, ticket_id: int) -> Optional[SupportTicket]:
        """Получить тикет по ID"""
        try:
            result = await self.session.execute(
                select(SupportTicket)
                .where(SupportTicket.id == ticket_id)
                .options(
                    selectinload(SupportTicket.user),
                    selectinload(SupportTicket.assigned_admin),
                    selectinload(SupportTicket.messages)
                )
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error getting ticket by id {ticket_id}: {e}")
            return None
    
    async def get_user_tickets(self, user_id: int) -> List[SupportTicket]:
        """Получить тикеты пользователя"""
        try:
            result = await self.session.execute(
                select(SupportTicket)
                .where(SupportTicket.user_id == user_id)
                .order_by(SupportTicket.created_at.desc())
            )
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error getting user tickets {user_id}: {e}")
            return []
    
    async def get_open_tickets(self) -> List[SupportTicket]:
        """Получить открытые тикеты"""
        try:
            result = await self.session.execute(
                select(SupportTicket)
                .where(SupportTicket.status.in_([TicketStatus.OPEN, TicketStatus.IN_PROGRESS]))
                .options(selectinload(SupportTicket.user))
                .order_by(SupportTicket.priority.desc(), SupportTicket.created_at.asc())
            )
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error getting open tickets: {e}")
            return []
    
    async def update_status(self, ticket_id: int, status: TicketStatus, **kwargs) -> bool:
        """Обновить статус тикета"""
        try:
            update_data = {"status": status, "updated_at": datetime.utcnow()}
            if status == TicketStatus.CLOSED:
                update_data["closed_at"] = datetime.utcnow()
            
            update_data.update(kwargs)
            
            result = await self.session.execute(
                update(SupportTicket)
                .where(SupportTicket.id == ticket_id)
                .values(**update_data)
            )
            return result.rowcount > 0
        except Exception as e:
            logger.error(f"Error updating ticket status {ticket_id}: {e}")
            return False
    
    async def assign_admin(self, ticket_id: int, admin_id: int) -> bool:
        """Назначить администратора на тикет"""
        try:
            result = await self.session.execute(
                update(SupportTicket)
                .where(SupportTicket.id == ticket_id)
                .values(
                    assigned_admin_id=admin_id,
                    status=TicketStatus.IN_PROGRESS,
                    updated_at=datetime.utcnow()
                )
            )
            return result.rowcount > 0
        except Exception as e:
            logger.error(f"Error assigning admin to ticket {ticket_id}: {e}")
            return False


class SupportMessageRepository(BaseRepository):
    """Репозиторий для работы с сообщениями поддержки"""
    
    async def create(self, **kwargs) -> SupportMessage:
        """Создать сообщение"""
        try:
            message = SupportMessage(**kwargs)
            self.session.add(message)
            await self.session.flush()
            await self.session.refresh(message)
            return message
        except Exception as e:
            logger.error(f"Error creating support message: {e}")
            await self.session.rollback()
            raise
    
    async def get_ticket_messages(self, ticket_id: int) -> List[SupportMessage]:
        """Получить сообщения тикета"""
        try:
            result = await self.session.execute(
                select(SupportMessage)
                .where(SupportMessage.ticket_id == ticket_id)
                .options(selectinload(SupportMessage.user))
                .order_by(SupportMessage.created_at.asc())
            )
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error getting ticket messages {ticket_id}: {e}")
            return []


class UserActivityRepository(BaseRepository):
    """Репозиторий для работы с активностью пользователей"""
    
    async def log_activity(self, user_id: int, action: str, details: Optional[Dict[str, Any]] = None, **kwargs):
        """Записать активность пользователя"""
        try:
            activity = UserActivity(
                user_id=user_id,
                action=action,
                details=details,
                **kwargs
            )
            self.session.add(activity)
            await self.session.flush()
        except Exception as e:
            logger.error(f"Error logging user activity: {e}")
    
    async def get_user_activities(self, user_id: int, limit: int = 50) -> List[UserActivity]:
        """Получить активность пользователя"""
        try:
            result = await self.session.execute(
                select(UserActivity)
                .where(UserActivity.user_id == user_id)
                .order_by(UserActivity.created_at.desc())
                .limit(limit)
            )
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error getting user activities {user_id}: {e}")
            return []
    
    async def get_activities_by_action(self, action: str, days: int = 7) -> List[UserActivity]:
        """Получить активность по действию за период"""
        try:
            since_date = datetime.utcnow() - timedelta(days=days)
            result = await self.session.execute(
                select(UserActivity)
                .where(
                    and_(
                        UserActivity.action == action,
                        UserActivity.created_at >= since_date
                    )
                )
                .order_by(UserActivity.created_at.desc())
            )
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error getting activities by action {action}: {e}")
            return []


class ServerStatsRepository(BaseRepository):
    """Репозиторий для работы со статистикой серверов"""
    
    async def record_stats(self, server_id: int, **stats):
        """Записать статистику сервера"""
        try:
            server_stats = ServerStats(server_id=server_id, **stats)
            self.session.add(server_stats)
            await self.session.flush()
        except Exception as e:
            logger.error(f"Error recording server stats: {e}")
    
    async def get_server_stats(self, server_id: int, hours: int = 24) -> List[ServerStats]:
        """Получить статистику сервера за период"""
        try:
            since_date = datetime.utcnow() - timedelta(hours=hours)
            result = await self.session.execute(
                select(ServerStats)
                .where(
                    and_(
                        ServerStats.server_id == server_id,
                        ServerStats.recorded_at >= since_date
                    )
                )
                .order_by(ServerStats.recorded_at.asc())
            )
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error getting server stats {server_id}: {e}")
            return []


class SystemSettingsRepository(BaseRepository):
    """Репозиторий для работы с системными настройками"""
    
    async def get_setting(self, key: str) -> Optional[str]:
        """Получить настройку по ключу"""
        try:
            result = await self.session.execute(
                select(SystemSettings.value).where(SystemSettings.key == key)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error getting setting {key}: {e}")
            return None
    
    async def set_setting(self, key: str, value: str, description: Optional[str] = None, category: str = "general") -> bool:
        """Установить настройку"""
        try:
            # Проверяем существование
            existing = await self.session.execute(
                select(SystemSettings).where(SystemSettings.key == key)
            )
            existing_setting = existing.scalar_one_or_none()
            
            if existing_setting:
                # Обновляем
                await self.session.execute(
                    update(SystemSettings)
                    .where(SystemSettings.key == key)
                    .values(value=value, updated_at=datetime.utcnow())
                )
            else:
                # Создаем новую
                setting = SystemSettings(
                    key=key,
                    value=value,
                    description=description,
                    category=category
                )
                self.session.add(setting)
            
            await self.session.flush()
            return True
        except Exception as e:
            logger.error(f"Error setting {key}: {e}")
            return False
    
    async def get_settings_by_category(self, category: str) -> List[SystemSettings]:
        """Получить настройки по категории"""
        try:
            result = await self.session.execute(
                select(SystemSettings).where(SystemSettings.category == category)
            )
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error getting settings by category {category}: {e}")
            return []


class RepositoryManager:
    """Менеджер всех репозиториев"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        
        # Инициализация всех репозиториев
        self.users = UserRepository(session)
        self.servers = ServerRepository(session)
        self.subscription_plans = SubscriptionPlanRepository(session)
        self.subscriptions = SubscriptionRepository(session)
        self.vpn_configs = VpnConfigRepository(session)
        self.payments = PaymentRepository(session)
        self.support_tickets = SupportTicketRepository(session)
        self.support_messages = SupportMessageRepository(session)
        self.user_activities = UserActivityRepository(session)
        self.server_stats = ServerStatsRepository(session)
        self.system_settings = SystemSettingsRepository(session)
    
    async def commit(self):
        """Зафиксировать все изменения"""
        await self.session.commit()
    
    async def rollback(self):
        """Откатить все изменения"""
        await self.session.rollback()
            logger.error(f"Error getting user by telegram_id {telegram_id}: {e}")
            return None
    
    async def get_by_id(self, user_id: int) -> Optional[User]:
        """Получить пользователя по ID"""
        try:
            result = await self.session.execute(
                select(User).where(User.id == user_id)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error getting user by id {user_id}: {e}")
            return None
    
    async def create(self, **kwargs) -> User:
        """Создать нового пользователя"""
        try:
            user = User(**kwargs)
            self.session.add(user)
            await self.session.flush()
            await self.session.refresh(user)
            return user
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            await self.session.rollback()
            raise
    
    async def update(self, user_id: int, **kwargs) -> bool:
        """Обновить пользователя"""
        try:
            kwargs['updated_at'] = datetime.utcnow()
            result = await self.session.execute(
                update(User).where(User.id == user_id).values(**kwargs)
            )
            return result.rowcount > 0
        except Exception as e:
            logger.error(f"Error updating user {user_id}: {e}")
            return False
    
    async def update_last_activity(self, telegram_id: int):
        """Обновить время последней активности"""
        try:
            await self.session.execute(
                update(User)
                .where(User.telegram_id == telegram_id)
                .values(last_activity=datetime.utcnow())
            )
        except Exception as e:
            logger.error(f"Error updating last activity for {telegram_id}: {e}")
    
    async def get_admins(self) -> List[User]:
        """Получить всех администраторов"""
        try:
            result = await self.session.execute(
                select(User).where(User.role == UserRole.ADMIN)
            )
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error getting admins: {e}")
            return []
    
    async def get_active_users_count(self) -> int:
        """Получить количество активных пользователей"""
        try:
            result = await self.session.execute(
                select(func.count(User.id)).where(
                    and_(User.is_active == True, User.is_banned == False)
                )
            )
            return result.scalar() or 0
        except Exception as e:
            logger.error(f"Error getting active users count: {e}")
            return 0
    
    async def get_users_by_country(self, country_code: str) -> List[User]:
        """Получить пользователей по коду страны"""
        try:
            result = await self.session.execute(
                select(User).where(User.country_code == country_code)
            )
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error getting users by country {country_code}: {e}")
            return []


class ServerRepository(BaseRepository):
    """Репозиторий для работы с серверами"""
    
    async def get_all_active(self) -> List[Server]:
        """Получить все активные серверы"""
        try:
            result = await self.session.execute(
                select(Server).where(
                    and_(Server.is_active == True, Server.is_maintenance == False)
                ).order_by(Server.country, Server.name)
            )
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error getting active servers: {e}")
            return []
    
    async def get_by_id(self, server_id: int) -> Optional[Server]:
        """Получить сервер по ID"""
        try:
            result = await self.session.execute(
                select(Server).where(Server.id == server_id)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error getting server by id {server_id}: {e}")
            return None
    
    async def get_by_protocol(self, protocol: VpnProtocol) -> List[Server]:
        """Получить серверы, поддерживающие протокол"""
        try:
            result = await self.session.execute(
                select(Server).where(
                    and_(
                        Server.is_active == True,
                        Server.supported_protocols.contains([protocol.value])
                    )
                )
            )
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error getting servers by protocol {protocol}: {e}")
            return []
    
    async def get_best_server(self, country_code: Optional[str] = None) -> Optional[Server]:
        """Получить лучший сервер (с наименьшей нагрузкой)"""
        try:
            query = select(Server).where(
                and_(Server.is_active == True, Server.is_maintenance == False)
            )
            
            if country_code:
                query = query.where(Server.country_code == country_code)
            
            # Сортируем по загрузке (current_users / max_users)
            query = query.order_by(
                (Server.current_users / Server.max_users).asc(),
                Server.cpu_usage.asc()
            )
            
            result = await self.session.execute(query)
            return result.scalars().first()
        except Exception as e:
            logger.error(f"Error getting best server: {e}")
            return None
    
    async def update_stats(self, server_id: int, **stats) -> bool:
        """Обновить статистику сервера"""
        try:
            stats['updated_at'] = datetime.utcnow()
            stats['last_check'] = datetime.utcnow()
            
            result = await self.session.execute(
                update(Server).where(Server.id == server_id).values(**stats)
            )
            return result.rowcount > 0
        except Exception as e:
            logger.error(f"Error updating server stats {server_id}: {e}")
            return False


class SubscriptionPlanRepository(BaseRepository):
    """Репозиторий для работы с тарифными планами"""
    
    async def get_all_active(self) -> List[SubscriptionPlan]:
        """Получить все активные тарифы"""
        try:
            result = await self.session.execute(
                select(SubscriptionPlan)
                .where(SubscriptionPlan.is_active == True)
                .order_by(SubscriptionPlan.sort_order, SubscriptionPlan.price)
            )
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error getting active plans: {e}")
            return []
    
    async def get_by_id(self, plan_id: int) -> Optional[SubscriptionPlan]:
        """Получить тариф по ID"""
        try:
            result = await self.session.execute(
                select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error getting plan by id {plan_id}: {e}")
            return None
    
    async def get_trial_plan(self) -> Optional[SubscriptionPlan]:
        """Получить пробный тариф"""
        try:
            result = await self.session.execute(
                select(SubscriptionPlan).where(
                    and_(
                        SubscriptionPlan.is_trial == True,
                        SubscriptionPlan.is_active == True
                    )
                )
            )
            return result.scalars().first()
        except Exception as e:
            logger.error(f"Error getting trial plan: {e}")
            return None


class SubscriptionRepository(BaseRepository):
    """Репозиторий для работы с подписками"""
    
    async def get_user_subscriptions(self, user_id: int) -> List[Subscription]:
        """Получить подписки пользователя"""
        try:
            result = await self.session.execute(
                select(Subscription)
                .where(Subscription.user_id == user_id)
                .options(
                    selectinload(Subscription.server),
                    selectinload(Subscription.plan),
                    selectinload(Subscription.vpn_configs)
                )
                .order_by(Subscription.created_at.desc())
            )
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error getting user subscriptions {user_id}: {e}")
            return []
    
    async def get_active_subscription(self, user_id: int) -> Optional[Subscription]:
        """Получить активную подписку пользователя"""
        try:
            result = await self.session.execute(
                select(Subscription)
                .where(
                    and_(
                        Subscription.user_id == user_id,
                        Subscription.status == SubscriptionStatus.ACTIVE,
                        Subscription.expires_at > datetime.utcnow()
                    )
                )
                .options(
                    selectinload(Subscription.server),
                    selectinload(Subscription.plan),
                    selectinload(Subscription.vpn_configs)
                )
            )
            return result.scalars().first()
        except Exception as e:
            logger.error(f"Error getting active subscription for user {user_id}: {e}")
            return None
    
    async def create(self, **kwargs) -> Subscription:
        """Создать подписку"""
        try:
            subscription = Subscription(**kwargs)
            self.session.add(subscription)
            await self.session.flush()
            await self.session.refresh(subscription)
            return subscription
        except Exception as e:
            logger.error(f"Error creating subscription: {e}")
            await self.session.rollback()
            raise
    
    async def update_status(self, subscription_id: int, status: SubscriptionStatus) -> bool:
        """Обновить статус подписки"""
        try:
            result = await self.session.execute(
                update(Subscription)
                .where(Subscription.id == subscription_id)
                .values(status=status, updated_at=datetime.utcnow())
            )
            return result.rowcount > 0
        except Exception as e:
            logger.error(f"Error updating subscription status {subscription_id}: {e}")
            return False
    
    async def get_expiring_subscriptions(self, hours: int = 24) -> List[Subscription]:
        """Получить подписки, истекающие через указанное количество часов"""
        try:
            expiry_time = datetime.utcnow() + timedelta(hours=hours)
            result = await self.session.execute(
                select(Subscription)
                .where(
                    and_(
                        Subscription.status == SubscriptionStatus.ACTIVE,
                        Subscription.expires_at <= expiry_time,
                        Subscription.expires_at > datetime.utcnow()
                    )
                )
                .options(selectinload(Subscription.user))
            )
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error getting expiring subscriptions: {e}")
            return []


class VpnConfigRepository(BaseRepository):
    """Репозиторий для работы с VPN конфигурациями"""
    
    async def get_by_subscription(self, subscription_id: int) -> List[VpnConfig]:
        """Получить конфигурации по подписке"""
        try:
            result = await self.session.execute(
                select(VpnConfig)
                .where(VpnConfig.subscription_id == subscription_id)
                .options(selectinload(VpnConfig.server))
            )
            return result.scalars().all()
        except Exception as e: