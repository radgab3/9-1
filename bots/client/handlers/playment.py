"""
Обработчик платежей для клиентского бота
"""

import asyncio
from decimal import Decimal
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from loguru import logger

from bots.client.states.client_states import PaymentStates
from bots.client.keyboards.inline import (
    get_payment_methods_keyboard, get_payment_status_keyboard,
    get_back_button, get_payment_confirmation_keyboard
)
from core.services.payment_service import PaymentService
from core.services.subscription_service import SubscriptionService
from core.services.user_service import UserService
from core.database.repositories import RepositoryManager
from core.database.models import PaymentStatus, PaymentMethod
from core.utils.helpers import format_bytes, mask_sensitive_data
from config.settings import settings

router = Router()


@router.callback_query(F.data.startswith("pay_card_"))
async def initiate_card_payment(callback: CallbackQuery, state: FSMContext, session, **kwargs):
    """Инициировать оплату банковской картой через ЮKassa"""
    try:
        await callback.answer()
        
        plan_id = int(callback.data.split("_")[2])
        
        # Получаем данные заказа из состояния
        data = await state.get_data()
        user_service = UserService(session)
        payment_service = PaymentService(session)
        
        user = await user_service.get_user_by_telegram_id(callback.from_user.id)
        
        # Получаем план
        repos = RepositoryManager(session)
        plan = await repos.subscription_plans.get_by_id(plan_id)
        
        if not plan or not plan.is_active:
            await callback.answer("❌ Тариф недоступен", show_alert=True)
            return
        
        # Создаем платеж
        try:
            payment = await payment_service.create_payment(
                user_id=user.id,
                plan_id=plan_id,
                server_id=data.get("selected_server_id"),
                protocol=data.get("selected_protocol"),
                payment_method=PaymentMethod.YOOKASSA,
                amount=plan.price,
                currency=plan.currency
            )
            
            # Получаем ссылку на оплату от ЮKassa
            payment_url = await payment_service.get_payment_url(payment.id)
            
            if not payment_url:
                await callback.message.edit_text(
                    "❌ Ошибка при создании платежа. Обратитесь в поддержку.",
                    reply_markup=get_back_button("subscriptions")
                )
                return
            
            # Формируем сообщение об оплате
            text = f"💳 <b>Оплата банковской картой</b>\n\n"
            text += f"📦 План: {plan.name}\n"
            text += f"💰 Сумма: {plan.price} {plan.currency}\n"
            text += f"📅 Период: {plan.duration_days} дней\n\n"
            text += f"🔗 <b>Для оплаты перейдите по ссылке:</b>\n"
            text += f"<a href='{payment_url}'>💳 Оплатить {plan.price} {plan.currency}</a>\n\n"
            text += f"⏰ Время на оплату: 15 минут\n"
            text += f"💡 После оплаты подписка активируется автоматически"
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💳 Открыть страницу оплаты", url=payment_url)],
                [
                    InlineKeyboardButton(text="🔄 Проверить статус", callback_data=f"check_payment_{payment.id}"),
                    InlineKeyboardButton(text="❌ Отменить", callback_data=f"cancel_payment_{payment.id}")
                ],
                [InlineKeyboardButton(text="💬 Поддержка", callback_data="support")]
            ])
            
            await callback.message.edit_text(text=text, reply_markup=keyboard)
            
            # Сохраняем ID платежа в состояние
            await state.update_data(payment_id=payment.id)
            await state.set_state(PaymentStates.waiting_payment)
            
            # Логируем создание платежа
            await user_service.log_user_action(
                user_id=user.id,
                action="payment_initiated",
                details={
                    "payment_id": payment.id,
                    "plan_id": plan_id,
                    "amount": float(plan.price),
                    "currency": plan.currency,
                    "method": "yookassa"
                }
            )
            
            # Запускаем проверку статуса платежа в фоне
            asyncio.create_task(monitor_payment_status(payment.id, session))
            
        except Exception as e:
            logger.error(f"Error creating YooKassa payment: {e}")
            await callback.message.edit_text(
                "❌ Ошибка при создании платежа. Попробуйте позже.",
                reply_markup=get_back_button("subscriptions")
            )
        
    except Exception as e:
        logger.error(f"Error initiating card payment: {e}")
        await callback.answer("❌ Ошибка при создании платежа", show_alert=True)


@router.callback_query(F.data.startswith("pay_crypto_"))
async def initiate_crypto_payment(callback: CallbackQuery, state: FSMContext, session, **kwargs):
    """Инициировать CryptoPay платеж"""
    try:
        await callback.answer()
        
        plan_id = int(callback.data.split("_")[2])
        
        # Создаем CryptoPay платеж
        await create_cryptopay_payment(callback, state, session, plan_id)
        
    except Exception as e:
        logger.error(f"Error initiating CryptoPay payment: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


async def create_cryptopay_payment(callback: CallbackQuery, state: FSMContext, session, plan_id: int):
    """Создать CryptoPay платеж"""
    try:
        # Получаем данные
        data = await state.get_data()
        user_service = UserService(session)
        payment_service = PaymentService(session)
        
        user = await user_service.get_user_by_telegram_id(callback.from_user.id)
        
        repos = RepositoryManager(session)
        plan = await repos.subscription_plans.get_by_id(plan_id)
        
        if not plan:
            await callback.answer("❌ Тариф не найден", show_alert=True)
            return
        
        try:
            # Конвертируем RUB в USDT (примерно 1 USD = 100 RUB)
            usdt_amount = round(plan.price / 100, 2)
            
            # Создаем платеж в базе данных
            payment = await payment_service.create_payment(
                user_id=user.id,
                plan_id=plan_id,
                server_id=data.get("selected_server_id"),
                protocol=data.get("selected_protocol"),
                payment_method=PaymentMethod.CRYPTOPAY,
                amount=usdt_amount,
                currency="USDT"
            )
            
            # Создаем CryptoPay инвойс
            cryptopay_invoice = await payment_service.create_cryptopay_invoice(
                payment_id=payment.id,
                amount=usdt_amount,
                currency="USDT",
                description=f"VPN подписка: {plan.name}"
            )
            
            if not cryptopay_invoice:
                await callback.message.edit_text(
                    "❌ Ошибка при создании CryptoPay платежа. Обратитесь в поддержку.",
                    reply_markup=get_back_button("subscriptions")
                )
                return
            
            # Формируем сообщение с CryptoPay
            text = f"💎 <b>Оплата через CryptoPay</b>\n\n"
            text += f"📦 План: {plan.name}\n"
            text += f"💰 Сумма: {usdt_amount} USDT\n"
            text += f"💱 Курс: {plan.price} RUB ≈ {usdt_amount} USDT\n\n"
            text += f"🚀 <b>CryptoPay преимущества:</b>\n"
            text += f"• Оплата прямо в Telegram\n"
            text += f"• Поддержка 15+ криптовалют\n"
            text += f"• Мгновенное зачисление\n"
            text += f"• Низкие комиссии\n\n"
            text += f"⏰ Время на оплату: 1 час\n"
            text += f"💡 После оплаты подписка активируется автоматически"
            
            # Кнопка для оплаты через CryptoPay
            pay_url = cryptopay_invoice.get("pay_url")
            mini_app_url = cryptopay_invoice.get("mini_app_pay_url")
            
            keyboard_buttons = []
            
            # Основная кнопка оплаты
            if mini_app_url:
                keyboard_buttons.append([
                    InlineKeyboardButton(
                        text="💎 Оплатить через CryptoPay", 
                        url=mini_app_url
                    )
                ])
            elif pay_url:
                keyboard_buttons.append([
                    InlineKeyboardButton(
                        text="💎 Оплатить в браузере", 
                        url=pay_url
                    )
                ])
            
            # Дополнительные кнопки
            keyboard_buttons.extend([
                [
                    InlineKeyboardButton(text="🔄 Проверить оплату", callback_data=f"check_cryptopay_{payment.id}"),
                    InlineKeyboardButton(text="❌ Отменить", callback_data=f"cancel_payment_{payment.id}")
                ],
                [InlineKeyboardButton(text="❓ Что такое CryptoPay?", callback_data="cryptopay_info")],
                [InlineKeyboardButton(text="💬 Поддержка", callback_data="support")]
            ])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
            
            await callback.message.edit_text(text=text, reply_markup=keyboard)
            
            # Сохраняем данные в состояние
            await state.update_data(
                payment_id=payment.id,
                cryptopay_invoice_id=cryptopay_invoice.get("invoice_id"),
                payment_method="cryptopay"
            )
            await state.set_state(PaymentStates.waiting_payment)
            
            # Логируем создание платежа
            await user_service.log_user_action(
                user_id=user.id,
                action="cryptopay_payment_initiated",
                details={
                    "payment_id": payment.id,
                    "amount": float(usdt_amount),
                    "invoice_id": cryptopay_invoice.get("invoice_id")
                }
            )
            
            # Запускаем мониторинг CryptoPay платежа
            asyncio.create_task(monitor_cryptopay_payment(payment.id, session))
            
        except Exception as e:
            logger.error(f"Error creating CryptoPay payment: {e}")
            await callback.message.edit_text(
                "❌ Ошибка при создании CryptoPay платежа. Попробуйте позже.",
                reply_markup=get_back_button("subscriptions")
            )
        
    except Exception as e:
        logger.error(f"Error in create_cryptopay_payment: {e}")


@router.callback_query(F.data == "cryptopay_info")
async def show_cryptopay_info(callback: CallbackQuery, **kwargs):
    """Показать информацию о CryptoPay"""
    try:
        await callback.answer()
        
        text = f"💎 <b>Что такое CryptoPay?</b>\n\n"
        text += f"🚀 CryptoPay - это удобный сервис для оплаты криптовалютами прямо в Telegram.\n\n"
        text += f"✅ <b>Преимущества:</b>\n"
        text += f"• Оплата без выхода из Telegram\n"
        text += f"• 15+ поддерживаемых криптовалют\n"
        text += f"• Мгновенное зачисление средств\n"
        text += f"• Низкие комиссии сети\n"
        text += f"• Безопасные транзакции\n\n"
        text += f"💰 <b>Поддерживаемые валюты:</b>\n"
        text += f"• USDT, BTC, ETH, TON\n"
        text += f"• USDC, LTC, BNB, TRX\n"
        text += f"• И многие другие\n\n"
        text += f"🔒 <b>Безопасность:</b>\n"
        text += f"• Все транзакции проходят через блокчейн\n"
        text += f"• Средства поступают мгновенно\n"
        text += f"• Полная прозрачность операций"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад к оплате", callback_data="back_to_payment")]
        ])
        
        await callback.message.edit_text(text=text, reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Error showing CryptoPay info: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data.startswith("check_payment_"))
async def check_payment_status(callback: CallbackQuery, state: FSMContext, session, **kwargs):
    """Проверить статус платежа"""
    try:
        await callback.answer("Проверяем статус платежа...")
        
        payment_id = int(callback.data.split("_")[2])
        
        payment_service = PaymentService(session)
        repos = RepositoryManager(session)
        
        # Получаем платеж
        payment = await repos.payments.get_by_id(payment_id)
        if not payment:
            await callback.answer("❌ Платеж не найден", show_alert=True)
            return
        
        # Проверяем актуальный статус
        updated_payment = await payment_service.check_payment_status(payment_id)
        
        if updated_payment.status == PaymentStatus.COMPLETED:
            # Платеж завершен успешно
            text = "✅ <b>Платеж успешно завершен!</b>\n\n"
            text += f"💰 Оплачено: {payment.amount} {payment.currency}\n"
            text += f"📅 Время оплаты: {payment.paid_at.strftime('%d.%m.%Y %H:%M')}\n\n"
            text += "🎉 Ваша подписка активирована!\n"
            text += "Перейдите в раздел конфигураций для получения VPN."
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⚙️ Мои конфигурации", callback_data="my_configs")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
            ])
            
            await callback.message.edit_text(text=text, reply_markup=keyboard)
            await state.clear()
            
        elif updated_payment.status == PaymentStatus.FAILED:
            # Платеж не прошел
            text = "❌ <b>Платеж не прошел</b>\n\n"
            text += "Возможные причины:\n"
            text += "• Недостаточно средств на карте\n"
            text += "• Карта заблокирована банком\n"
            text += "• Технические проблемы\n\n"
            text += "Попробуйте:\n"
            text += "• Оплатить другой картой\n"
            text += "• Использовать криптовалюту\n"
            text += "• Обратиться в поддержку"
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Попробовать снова", callback_data="subscriptions")],
                [InlineKeyboardButton(text="💬 Поддержка", callback_data="support")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
            ])
            
            await callback.message.edit_text(text=text, reply_markup=keyboard)
            await state.clear()
            
        else:
            # Платеж еще в обработке
            expires_in = ""
            if payment.expires_at:
                time_left = payment.expires_at - datetime.utcnow()
                if time_left.total_seconds() > 0:
                    minutes_left = int(time_left.total_seconds() / 60)
                    expires_in = f"\n⏰ Осталось времени: {minutes_left} минут"
                else:
                    expires_in = "\n⏰ Время на оплату истекло"
            
            text = f"🔄 <b>Платеж в обработке</b>\n\n"
            text += f"💰 Сумма: {payment.amount} {payment.currency}\n"
            text += f"📅 Создан: {payment.created_at.strftime('%d.%m.%Y %H:%M')}"
            text += expires_in
            text += f"\n\n💡 Как только оплата пройдет, подписка активируется автоматически."
            
            # Обновляем клавиатуру с актуальными кнопками
            keyboard = get_payment_status_keyboard(payment_id, payment.payment_method)
            await callback.message.edit_text(text=text, reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Error checking payment status: {e}")
        await callback.answer("❌ Ошибка при проверке статуса", show_alert=True)


@router.callback_query(F.data.startswith("check_cryptopay_"))
async def check_cryptopay_payment(callback: CallbackQuery, state: FSMContext, session, **kwargs):
    """Проверить CryptoPay платеж"""
    try:
        await callback.answer("Проверяем статус CryptoPay...")
        
        payment_id = int(callback.data.split("_")[2])
        
        payment_service = PaymentService(session)
        
        # Проверяем статус в CryptoPay
        result = await payment_service.check_cryptopay_status(payment_id)
        
        if result["status"] == "paid":
            await callback.answer("✅ CryptoPay платеж завершен! Активируем подписку...", show_alert=True)
            # Статус обновится автоматически через webhook или мониторинг
        elif result["status"] == "active":
            await callback.answer(
                "🔄 Платеж создан, ожидаем оплату через CryptoPay",
                show_alert=True
            )
        else:
            await callback.answer(
                "⏳ Платеж еще в обработке. Проверьте через несколько минут.",
                show_alert=True
            )
        
    except Exception as e:
        logger.error(f"Error checking CryptoPay payment: {e}")
        await callback.answer("❌ Ошибка при проверке CryptoPay", show_alert=True)
        
        payment_service = PaymentService(session)
        
        # Проверяем транзакции в блокчейне
        result = await payment_service.check_crypto_transaction(payment_id)
        
        if result["status"] == "confirmed":
            await callback.answer("✅ Транзакция подтверждена! Активируем подписку...", show_alert=True)
            # Статус обновится автоматически через мониторинг
        elif result["status"] == "pending":
            confirmations = result.get("confirmations", 0)
            required = result.get("required_confirmations", 3)
            
            await callback.answer(
                f"🔄 Транзакция найдена! Подтверждений: {confirmations}/{required}",
                show_alert=True
            )
        else:
            await callback.answer(
                "⏳ Транзакция еще не найдена. Проверьте через несколько минут.",
                show_alert=True
            )
        
    except Exception as e:
        logger.error(f"Error checking crypto payment: {e}")
        await callback.answer("❌ Ошибка при проверке транзакции", show_alert=True)


@router.callback_query(F.data.startswith("cancel_payment_"))
async def cancel_payment(callback: CallbackQuery, state: FSMContext, session, **kwargs):
    """Отменить платеж"""
    try:
        await callback.answer()
        
        payment_id = int(callback.data.split("_")[2])
        
        payment_service = PaymentService(session)
        
        # Отменяем платеж
        success = await payment_service.cancel_payment(payment_id)
        
        if success:
            text = "❌ <b>Платеж отменен</b>\n\n"
            text += "Вы можете выбрать другой способ оплаты или тариф."
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📦 Выбрать тариф", callback_data="subscriptions")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
            ])
            
            await callback.message.edit_text(text=text, reply_markup=keyboard)
            await state.clear()
        else:
            await callback.answer("❌ Не удалось отменить платеж", show_alert=True)
        
    except Exception as e:
        logger.error(f"Error canceling payment: {e}")
        await callback.answer("❌ Ошибка при отмене платежа", show_alert=True)


@router.callback_query(F.data.startswith("copy_address_"))
async def copy_wallet_address(callback: CallbackQuery, state: FSMContext, session, **kwargs):
    """Скопировать адрес кошелька"""
    try:
        payment_id = int(callback.data.split("_")[2])
        
        data = await state.get_data()
        wallet_address = data.get("wallet_address")
        
        if wallet_address:
            # Отправляем адрес отдельным сообщением для легкого копирования
            await callback.message.answer(
                f"📋 <b>Адрес для копирования:</b>\n\n<code>{wallet_address}</code>",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Назад к платежу", callback_data=f"check_crypto_{payment_id}")]
                ])
            )
            await callback.answer("📋 Адрес отправлен отдельным сообщением", show_alert=False)
        else:
            await callback.answer("❌ Адрес не найден", show_alert=True)
        
    except Exception as e:
        logger.error(f"Error copying address: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data.startswith("crypto_instruction_"))
async def show_crypto_instruction(callback: CallbackQuery, state: FSMContext, **kwargs):
    """Показать инструкцию по криптоплатежам"""
    try:
        await callback.answer()
        
        currency = callback.data.split("_")[2]
        
        instructions = {
            "BTC": {
                "name": "Bitcoin",
                "apps": ["Electrum", "Bitcoin Core", "Trust Wallet", "Coinbase"],
                "network": "Bitcoin Network",
                "time": "10-60 минут"
            },
            "ETH": {
                "name": "Ethereum", 
                "apps": ["MetaMask", "Trust Wallet", "Coinbase", "MyEtherWallet"],
                "network": "Ethereum Network (ERC-20)",
                "time": "5-15 минут"
            },
            "USDT": {
                "name": "Tether",
                "apps": ["Trust Wallet", "MetaMask", "Coinbase", "Binance"],
                "network": "Ethereum Network (ERC-20)",
                "time": "5-15 минут"
            }
        }
        
        info = instructions.get(currency, instructions["BTC"])
        
        text = f"📱 <b>Инструкция по оплате {info['name']}</b>\n\n"
        text += f"💳 <b>Рекомендуемые кошельки:</b>\n"
        for app in info['apps']:
            text += f"• {app}\n"
        text += f"\n🌐 <b>Сеть:</b> {info['network']}\n"
        text += f"⏰ <b>Время подтверждения:</b> {info['time']}\n\n"
        text += f"📋 <b>Пошаговая инструкция:</b>\n"
        text += f"1. Откройте ваш криптокошелек\n"
        text += f"2. Выберите 'Отправить' или 'Send'\n"
        text += f"3. Вставьте адрес получателя\n"
        text += f"4. Укажите точную сумму\n"
        text += f"5. Подтвердите транзакцию\n\n"
        text += f"⚠️ <b>Важно:</b>\n"
        text += f"• Проверьте правильность адреса\n"
        text += f"• Используйте правильную сеть\n"
        text += f"• Не отправляйте с биржевых аккаунтов"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад к оплате", callback_data="back_to_payment")]
        ])
        
        await callback.message.edit_text(text=text, reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Error showing crypto instruction: {e}")
        await callback.answer("❌ Ошибка при загрузке инструкции", show_alert=True)


# Фоновые задачи для мониторинга платежей

async def monitor_payment_status(payment_id: int, session):
    """Мониторинг статуса платежа ЮKassa"""
    try:
        payment_service = PaymentService(session)
        
        # Проверяем статус каждые 30 секунд в течение 15 минут
        for _ in range(30):  # 30 проверок по 30 секунд = 15 минут
            await asyncio.sleep(30)
            
            payment = await payment_service.check_payment_status(payment_id)
            
            if payment.status in [PaymentStatus.COMPLETED, PaymentStatus.FAILED]:
                # Платеж завершен, отправляем уведомление пользователю
                await notify_payment_status_change(payment, session)
                break
                
    except Exception as e:
        logger.error(f"Error monitoring payment {payment_id}: {e}")


async def monitor_cryptopay_payment(payment_id: int, session):
    """Мониторинг CryptoPay платежа"""
    try:
        payment_service = PaymentService(session)
        
        # Проверяем каждые 1 минуту в течение 1 часа
        for _ in range(60):  # 60 проверок по 1 минуте = 1 час
            await asyncio.sleep(60)  # 1 минута
            
            result = await payment_service.check_cryptopay_status(payment_id)
            
            if result["status"] == "paid":
                # CryptoPay платеж завершен
                payment = await payment_service.complete_payment(payment_id)
                await notify_payment_status_change(payment, session)
                break
            elif result["status"] == "expired":
                # Платеж истек
                await payment_service.expire_payment(payment_id)
                break
                
    except Exception as e:
        logger.error(f"Error monitoring CryptoPay payment {payment_id}: {e}")


# Удаляем старые функции USDT
# async def monitor_usdt_payment() - убрана


async def notify_payment_status_change(payment, session):
    """Уведомить пользователя об изменении статуса платежа"""
    try:
        # Здесь должна быть отправка уведомления пользователю
        # Это можно реализовать через отдельный сервис уведомлений
        logger.info(f"Payment {payment.id} status changed to {payment.status}")
        
    except Exception as e:
        logger.error(f"Error notifying payment status change: {e}")