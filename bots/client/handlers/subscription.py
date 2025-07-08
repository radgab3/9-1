"""
Обработчик подписок для клиентского бота
"""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from loguru import logger

from bots.client.states.client_states import SubscriptionStates, TrialStates
from bots.client.keyboards.inline import (
    get_subscription_plans_keyboard, get_servers_keyboard, 
    get_protocols_keyboard, get_payment_methods_keyboard,
    get_confirmation_keyboard, get_trial_keyboard, get_back_button
)
from core.services.subscription_service import SubscriptionService, SubscriptionPlanService
from core.services.server_service import ServerService
from core.services.user_service import UserService
from core.services.vpn.vpn_factory import VpnServiceManager
from core.database.models import VpnProtocol

router = Router()


@router.callback_query(F.data == "subscriptions")
@router.callback_query(F.data == "buy_subscription")
async def show_subscription_plans(callback: CallbackQuery, state: FSMContext, session, **kwargs):
    """Показать тарифные планы"""
    try:
        await callback.answer()
        
        plan_service = SubscriptionPlanService(session)
        plans = await plan_service.get_all_plans()
        
        if not plans:
            await callback.message.edit_text(
                "❌ Тарифные планы временно недоступны",
                reply_markup=get_back_button()
            )
            return
        
        text = "💎 <b>Выберите тарифный план:</b>\n\n"
        
        for plan in plans:
            emoji = "⭐" if plan.is_popular else "📦"
            
            text += f"{emoji} <b>{plan.name}</b>\n"
            text += f"💰 {plan.price} {plan.currency}\n"
            text += f"📅 {plan.duration_days} дней\n"
            
            if plan.traffic_limit_gb:
                text += f"📊 {plan.traffic_limit_gb} ГБ трафика\n"
            else:
                text += "📊 Безлимитный трафик\n"
                
            text += f"📱 {plan.device_limit} устройств\n\n"
        
        await callback.message.edit_text(
            text=text,
            reply_markup=get_subscription_plans_keyboard(plans)
        )
        
        await state.set_state(SubscriptionStates.selecting_plan)
        
    except Exception as e:
        logger.error(f"Error showing subscription plans: {e}")
        await callback.answer("❌ Ошибка при загрузке планов", show_alert=True)


@router.callback_query(F.data.startswith("plan_"))
async def select_plan(callback: CallbackQuery, state: FSMContext, session, **kwargs):
    """Выбор тарифного плана"""
    try:
        await callback.answer()
        
        plan_id = int(callback.data.split("_")[1])
        
        plan_service = SubscriptionPlanService(session)
        plan = await plan_service.get_plan_by_id(plan_id)
        
        if not plan:
            await callback.answer("❌ План не найден", show_alert=True)
            return
        
        # Сохраняем выбранный план
        await state.update_data(selected_plan_id=plan_id)
        
        # Показываем информацию о плане
        text = f"📦 <b>{plan.name}</b>\n\n"
        text += f"💰 Стоимость: {plan.price} {plan.currency}\n"
        text += f"📅 Период: {plan.duration_days} дней\n"
        
        if plan.traffic_limit_gb:
            text += f"📊 Трафик: {plan.traffic_limit_gb} ГБ\n"
        else:
            text += "📊 Трафик: Безлимит\n"
            
        text += f"📱 Устройства: {plan.device_limit}\n\n"
        text += f"📝 {plan.description}\n\n"
        text += "Теперь выберите сервер:"
        
        # Получаем доступные серверы
        server_service = ServerService(session)
        servers = await server_service.get_all_servers()
        
        await callback.message.edit_text(
            text=text,
            reply_markup=get_servers_keyboard(servers)
        )
        
        await state.set_state(SubscriptionStates.selecting_server)
        
    except Exception as e:
        logger.error(f"Error selecting plan: {e}")
        await callback.answer("❌ Ошибка при выборе плана", show_alert=True)


@router.callback_query(F.data.startswith("server_"))
async def select_server(callback: CallbackQuery, state: FSMContext, session, **kwargs):
    """Выбор сервера"""
    try:
        await callback.answer()
        
        server_id = int(callback.data.split("_")[1])
        
        server_service = ServerService(session)
        server = await server_service.get_server_by_id(server_id)
        
        if not server or not server.is_active:
            await callback.answer("❌ Сервер недоступен", show_alert=True)
            return
        
        # Сохраняем выбранный сервер
        await state.update_data(selected_server_id=server_id)
        
        # Показываем доступные протоколы
        text = f"🌍 <b>Сервер: {server.name}</b>\n"
        text += f"📍 {server.country}, {server.city}\n\n"
        text += "Выберите VPN протокол:"
        
        protocols = server.supported_protocols
        
        await callback.message.edit_text(
            text=text,
            reply_markup=get_protocols_keyboard(protocols)
        )
        
        await state.set_state(SubscriptionStates.selecting_protocol)
        
    except Exception as e:
        logger.error(f"Error selecting server: {e}")
        await callback.answer("❌ Ошибка при выборе сервера", show_alert=True)


@router.callback_query(F.data.startswith("protocol_"))
async def select_protocol(callback: CallbackQuery, state: FSMContext, session, **kwargs):
    """Выбор протокола"""
    try:
        await callback.answer()
        
        protocol = callback.data.split("_")[1]
        
        # Сохраняем выбранный протокол
        await state.update_data(selected_protocol=protocol)
        
        # Получаем данные заказа
        data = await state.get_data()
        plan_id = data.get("selected_plan_id")
        server_id = data.get("selected_server_id")
        
        # Получаем информацию для подтверждения
        plan_service = SubscriptionPlanService(session)
        server_service = ServerService(session)
        
        plan = await plan_service.get_plan_by_id(plan_id)
        server = await server_service.get_server_by_id(server_id)
        
        # Формируем сводку заказа
        text = "📋 <b>Подтверждение заказа:</b>\n\n"
        text += f"📦 План: {plan.name}\n"
        text += f"💰 Стоимость: {plan.price} {plan.currency}\n"
        text += f"🌍 Сервер: {server.name} ({server.country})\n"
        text += f"🔐 Протокол: {protocol.upper()}\n\n"
        text += "Подтверждаете заказ?"
        
        await callback.message.edit_text(
            text=text,
            reply_markup=get_confirmation_keyboard("order", plan_id)
        )
        
        await state.set_state(SubscriptionStates.confirming_purchase)
        
    except Exception as e:
        logger.error(f"Error selecting protocol: {e}")
        await callback.answer("❌ Ошибка при выборе протокола", show_alert=True)


@router.callback_query(F.data.startswith("confirm_order_"))
async def confirm_order(callback: CallbackQuery, state: FSMContext, session, **kwargs):
    """Подтверждение заказа"""
    try:
        await callback.answer()
        
        plan_id = int(callback.data.split("_")[2])
        
        # Получаем данные заказа
        data = await state.get_data()
        server_id = data.get("selected_server_id")
        protocol = data.get("selected_protocol")
        
        # Показываем способы оплаты
        text = "💳 <b>Выберите способ оплаты:</b>\n\n"
        text += "• Банковская карта (мгновенно)\n"
        text += "• Криптовалюта (BTC, ETH, USDT)\n\n"
        text += "После оплаты подписка активируется автоматически!"
        
        await callback.message.edit_text(
            text=text,
            reply_markup=get_payment_methods_keyboard(plan_id)
        )
        
        await state.set_state(SubscriptionStates.waiting_for_payment)
        
    except Exception as e:
        logger.error(f"Error confirming order: {e}")
        await callback.answer("❌ Ошибка при подтверждении", show_alert=True)


@router.callback_query(F.data == "trial_period")
async def show_trial_offer(callback: CallbackQuery, state: FSMContext, session, **kwargs):
    """Показать предложение пробного периода"""
    try:
        await callback.answer()
        
        user_service = UserService(session)
        user = await user_service.get_user_by_telegram_id(callback.from_user.id)
        
        # Проверяем, использовал ли пользователь пробный период
        subscription_service = SubscriptionService(session)
        user_subscriptions = await subscription_service.get_user_subscriptions(user.id)
        
        trial_used = any(sub.plan.is_trial for sub in user_subscriptions)
        
        if trial_used:
            text = (
                "❌ <b>Пробный период недоступен</b>\n\n"
                "Вы уже использовали пробный период.\n"
                "Выберите один из платных тарифов:"
            )
            
            plan_service = SubscriptionPlanService(session)
            plans = await plan_service.get_all_plans()
            non_trial_plans = [p for p in plans if not p.is_trial]
            
            await callback.message.edit_text(
                text=text,
                reply_markup=get_subscription_plans_keyboard(non_trial_plans)
            )
            return
        
        # Показываем условия пробного периода
        plan_service = SubscriptionPlanService(session)
        trial_plan = await plan_service.get_trial_plan()
        
        if not trial_plan:
            await callback.message.edit_text(
                "❌ Пробный период временно недоступен",
                reply_markup=get_back_button()
            )
            return
        
        text = f"🆓 <b>Пробный период</b>\n\n"
        text += f"📅 Срок: {trial_plan.duration_days} дней\n"
        text += f"📊 Трафик: {trial_plan.traffic_limit_gb} ГБ\n"
        text += f"📱 Устройств: {trial_plan.device_limit}\n"
        text += f"🌍 Доступ ко всем серверам\n\n"
        text += "✨ Попробуйте наш сервис бесплатно!\n"
        text += "После окончания можете приобрести полную подписку."
        
        await callback.message.edit_text(
            text=text,
            reply_markup=get_trial_keyboard()
        )
        
        await state.set_state(TrialStates.requesting_trial)
        
    except Exception as e:
        logger.error(f"Error showing trial offer: {e}")
        await callback.answer("❌ Ошибка при загрузке пробного периода", show_alert=True)


@router.callback_query(F.data == "activate_trial")
async def activate_trial(callback: CallbackQuery, state: FSMContext, session, **kwargs):
    """Активация пробного периода"""
    try:
        await callback.answer()
        
        user_service = UserService(session)
        subscription_service = SubscriptionService(session)
        plan_service = SubscriptionPlanService(session)
        server_service = ServerService(session)
        
        user = await user_service.get_user_by_telegram_id(callback.from_user.id)
        
        # Получаем пробный план
        trial_plan = await plan_service.get_trial_plan()
        if not trial_plan:
            await callback.answer("❌ Пробный план недоступен", show_alert=True)
            return
        
        # Выбираем лучший сервер
        best_server = await server_service.get_best_server_for_user(user)
        if not best_server:
            await callback.answer("❌ Серверы недоступны", show_alert=True)
            return
        
        # Создаем пробную подписку
        subscription = await subscription_service.create_subscription(
            user_id=user.id,
            plan_id=trial_plan.id,
            server_id=best_server.id,
            protocol=VpnProtocol.VLESS  # По умолчанию VLESS для РФ пользователей
        )
        
        # Активируем подписку
        await subscription_service.activate_subscription(subscription.id)
        
        # Создаем VPN конфигурацию
        vpn_manager = VpnServiceManager(session)
        config = await vpn_manager.create_config_for_best_protocol(
            server=best_server,
            subscription_id=subscription.id,
            preferred_protocol=VpnProtocol.VLESS
        )
        
        success_text = (
            "🎉 <b>Пробный период активирован!</b>\n\n"
            f"📅 Действует: {trial_plan.duration_days} дней\n"
            f"🌍 Сервер: {best_server.name}\n"
            f"🔐 Протокол: {config.protocol.value.upper()}\n\n"
            "✅ Ваша конфигурация готова!\n"
            "Используйте кнопку ниже для скачивания."
        )
        
        from bots.client.keyboards.inline import get_config_actions_keyboard
        
        await callback.message.edit_text(
            text=success_text,
            reply_markup=get_config_actions_keyboard(config.id)
        )
        
        await state.clear()
        
        # Логируем активацию пробного периода
        await user_service.log_user_action(
            user_id=user.id,
            action="trial_activated",
            details={
                "subscription_id": subscription.id,
                "server_id": best_server.id,
                "protocol": config.protocol.value
            }
        )
        
    except Exception as e:
        logger.error(f"Error activating trial: {e}")
        await callback.answer("❌ Ошибка при активации пробного периода", show_alert=True)


@router.callback_query(F.data.startswith("cancel_"))
async def cancel_action(callback: CallbackQuery, state: FSMContext, **kwargs):
    """Отмена действия"""
    try:
        await callback.answer()
        
        from bots.client.handlers.start import show_main_menu
        from core.services.user_service import UserService
        
        user_service = UserService(callback.bot.session)
        user = await user_service.get_user_by_telegram_id(callback.from_user.id)
        
        await show_main_menu(callback.message, user, state)
        
    except Exception as e:
        logger.error(f"Error canceling action: {e}")
        await callback.answer("❌ Ошибка при отмене", show_alert=True)