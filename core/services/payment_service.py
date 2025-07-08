"""
Сервис для управления платежами VPN Bot System
"""

import asyncio
import uuid
import hmac
import hashlib
import json
from decimal import Decimal
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from core.database.models import (
    Payment, PaymentStatus, PaymentMethod, User, 
    SubscriptionPlan, Subscription
)
from core.database.repositories import RepositoryManager
from core.services.user_service import UserService
from core.exceptions.custom_exceptions import (
    PaymentNotFoundError, PaymentFailedError, 
    InsufficientFundsError, ValidationError
)
from core.utils.crypto import crypto_manager, hash_config_data
from config.settings import settings


class PaymentMethod(enum.Enum):
    """Методы оплаты"""
    YOOKASSA = "yookassa"
    CRYPTOPAY = "cryptopay"
    CRYPTO_MANUAL = "crypto_manual"
    BALANCE = "balance"


class PaymentService:
    """Основной сервис для работы с платежами"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repos = RepositoryManager(session)
        self.user_service = UserService(session)
    
    async def create_payment(
        self,
        user_id: int,
        plan_id: int,
        server_id: Optional[int] = None,
        protocol: Optional[str] = None,
        payment_method: PaymentMethod = PaymentMethod.YOOKASSA,
        amount: Optional[Decimal] = None,
        currency: str = "RUB"
    ) -> Payment:
        """
        Создать новый платеж
        
        Args:
            user_id: ID пользователя
            plan_id: ID тарифного плана
            server_id: ID сервера (опционально)
            protocol: Протокол VPN (опционально)
            payment_method: Способ оплаты
            amount: Сумма (если не указана, берется из плана)
            currency: Валюта
            
        Returns:
            Payment: Созданный платеж
        """
        try:
            # Получаем план подписки
            plan = await self.repos.subscription_plans.get_by_id(plan_id)
            if not plan:
                raise ValidationError(f"Subscription plan {plan_id} not found")
            
            # Определяем сумму
            if amount is None:
                amount = Decimal(str(plan.price))
            
            # Создаем платеж
            payment_data = {
                "user_id": user_id,
                "subscription_plan_id": plan_id,
                "server_id": server_id,
                "payment_method": payment_method,
                "amount": amount,
                "currency": currency,
                "status": PaymentStatus.PENDING,
                "metadata": {
                    "protocol": protocol,
                    "plan_name": plan.name,
                    "created_via": "telegram_bot"
                }
            }
            
            payment = await self.repos.payments.create(**payment_data)
            
            # Логируем создание платежа
            await self.user_service.log_user_action(
                user_id=user_id,
                action="payment_created",
                details={
                    "payment_id": payment.id,
                    "amount": float(amount),
                    "currency": currency,
                    "method": payment_method.value,
                    "plan_id": plan_id
                }
            )
            
            await self.repos.commit()
            logger.info(f"Payment created: {payment.id} for user {user_id}")
            
            return payment
            
        except Exception as e:
            await self.repos.rollback()
            logger.error(f"Error creating payment: {e}")
            raise
    
    async def get_payment_url(self, payment_id: int) -> Optional[str]:
        """
        Получить URL для оплаты
        
        Args:
            payment_id: ID платежа
            
        Returns:
            Optional[str]: URL для оплаты
        """
        try:
            payment = await self.repos.payments.get_by_id(payment_id)
            if not payment:
                raise PaymentNotFoundError(f"Payment {payment_id} not found")
            
            if payment.payment_method == PaymentMethod.YOOKASSA:
                return await self._create_yookassa_payment(payment)
            elif payment.payment_method == PaymentMethod.CRYPTOPAY:
                return await self._create_cryptopay_payment(payment)
            else:
                logger.warning(f"Unsupported payment method: {payment.payment_method}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting payment URL: {e}")
            return None
    
    async def _create_yookassa_payment(self, payment: Payment) -> Optional[str]:
        """
        Создать платеж в ЮKassa
        
        Args:
            payment: Объект платежа
            
        Returns:
            Optional[str]: URL для оплаты
        """
        try:
            if not settings.YOOKASSA_ACCOUNT_ID or not settings.YOOKASSA_SECRET_KEY:
                logger.error("YooKassa credentials not configured")
                return None
            
            import yookassa
            from yookassa import Configuration, Payment as YooPayment
            
            # Настраиваем YooKassa
            Configuration.account_id = settings.YOOKASSA_ACCOUNT_ID
            Configuration.secret_key = settings.YOOKASSA_SECRET_KEY
            
            # Создаем платеж
            yoo_payment = YooPayment.create({
                "amount": {
                    "value": str(payment.amount),
                    "currency": payment.currency
                },
                "confirmation": {
                    "type": "redirect",
                    "return_url": f"{settings.WEBHOOK_DOMAIN}/payment/success/{payment.id}"
                },
                "capture": True,
                "description": f"Оплата подписки VPN - План {payment.metadata.get('plan_name', 'Unknown')}",
                "metadata": {
                    "payment_id": str(payment.id),
                    "user_id": str(payment.user_id),
                    "plan_id": str(payment.subscription_plan_id)
                }
            }, uuid.uuid4())
            
            # Сохраняем внешний ID платежа
            await self.repos.payments.update(
                payment.id,
                external_payment_id=yoo_payment.id,
                expires_at=datetime.utcnow() + timedelta(minutes=15)
            )
            await self.repos.commit()
            
            logger.info(f"YooKassa payment created: {yoo_payment.id}")
            return yoo_payment.confirmation.confirmation_url
            
        except Exception as e:
            logger.error(f"Error creating YooKassa payment: {e}")
            return None
    
    async def _create_cryptopay_payment(self, payment: Payment) -> Optional[str]:
        """
        Создать платеж в CryptoPay
        
        Args:
            payment: Объект платежа
            
        Returns:
            Optional[str]: URL для оплаты
        """
        try:
            # Здесь была бы интеграция с CryptoPay API
            # Пока возвращаем заглушку
            
            # Конвертируем RUB в USDT (примерная конвертация)
            usdt_amount = float(payment.amount) / 100  # 1 USD ≈ 100 RUB
            
            # Генерируем уникальный ID для CryptoPay
            cryptopay_id = f"cp_{payment.id}_{uuid.uuid4().hex[:8]}"
            
            # Сохраняем внешний ID
            await self.repos.payments.update(
                payment.id,
                external_payment_id=cryptopay_id,
                expires_at=datetime.utcnow() + timedelta(hours=1)
            )
            await self.repos.commit()
            
            # В реальной реализации здесь был бы вызов CryptoPay API
            cryptopay_url = f"https://t.me/CryptoBot?start=pay_{cryptopay_id}"
            
            logger.info(f"CryptoPay payment created: {cryptopay_id}")
            return cryptopay_url
            
        except Exception as e:
            logger.error(f"Error creating CryptoPay payment: {e}")
            return None
    
    async def create_cryptopay_invoice(
        self,
        payment_id: int,
        amount: float,
        currency: str = "USDT",
        description: str = "VPN Subscription"
    ) -> Optional[Dict[str, Any]]:
        """
        Создать инвойс в CryptoPay
        
        Args:
            payment_id: ID платежа
            amount: Сумма
            currency: Валюта
            description: Описание
            
        Returns:
            Optional[Dict[str, Any]]: Данные инвойса
        """
        try:
            # В реальной реализации здесь был бы вызов CryptoPay API
            invoice_id = f"inv_{payment_id}_{uuid.uuid4().hex[:8]}"
            
            return {
                "invoice_id": invoice_id,
                "amount": amount,
                "currency": currency,
                "description": description,
                "pay_url": f"https://t.me/CryptoBot?start=pay_{invoice_id}",
                "mini_app_pay_url": f"https://t.me/CryptoBot/app?startapp=pay_{invoice_id}",
                "status": "active",
                "created_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error creating CryptoPay invoice: {e}")
            return None
    
    async def check_payment_status(self, payment_id: int) -> Payment:
        """
        Проверить статус платежа
        
        Args:
            payment_id: ID платежа
            
        Returns:
            Payment: Обновленный платеж
        """
        try:
            payment = await self.repos.payments.get_by_id(payment_id)
            if not payment:
                raise PaymentNotFoundError(f"Payment {payment_id} not found")
            
            # Если платеж уже завершен, возвращаем как есть
            if payment.status in [PaymentStatus.COMPLETED, PaymentStatus.FAILED, PaymentStatus.CANCELLED]:
                return payment
            
            # Проверяем статус в зависимости от метода оплаты
            if payment.payment_method == PaymentMethod.YOOKASSA:
                updated_status = await self._check_yookassa_status(payment)
            elif payment.payment_method == PaymentMethod.CRYPTOPAY:
                updated_status = await self._check_cryptopay_status(payment)
            else:
                updated_status = payment.status
            
            # Обновляем статус если изменился
            if updated_status != payment.status:
                await self.update_payment_status(payment_id, updated_status)
                payment.status = updated_status
            
            return payment
            
        except Exception as e:
            logger.error(f"Error checking payment status {payment_id}: {e}")
            raise
    
    async def _check_yookassa_status(self, payment: Payment) -> PaymentStatus:
        """
        Проверить статус в YooKassa
        
        Args:
            payment: Объект платежа
            
        Returns:
            PaymentStatus: Статус платежа
        """
        try:
            if not payment.external_payment_id:
                return payment.status
            
            import yookassa
            from yookassa import Configuration, Payment as YooPayment
            
            Configuration.account_id = settings.YOOKASSA_ACCOUNT_ID
            Configuration.secret_key = settings.YOOKASSA_SECRET_KEY
            
            yoo_payment = YooPayment.find_one(payment.external_payment_id)
            
            if yoo_payment.status == "succeeded":
                return PaymentStatus.COMPLETED
            elif yoo_payment.status == "canceled":
                return PaymentStatus.FAILED
            else:
                return PaymentStatus.PENDING
                
        except Exception as e:
            logger.error(f"Error checking YooKassa status: {e}")
            return payment.status
    
    async def _check_cryptopay_status(self, payment: Payment) -> PaymentStatus:
        """
        Проверить статус в CryptoPay
        
        Args:
            payment: Объект платежа
            
        Returns:
            PaymentStatus: Статус платежа
        """
        try:
            # В реальной реализации здесь был бы вызов CryptoPay API
            # Пока возвращаем текущий статус
            return payment.status
            
        except Exception as e:
            logger.error(f"Error checking CryptoPay status: {e}")
            return payment.status
    
    async def update_payment_status(
        self,
        payment_id: int,
        status: PaymentStatus,
        external_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Обновить статус платежа
        
        Args:
            payment_id: ID платежа
            status: Новый статус
            external_data: Дополнительные данные от платежной системы
            
        Returns:
            bool: Успешность обновления
        """
        try:
            update_data = {"status": status}
            
            if status == PaymentStatus.COMPLETED:
                update_data["paid_at"] = datetime.utcnow()
                
                # Активируем подписку при успешной оплате
                await self._activate_subscription_after_payment(payment_id)
            
            if external_data:
                payment = await self.repos.payments.get_by_id(payment_id)
                if payment:
                    metadata = payment.metadata or {}
                    metadata.update(external_data)
                    update_data["metadata"] = metadata
            
            success = await self.repos.payments.update_status(payment_id, status, **update_data)
            
            if success:
                # Логируем изменение статуса
                payment = await self.repos.payments.get_by_id(payment_id)
                if payment:
                    await self.user_service.log_user_action(
                        user_id=payment.user_id,
                        action="payment_status_updated",
                        details={
                            "payment_id": payment_id,
                            "new_status": status.value,
                            "external_data": external_data
                        }
                    )
                
                await self.repos.commit()
                logger.info(f"Payment {payment_id} status updated to {status.value}")
            
            return success
            
        except Exception as e:
            await self.repos.rollback()
            logger.error(f"Error updating payment status {payment_id}: {e}")
            return False
    
    async def _activate_subscription_after_payment(self, payment_id: int):
        """
        Активировать подписку после успешной оплаты
        
        Args:
            payment_id: ID платежа
        """
        try:
            payment = await self.repos.payments.get_by_id(payment_id)
            if not payment:
                return
            
            # Импортируем здесь чтобы избежать циклического импорта
            from core.services.subscription_service import SubscriptionService
            
            subscription_service = SubscriptionService(self.session)
            
            # Создаем подписку
            subscription = await subscription_service.create_subscription(
                user_id=payment.user_id,
                plan_id=payment.subscription_plan_id,
                server_id=payment.server_id,
                protocol=payment.metadata.get("protocol"),
                payment_id=payment.id
            )
            
            # Активируем подписку
            await subscription_service.activate_subscription(subscription.id)
            
            logger.info(f"Subscription activated after payment {payment_id}")
            
        except Exception as e:
            logger.error(f"Error activating subscription after payment {payment_id}: {e}")
    
    async def cancel_payment(self, payment_id: int) -> bool:
        """
        Отменить платеж
        
        Args:
            payment_id: ID платежа
            
        Returns:
            bool: Успешность отмены
        """
        try:
            payment = await self.repos.payments.get_by_id(payment_id)
            if not payment:
                return False
            
            # Можно отменить только ожидающие платежи
            if payment.status != PaymentStatus.PENDING:
                return False
            
            success = await self.update_payment_status(payment_id, PaymentStatus.CANCELLED)
            
            if success:
                await self.user_service.log_user_action(
                    user_id=payment.user_id,
                    action="payment_cancelled",
                    details={"payment_id": payment_id}
                )
            
            return success
            
        except Exception as e:
            logger.error(f"Error cancelling payment {payment_id}: {e}")
            return False
    
    async def refund_payment(
        self,
        payment_id: int,
        amount: Optional[Decimal] = None,
        reason: str = "User request"
    ) -> bool:
        """
        Вернуть деньги за платеж
        
        Args:
            payment_id: ID платежа
            amount: Сумма возврата (если не указана, возвращается вся сумма)
            reason: Причина возврата
            
        Returns:
            bool: Успешность возврата
        """
        try:
            payment = await self.repos.payments.get_by_id(payment_id)
            if not payment:
                return False
            
            # Можно вернуть только завершенные платежи
            if payment.status != PaymentStatus.COMPLETED:
                return False
            
            if amount is None:
                amount = payment.amount
            
            # В реальной реализации здесь был бы вызов API платежной системы
            success = True  # Заглушка
            
            if success:
                await self.update_payment_status(
                    payment_id,
                    PaymentStatus.REFUNDED,
                    {"refund_amount": float(amount), "refund_reason": reason}
                )
                
                await self.user_service.log_user_action(
                    user_id=payment.user_id,
                    action="payment_refunded",
                    details={
                        "payment_id": payment_id,
                        "refund_amount": float(amount),
                        "reason": reason
                    }
                )
            
            return success
            
        except Exception as e:
            logger.error(f"Error refunding payment {payment_id}: {e}")
            return False
    
    async def check_cryptopay_status(self, payment_id: int) -> Dict[str, Any]:
        """
        Проверить статус CryptoPay платежа
        
        Args:
            payment_id: ID платежа
            
        Returns:
            Dict[str, Any]: Статус платежа
        """
        try:
            payment = await self.repos.payments.get_by_id(payment_id)
            if not payment:
                return {"status": "not_found"}
            
            # В реальной реализации здесь был бы вызов CryptoPay API
            return {
                "status": "active",  # active, paid, expired
                "invoice_id": payment.external_payment_id,
                "amount": float(payment.amount),
                "currency": payment.currency
            }
            
        except Exception as e:
            logger.error(f"Error checking CryptoPay status: {e}")
            return {"status": "error", "error": str(e)}
    
    async def check_crypto_transaction(self, payment_id: int) -> Dict[str, Any]:
        """
        Проверить криптовалютную транзакцию
        
        Args:
            payment_id: ID платежа
            
        Returns:
            Dict[str, Any]: Статус транзакции
        """
        try:
            payment = await self.repos.payments.get_by_id(payment_id)
            if not payment:
                return {"status": "not_found"}
            
            # В реальной реализации здесь была бы проверка в блокчейне
            return {
                "status": "pending",  # pending, confirmed, failed
                "confirmations": 0,
                "required_confirmations": 3,
                "transaction_hash": None
            }
            
        except Exception as e:
            logger.error(f"Error checking crypto transaction: {e}")
            return {"status": "error", "error": str(e)}
    
    async def complete_payment(self, payment_id: int) -> Payment:
        """
        Завершить платеж
        
        Args:
            payment_id: ID платежа
            
        Returns:
            Payment: Завершенный платеж
        """
        try:
            await self.update_payment_status(payment_id, PaymentStatus.COMPLETED)
            payment = await self.repos.payments.get_by_id(payment_id)
            return payment
            
        except Exception as e:
            logger.error(f"Error completing payment {payment_id}: {e}")
            raise
    
    async def expire_payment(self, payment_id: int) -> bool:
        """
        Пометить платеж как истекший
        
        Args:
            payment_id: ID платежа
            
        Returns:
            bool: Успешность операции
        """
        try:
            return await self.update_payment_status(payment_id, PaymentStatus.FAILED)
            
        except Exception as e:
            logger.error(f"Error expiring payment {payment_id}: {e}")
            return False
    
    async def get_user_payments(self, user_id: int) -> List[Payment]:
        """
        Получить платежи пользователя
        
        Args:
            user_id: ID пользователя
            
        Returns:
            List[Payment]: Список платежей
        """
        try:
            return await self.repos.payments.get_user_payments(user_id)
        except Exception as e:
            logger.error(f"Error getting user payments {user_id}: {e}")
            return []
    
    async def get_payment_statistics(self, days: int = 30) -> Dict[str, Any]:
        """
        Получить статистику платежей
        
        Args:
            days: Количество дней для анализа
            
        Returns:
            Dict[str, Any]: Статистика платежей
        """
        try:
            # В реальной реализации здесь были бы сложные запросы к БД
            return {
                "period_days": days,
                "total_payments": 0,
                "successful_payments": 0,
                "failed_payments": 0,
                "total_amount": 0.0,
                "average_amount": 0.0,
                "payment_methods": {
                    "yookassa": {"count": 0, "amount": 0.0},
                    "cryptopay": {"count": 0, "amount": 0.0}
                },
                "conversion_rate": 0.0
            }
            
        except Exception as e:
            logger.error(f"Error getting payment statistics: {e}")
            return {}


class PaymentWebhookService:
    """Сервис для обработки webhook'ов от платежных систем"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.payment_service = PaymentService(session)
    
    async def handle_yookassa_webhook(
        self,
        webhook_data: Dict[str, Any],
        signature: Optional[str] = None
    ) -> bool:
        """
        Обработать webhook от YooKassa
        
        Args:
            webhook_data: Данные webhook'а
            signature: Подпись webhook'а
            
        Returns:
            bool: Успешность обработки
        """
        try:
            # Проверяем подпись webhook'а
            if signature and not self._verify_yookassa_signature(webhook_data, signature):
                logger.warning("Invalid YooKassa webhook signature")
                return False
            
            event_type = webhook_data.get("event")
            payment_data = webhook_data.get("object", {})
            
            if event_type == "payment.succeeded":
                return await self._handle_yookassa_success(payment_data)
            elif event_type == "payment.canceled":
                return await self._handle_yookassa_failure(payment_data)
            else:
                logger.info(f"Unhandled YooKassa event: {event_type}")
                return True
                
        except Exception as e:
            logger.error(f"Error handling YooKassa webhook: {e}")
            return False
    
    def _verify_yookassa_signature(
        self,
        webhook_data: Dict[str, Any],
        signature: str
    ) -> bool:
        """
        Проверить подпись YooKassa webhook'а
        
        Args:
            webhook_data: Данные webhook'а
            signature: Подпись
            
        Returns:
            bool: Валидность подписи
        """
        try:
            # В реальной реализации здесь была бы проверка подписи
            return True  # Заглушка
        except Exception as e:
            logger.error(f"Error verifying YooKassa signature: {e}")
            return False
    
    async def _handle_yookassa_success(self, payment_data: Dict[str, Any]) -> bool:
        """
        Обработать успешный платеж YooKassa
        
        Args:
            payment_data: Данные платежа
            
        Returns:
            bool: Успешность обработки
        """
        try:
            external_id = payment_data.get("id")
            if not external_id:
                return False
            
            # Найти платеж по внешнему ID
            payment = await self.payment_service.repos.payments.get_by_external_id(external_id)
            if not payment:
                logger.warning(f"Payment not found for external_id: {external_id}")
                return False
            
            # Обновить статус
            await self.payment_service.update_payment_status(
                payment.id,
                PaymentStatus.COMPLETED,
                {"yookassa_data": payment_data}
            )
            
            logger.info(f"YooKassa payment {external_id} processed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error handling YooKassa success: {e}")
            return False
    
    async def _handle_yookassa_failure(self, payment_data: Dict[str, Any]) -> bool:
        """
        Обработать неуспешный платеж YooKassa
        
        Args:
            payment_data: Данные платежа
            
        Returns:
            bool: Успешность обработки
        """
        try:
            external_id = payment_data.get("id")
            if not external_id:
                return False
            
            payment = await self.payment_service.repos.payments.get_by_external_id(external_id)
            if not payment:
                return False
            
            await self.payment_service.update_payment_status(
                payment.id,
                PaymentStatus.FAILED,
                {"yookassa_data": payment_data}
            )
            
            logger.info(f"YooKassa payment {external_id} marked as failed")
            return True
            
        except Exception as e:
            logger.error(f"Error handling YooKassa failure: {e}")
            return False
    
    async def handle_cryptopay_webhook(
        self,
        webhook_data: Dict[str, Any]
    ) -> bool:
        """
        Обработать webhook от CryptoPay
        
        Args:
            webhook_data: Данные webhook'а
            
        Returns:
            bool: Успешность обработки
        """
        try:
            # В реальной реализации здесь была бы обработка CryptoPay webhook'ов
            logger.info("CryptoPay webhook received")
            return True
            
        except Exception as e:
            logger.error(f"Error handling CryptoPay webhook: {e}")
            return False


class PaymentValidationService:
    """Сервис валидации платежей"""
    
    @staticmethod
    def validate_payment_data(payment_data: Dict[str, Any]) -> List[str]:
        """
        Валидировать данные платежа
        
        Args:
            payment_data: Данные платежа
            
        Returns:
            List[str]: Список ошибок валидации
        """
        errors = []
        
        # Проверяем обязательные поля
        required_fields = ["user_id", "plan_id", "amount", "currency"]
        for field in required_fields:
            if field not in payment_data:
                errors.append(f"Missing required field: {field}")
        
        # Проверяем сумму
        if "amount" in payment_data:
            try:
                amount = Decimal(str(payment_data["amount"]))
                if amount <= 0:
                    errors.append("Amount must be positive")
            except (ValueError, TypeError):
                errors.append("Invalid amount format")
        
        # Проверяем валюту
        if "currency" in payment_data:
            valid_currencies = ["RUB", "USD", "EUR", "BTC", "ETH", "USDT"]
            if payment_data["currency"] not in valid_currencies:
                errors.append(f"Unsupported currency: {payment_data['currency']}")
        
        return errors


# Утилиты для работы с платежами

async def create_payment_simple(
    session: AsyncSession,
    user_id: int,
    plan_id: int,
    payment_method: str = "yookassa"
) -> Optional[Payment]:
    """
    Простое создание платежа
    
    Args:
        session: Сессия базы данных
        user_id: ID пользователя
        plan_id: ID плана
        payment_method: Метод оплаты
        
    Returns:
        Optional[Payment]: Созданный платеж
    """
    try:
        payment_service = PaymentService(session)
        method_enum = PaymentMethod(payment_method)
        
        return await payment_service.create_payment(
            user_id=user_id,
            plan_id=plan_id,
            payment_method=method_enum
        )
    except Exception as e:
        logger.error(f"Error creating simple payment: {e}")
        return None


async def process_successful_payment(
    session: AsyncSession,
    external_payment_id: str,
    external_data: Optional[Dict[str, Any]] = None
) -> bool:
    """
    Обработать успешный платеж по внешнему ID
    
    Args:
        session: Сессия базы данных
        external_payment_id: Внешний ID платежа
        external_data: Дополнительные данные
        
    Returns:
        bool: Успешность обработки
    """
    try:
        payment_service = PaymentService(session)
        repos = RepositoryManager(session)
        
        # Найти платеж
        payment = await repos.payments.get_by_external_id(external_payment_id)
        if not payment:
            logger.warning(f"Payment not found: {external_payment_id}")
            return False
        
        # Обновить статус
        return await payment_service.update_payment_status(
            payment.id,
            PaymentStatus.COMPLETED,
            external_data
        )
        
    except Exception as e:
        logger.error(f"Error processing successful payment: {e}")
        return False


class PaymentSecurityService:
    """Сервис безопасности платежей"""
    
    def __init__(self):
        self.max_attempts_per_hour = 5
        self.max_amount_per_day = Decimal("10000.00")
    
    async def check_payment_limits(
        self,
        session: AsyncSession,
        user_id: int,
        amount: Decimal
    ) -> Tuple[bool, Optional[str]]:
        """
        Проверить лимиты на платежи
        
        Args:
            session: Сессия базы данных
            user_id: ID пользователя
            amount: Сумма платежа
            
        Returns:
            Tuple[bool, Optional[str]]: (Разрешен ли платеж, Причина отказа)
        """
        try:
            repos = RepositoryManager(session)
            
            # Проверяем количество попыток за час
            hour_ago = datetime.utcnow() - timedelta(hours=1)
            recent_payments = await repos.payments.get_user_payments_since(user_id, hour_ago)
            
            if len(recent_payments) >= self.max_attempts_per_hour:
                return False, "Превышен лимит попыток оплаты в час"
            
            # Проверяем сумму за день
            day_ago = datetime.utcnow() - timedelta(days=1)
            daily_payments = await repos.payments.get_user_payments_since(user_id, day_ago)
            daily_total = sum(p.amount for p in daily_payments if p.status == PaymentStatus.COMPLETED)
            
            if daily_total + amount > self.max_amount_per_day:
                return False, "Превышен дневной лимит платежей"
            
            return True, None
            
        except Exception as e:
            logger.error(f"Error checking payment limits: {e}")
            return False, "Ошибка проверки лимитов"
    
    async def detect_suspicious_activity(
        self,
        session: AsyncSession,
        user_id: int,
        payment_data: Dict[str, Any]
    ) -> bool:
        """
        Обнаружить подозрительную активность
        
        Args:
            session: Сессия базы данных
            user_id: ID пользователя
            payment_data: Данные платежа
            
        Returns:
            bool: Обнаружена ли подозрительная активность
        """
        try:
            repos = RepositoryManager(session)
            
            # Проверяем частые платежи
            hour_ago = datetime.utcnow() - timedelta(hours=1)
            recent_payments = await repos.payments.get_user_payments_since(user_id, hour_ago)
            
            if len(recent_payments) > 3:
                logger.warning(f"Suspicious activity: too many payments from user {user_id}")
                return True
            
            # Проверяем необычно большие суммы
            amount = Decimal(str(payment_data.get("amount", 0)))
            if amount > Decimal("5000.00"):
                logger.warning(f"Suspicious activity: large amount {amount} from user {user_id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error detecting suspicious activity: {e}")
            return False


class PaymentNotificationService:
    """Сервис уведомлений о платежах"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_service = UserService(session)
    
    async def notify_payment_success(
        self,
        payment_id: int
    ):
        """
        Уведомить об успешном платеже
        
        Args:
            payment_id: ID платежа
        """
        try:
            repos = RepositoryManager(self.session)
            payment = await repos.payments.get_by_id(payment_id)
            
            if payment:
                await self.user_service.log_user_action(
                    user_id=payment.user_id,
                    action="payment_success_notification",
                    details={
                        "payment_id": payment_id,
                        "amount": float(payment.amount),
                        "currency": payment.currency
                    }
                )
                
                logger.info(f"Payment success notification sent for payment {payment_id}")
                
        except Exception as e:
            logger.error(f"Error sending payment success notification: {e}")
    
    async def notify_payment_failure(
        self,
        payment_id: int,
        reason: Optional[str] = None
    ):
        """
        Уведомить о неуспешном платеже
        
        Args:
            payment_id: ID платежа
            reason: Причина неудачи
        """
        try:
            repos = RepositoryManager(self.session)
            payment = await repos.payments.get_by_id(payment_id)
            
            if payment:
                await self.user_service.log_user_action(
                    user_id=payment.user_id,
                    action="payment_failure_notification",
                    details={
                        "payment_id": payment_id,
                        "reason": reason,
                        "amount": float(payment.amount)
                    }
                )
                
                logger.info(f"Payment failure notification sent for payment {payment_id}")
                
        except Exception as e:
            logger.error(f"Error sending payment failure notification: {e}")


class PaymentAnalyticsService:
    """Сервис аналитики платежей"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repos = RepositoryManager(session)
    
    async def get_revenue_statistics(self, days: int = 30) -> Dict[str, Any]:
        """
        Получить статистику доходов
        
        Args:
            days: Количество дней для анализа
            
        Returns:
            Dict[str, Any]: Статистика доходов
        """
        try:
            # В реальной реализации здесь были бы сложные запросы к БД
            return {
                "period_days": days,
                "total_revenue": 0.0,
                "revenue_by_currency": {
                    "RUB": 0.0,
                    "USD": 0.0,
                    "USDT": 0.0
                },
                "revenue_by_method": {
                    "yookassa": 0.0,
                    "cryptopay": 0.0
                },
                "average_payment": 0.0,
                "payment_count": 0,
                "conversion_rate": 0.0,
                "daily_breakdown": {}
            }
            
        except Exception as e:
            logger.error(f"Error getting revenue statistics: {e}")
            return {}
    
    async def get_payment_method_stats(self) -> Dict[str, Any]:
        """
        Получить статистику по методам оплаты
        
        Returns:
            Dict[str, Any]: Статистика методов оплаты
        """
        try:
            return {
                "yookassa": {
                    "total_payments": 0,
                    "successful_payments": 0,
                    "success_rate": 0.0,
                    "total_amount": 0.0,
                    "average_amount": 0.0
                },
                "cryptopay": {
                    "total_payments": 0,
                    "successful_payments": 0,
                    "success_rate": 0.0,
                    "total_amount": 0.0,
                    "average_amount": 0.0
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting payment method statistics: {e}")
            return {}
    
    async def get_user_payment_behavior(self, user_id: int) -> Dict[str, Any]:
        """
        Получить поведенческую статистику пользователя
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Dict[str, Any]: Поведенческая статистика
        """
        try:
            payments = await self.repos.payments.get_user_payments(user_id)
            
            if not payments:
                return {}
            
            successful_payments = [p for p in payments if p.status == PaymentStatus.COMPLETED]
            
            return {
                "total_payments": len(payments),
                "successful_payments": len(successful_payments),
                "success_rate": len(successful_payments) / len(payments) if payments else 0,
                "total_spent": sum(p.amount for p in successful_payments),
                "average_payment": sum(p.amount for p in successful_payments) / len(successful_payments) if successful_payments else 0,
                "preferred_method": self._get_preferred_payment_method(payments),
                "first_payment": payments[0].created_at.isoformat() if payments else None,
                "last_payment": payments[-1].created_at.isoformat() if payments else None,
                "payment_frequency": self._calculate_payment_frequency(successful_payments)
            }
            
        except Exception as e:
            logger.error(f"Error getting user payment behavior: {e}")
            return {}
    
    def _get_preferred_payment_method(self, payments: List[Payment]) -> Optional[str]:
        """Определить предпочитаемый метод оплаты"""
        if not payments:
            return None
        
        method_counts = {}
        for payment in payments:
            method = payment.payment_method.value
            method_counts[method] = method_counts.get(method, 0) + 1
        
        return max(method_counts, key=method_counts.get)
    
    def _calculate_payment_frequency(self, payments: List[Payment]) -> float:
        """Рассчитать частоту платежей (дней между платежами)"""
        if len(payments) < 2:
            return 0.0
        
        payments = sorted(payments, key=lambda p: p.created_at)
        intervals = []
        
        for i in range(1, len(payments)):
            interval = (payments[i].created_at - payments[i-1].created_at).days
            intervals.append(interval)
        
        return sum(intervals) / len(intervals) if intervals else 0.0


# Константы для платежной системы
class PaymentConstants:
    """Константы для платежной системы"""
    
    # Лимиты
    MIN_PAYMENT_AMOUNT = Decimal("1.00")
    MAX_PAYMENT_AMOUNT = Decimal("50000.00")
    MAX_PAYMENTS_PER_HOUR = 5
    MAX_DAILY_AMOUNT = Decimal("10000.00")
    
    # Таймауты
    PAYMENT_TIMEOUT_MINUTES = 15
    CRYPTOPAY_TIMEOUT_HOURS = 1
    
    # Валюты
    SUPPORTED_CURRENCIES = ["RUB", "USD", "EUR", "BTC", "ETH", "USDT"]
    DEFAULT_CURRENCY = "RUB"
    
    # Конвертация (примерная)
    CURRENCY_RATES = {
        "USD_TO_RUB": 100.0,
        "EUR_TO_RUB": 110.0,
        "USDT_TO_RUB": 100.0
    }


def get_payment_service(session: AsyncSession) -> PaymentService:
    """
    Получить экземпляр PaymentService
    
    Args:
        session: Сессия базы данных
        
    Returns:
        PaymentService: Сервис платежей
    """
    return PaymentService(session)


def get_webhook_service(session: AsyncSession) -> PaymentWebhookService:
    """
    Получить экземпляр PaymentWebhookService
    
    Args:
        session: Сессия базы данных
        
    Returns:
        PaymentWebhookService: Сервис webhook'ов
    """
    return PaymentWebhookService(session)


async def convert_currency(
    amount: Decimal,
    from_currency: str,
    to_currency: str
) -> Decimal:
    """
    Конвертировать валюту
    
    Args:
        amount: Сумма
        from_currency: Исходная валюта
        to_currency: Целевая валюта
        
    Returns:
        Decimal: Конвертированная сумма
    """
    if from_currency == to_currency:
        return amount
    
    # Простая конвертация (в реальности использовался бы внешний API)
    rate_key = f"{from_currency}_TO_{to_currency}"
    rate = PaymentConstants.CURRENCY_RATES.get(rate_key, 1.0)
    
    return amount * Decimal(str(rate))


class PaymentError(Exception):
    """Базовое исключение для платежной системы"""
    pass


class PaymentLimitExceededError(PaymentError):
    """Превышен лимит платежей"""
    pass


class PaymentMethodNotSupportedError(PaymentError):
    """Метод оплаты не поддерживается"""
    pass


class PaymentExpiredError(PaymentError):
    """Платеж истек"""
    pass