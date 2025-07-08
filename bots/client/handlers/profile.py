"""
Обработчик профиля пользователя для клиентского бота
"""

from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from loguru import logger

from bots.client.states.client_states import ProfileStates
from bots.client.keyboards.inline import get_profile_keyboard, get_back_button
from core.services.user_service import UserService
from core.services.subscription_service import SubscriptionService
from core.database.repositories import RepositoryManager
from core.database.models import VpnProtocol
from core.utils.helpers import format_bytes, format_duration, format_datetime

router = Router()


@router.callback_query(F.data == "profile")
async def show_profile(callback: CallbackQuery, state: FSMContext, session, **kwargs):
    """Показать профиль пользователя"""
    try:
        await callback.answer()
        
        user_service = UserService(session)
        subscription_service = SubscriptionService(session)
        
        user = await user_service.get_user_by_telegram_id(callback.from_user.id)
        
        if not user:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return
        
        # Получаем активную подписку
        active_subscription = await subscription_service.get_active_subscription(user.id)
        
        # Получаем статистику пользователя
        user_stats = await user_service.get_user_statistics(user.id)
        
        # Формируем информацию о профиле
        text = f"👤 <b>Ваш профиль</b>\n\n"
        
        # Основная информация
        text += f"🆔 <b>ID:</b> {user.telegram_id}\n"
        if user.username:
            text += f"👤 <b>Username:</b> @{user.username}\n"
        text += f"📝 <b>Имя:</b> {user.first_name}"
        if user.last_name:
            text += f" {user.last_name}"
        text += "\n"
        text += f"🌍 <b>Язык:</b> {user.language_code.upper()}\n"
        text += f"📅 <b>Регистрация:</b> {format_datetime(user.created_at)}\n"
        
        if user.last_activity:
            text += f"🕐 <b>Последний вход:</b> {format_datetime(user.last_activity)}\n"
        
        text += "\n"
        
        # Информация о подписке
        if active_subscription:
            expires_at = active_subscription.expires_at
            days_left = (expires_at - datetime.utcnow()).days if expires_at else 0
            
            text += "📦 <b>Активная подписка:</b>\n"
            text += f"   • План: {active_subscription.plan.name}\n"
            text += f"   • Сервер: {active_subscription.server.name}\n"
            text += f"   • Протокол: {active_subscription.active_protocol.value.upper()}\n"
            
            if expires_at:
                if days_left > 0:
                    text += f"   • До окончания: {days_left} дней\n"
                    text += f"   • Истекает: {format_datetime(expires_at)}\n"
                else:
                    text += f"   • ⚠️ Подписка истекла\n"
            
            # Статистика трафика
            if active_subscription.traffic_limit_gb:
                used_gb = active_subscription.traffic_used_gb
                limit_gb = active_subscription.traffic_limit_gb
                percent_used = (used_gb / limit_gb) * 100 if limit_gb > 0 else 0
                text += f"   • Трафик: {used_gb:.1f} ГБ / {limit_gb} ГБ ({percent_used:.1f}%)\n"
            else:
                text += f"   • Трафик: {active_subscription.traffic_used_gb:.1f} ГБ (безлимит)\n"
        else:
            text += "📦 <b>Подписка:</b> Не активна\n"
        
        text += "\n"
        
        # Статистика использования
        text += "📊 <b>Статистика:</b>\n"
        text += f"   • Всего подписок: {user_stats.get('total_subscriptions', 0)}\n"
        text += f"   • Использовано трафика: {format_bytes(user_stats.get('total_traffic_bytes', 0))}\n"
        text += f"   • Конфигураций создано: {user_stats.get('total_configs', 0)}\n"
        
        # VPN предпочтения
        text += "\n🔧 <b>Настройки VPN:</b>\n"
        if user.preferred_protocol:
            text += f"   • Предпочитаемый протокол: {user.preferred_protocol.value.upper()}\n"
        else:
            text += f"   • Предпочитаемый протокол: Автовыбор\n"
        text += f"   • Автовыбор протокола: {'Да' if user.auto_select_protocol else 'Нет'}\n"
        
        await callback.message.edit_text(
            text=text,
            reply_markup=get_profile_keyboard()
        )
        
        await state.set_state(ProfileStates.viewing_stats)
        
    except Exception as e:
        logger.error(f"Error showing profile: {e}")
        await callback.answer("❌ Ошибка при загрузке профиля", show_alert=True)


@router.callback_query(F.data == "profile_stats")
async def show_detailed_stats(callback: CallbackQuery, state: FSMContext, session, **kwargs):
    """Показать детальную статистику"""
    try:
        await callback.answer()
        
        user_service = UserService(session)
        user = await user_service.get_user_by_telegram_id(callback.from_user.id)
        
        # Получаем подробную статистику
        detailed_stats = await user_service.get_detailed_statistics(user.id)
        
        text = "📊 <b>Детальная статистика</b>\n\n"
        
        # Статистика по месяцам
        monthly_stats = detailed_stats.get('monthly_stats', [])
        if monthly_stats:
            text += "📈 <b>По месяцам (последние 6):</b>\n"
            for month_stat in monthly_stats[-6:]:
                month_name = month_stat['month']
                traffic_gb = month_stat['traffic_gb']
                text += f"   • {month_name}: {traffic_gb:.1f} ГБ\n"
        else:
            text += "📈 <b>Месячная статистика:</b> Данных нет\n"
        
        text += "\n"
        
        # Статистика по серверам
        server_stats = detailed_stats.get('server_stats', [])
        if server_stats:
            text += "🌍 <b>По серверам:</b>\n"
            for server_stat in server_stats:
                server_name = server_stat['server_name']
                sessions = server_stat['sessions']
                traffic_gb = server_stat['traffic_gb']
                text += f"   • {server_name}: {sessions} сессий, {traffic_gb:.1f} ГБ\n"
        else:
            text += "🌍 <b>Статистика серверов:</b> Данных нет\n"
        
        text += "\n"
        
        # Статистика по протоколам
        protocol_stats = detailed_stats.get('protocol_stats', [])
        if protocol_stats:
            text += "🔐 <b>По протоколам:</b>\n"
            for protocol_stat in protocol_stats:
                protocol = protocol_stat['protocol']
                usage_percent = protocol_stat['usage_percent']
                text += f"   • {protocol.upper()}: {usage_percent:.1f}%\n"
        else:
            text += "🔐 <b>Статистика протоколов:</b> Данных нет\n"
        
        # Активность за последнюю неделю
        week_activity = detailed_stats.get('week_activity', [])
        if week_activity:
            text += "\n📅 <b>Активность за неделю:</b>\n"
            total_actions = sum(day['actions'] for day in week_activity)
            text += f"   • Всего действий: {total_actions}\n"
            text += f"   • Дней активности: {len([d for d in week_activity if d['actions'] > 0])}\n"
        
        # Кнопки навигации
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 Экспорт данных", callback_data="export_user_data"),
                InlineKeyboardButton(text="🔄 Обновить", callback_data="profile_stats")
            ],
            [InlineKeyboardButton(text="🔙 К профилю", callback_data="profile")]
        ])
        
        await callback.message.edit_text(
            text=text,
            reply_markup=keyboard
        )
        
    except Exception as e:
        logger.error(f"Error showing detailed stats: {e}")
        await callback.answer("❌ Ошибка при загрузке статистики", show_alert=True)


@router.callback_query(F.data == "profile_settings")
async def show_profile_settings(callback: CallbackQuery, state: FSMContext, session, **kwargs):
    """Показать настройки профиля"""
    try:
        await callback.answer()
        
        user_service = UserService(session)
        user = await user_service.get_user_by_telegram_id(callback.from_user.id)
        
        # Получаем настройки уведомлений
        notification_settings = await user_service.get_notification_settings(user.id)
        
        text = "⚙️ <b>Настройки профиля</b>\n\n"
        
        # Основные настройки
        text += "🌍 <b>Язык интерфейса:</b>\n"
        text += f"   • Текущий: {user.language_code.upper()}\n\n"
        
        text += "🔐 <b>VPN протокол:</b>\n"
        if user.preferred_protocol:
            text += f"   • Предпочитаемый: {user.preferred_protocol.value.upper()}\n"
        else:
            text += f"   • Предпочитаемый: Автовыбор\n"
        text += f"   • Автовыбор: {'Включен' if user.auto_select_protocol else 'Выключен'}\n\n"
        
        # Настройки уведомлений
        text += "🔔 <b>Уведомления:</b>\n"
        expiry_notifications = notification_settings.get('expiry_notifications', True)
        maintenance_notifications = notification_settings.get('maintenance_notifications', True)
        news_notifications = notification_settings.get('news_notifications', False)
        
        text += f"   • Об истечении подписки: {'Включены' if expiry_notifications else 'Выключены'}\n"
        text += f"   • О технических работах: {'Включены' if maintenance_notifications else 'Выключены'}\n"
        text += f"   • Новости и обновления: {'Включены' if news_notifications else 'Выключены'}\n\n"
        
        text += "Выберите настройку для изменения:"
        
        # Кнопки настроек
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🌍 Язык", callback_data="settings_language"),
                InlineKeyboardButton(text="🔐 Протокол", callback_data="settings_protocol")
            ],
            [
                InlineKeyboardButton(text="🔔 Уведомления", callback_data="settings_notifications"),
                InlineKeyboardButton(text="🎨 Интерфейс", callback_data="settings_interface")
            ],
            [
                InlineKeyboardButton(text="🔒 Приватность", callback_data="settings_privacy"),
                InlineKeyboardButton(text="📱 Устройства", callback_data="settings_devices")
            ],
            [InlineKeyboardButton(text="🔙 К профилю", callback_data="profile")]
        ])
        
        await callback.message.edit_text(
            text=text,
            reply_markup=keyboard
        )
        
        await state.set_state(ProfileStates.editing_settings)
        
    except Exception as e:
        logger.error(f"Error showing profile settings: {e}")
        await callback.answer("❌ Ошибка при загрузке настроек", show_alert=True)


@router.callback_query(F.data == "settings_language")
async def change_language(callback: CallbackQuery, state: FSMContext, session, **kwargs):
    """Изменить язык интерфейса"""
    try:
        await callback.answer()
        
        text = "🌍 <b>Выберите язык интерфейса:</b>\n\n"
        text += "Choose your interface language:\n\n"
        text += "🇷🇺 Русский - для пользователей из России\n"
        text += "🇺🇸 English - for international users"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🇷🇺 Русский", callback_data="set_lang_ru"),
                InlineKeyboardButton(text="🇺🇸 English", callback_data="set_lang_en")
            ],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="profile_settings")]
        ])
        
        await callback.message.edit_text(
            text=text,
            reply_markup=keyboard
        )
        
        await state.set_state(ProfileStates.editing_language)
        
    except Exception as e:
        logger.error(f"Error changing language: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data.startswith("set_lang_"))
async def set_language(callback: CallbackQuery, state: FSMContext, session, **kwargs):
    """Установить язык"""
    try:
        await callback.answer()
        
        language = callback.data.split("_")[2]
        
        user_service = UserService(session)
        user = await user_service.get_user_by_telegram_id(callback.from_user.id)
        
        # Обновляем язык
        success = await user_service.update_user_preferences(
            user_id=user.id,
            language_code=language
        )
        
        if success:
            lang_names = {
                "ru": "русский", 
                "en": "английский"
            }
            
            if language == "en":
                text = f"✅ Interface language changed to English"
            else:
                text = f"✅ Язык интерфейса изменен на {lang_names.get(language, language)}"
            
            # Логируем изменение
            await user_service.log_user_action(
                user_id=user.id,
                action="language_changed",
                details={"new_language": language}
            )
        else:
            text = "❌ Ошибка при изменении языка / Error changing language"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 К настройкам / Back to settings", callback_data="profile_settings")]
        ])
        
        await callback.message.edit_text(
            text=text,
            reply_markup=keyboard
        )
        
    except Exception as e:
        logger.error(f"Error setting language: {e}")
        await callback.answer("❌ Ошибка при изменении языка", show_alert=True)


@router.callback_query(F.data == "settings_protocol")
async def change_protocol_settings(callback: CallbackQuery, state: FSMContext, session, **kwargs):
    """Изменить настройки протокола"""
    try:
        await callback.answer()
        
        user_service = UserService(session)
        user = await user_service.get_user_by_telegram_id(callback.from_user.id)
        
        text = "🔐 <b>Настройки VPN протокола</b>\n\n"
        text += "Выберите предпочитаемый протокол или оставьте автовыбор:\n\n"
        
        # Описания протоколов
        text += "🔥 <b>VLESS</b> - рекомендуется для России\n"
        text += "   • Лучший обход блокировок\n"
        text += "   • Поддержка Reality\n"
        text += "   • Высокая стабильность\n\n"
        
        text += "💙 <b>VMess</b> - универсальный протокол\n"
        text += "   • Хорошая совместимость\n"
        text += "   • Стабильное соединение\n\n"
        
        text += "🛡️ <b>OpenVPN</b> - классический протокол\n"
        text += "   • Максимальная совместимость\n"
        text += "   • Надежная безопасность\n\n"
        
        text += "⚡ <b>WireGuard</b> - быстрый и современный\n"
        text += "   • Высокая скорость\n"
        text += "   • Низкое энергопотребление\n\n"
        
        text += "🤖 <b>Автовыбор</b> - система выберет лучший"
        
        # Показываем текущую настройку
        if user.preferred_protocol:
            text += f"\n\n<b>Текущий выбор:</b> {user.preferred_protocol.value.upper()}"
        else:
            text += f"\n\n<b>Текущий выбор:</b> Автовыбор"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔥 VLESS", callback_data="set_protocol_vless"),
                InlineKeyboardButton(text="💙 VMess", callback_data="set_protocol_vmess")
            ],
            [
                InlineKeyboardButton(text="🛡️ OpenVPN", callback_data="set_protocol_openvpn"),
                InlineKeyboardButton(text="⚡ WireGuard", callback_data="set_protocol_wireguard")
            ],
            [InlineKeyboardButton(text="🤖 Автовыбор", callback_data="set_protocol_auto")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="profile_settings")]
        ])
        
        await callback.message.edit_text(
            text=text,
            reply_markup=keyboard
        )
        
        await state.set_state(ProfileStates.changing_protocol)
        
    except Exception as e:
        logger.error(f"Error showing protocol settings: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data.startswith("set_protocol_"))
async def set_protocol_preference(callback: CallbackQuery, state: FSMContext, session, **kwargs):
    """Установить предпочитаемый протокол"""
    try:
        await callback.answer()
        
        protocol_choice = callback.data.split("_")[2]
        
        user_service = UserService(session)
        user = await user_service.get_user_by_telegram_id(callback.from_user.id)
        
        # Определяем новые настройки
        if protocol_choice == "auto":
            preferred_protocol = None
            auto_select = True
            protocol_name = "Автовыбор"
        else:
            preferred_protocol = VpnProtocol(protocol_choice)
            auto_select = False
            protocol_names = {
                "vless": "VLESS",
                "vmess": "VMess",
                "openvpn": "OpenVPN",
                "wireguard": "WireGuard"
            }
            protocol_name = protocol_names.get(protocol_choice, protocol_choice.upper())
        
        # Обновляем настройки
        success = await user_service.update_user_preferences(
            user_id=user.id,
            preferred_protocol=preferred_protocol,
            auto_select_protocol=auto_select
        )
        
        if success:
            text = f"✅ <b>Протокол изменен</b>\n\n"
            text += f"🔐 Новое предпочтение: {protocol_name}\n\n"
            
            if protocol_choice != "auto":
                text += f"📝 <b>Что это означает:</b>\n"
                text += f"• При создании новых конфигураций будет использоваться {protocol_name}\n"
                text += f"• Существующие конфигурации останутся без изменений\n"
                text += f"• Вы можете создать конфигурации для других протоколов вручную"
            else:
                text += f"📝 <b>Что это означает:</b>\n"
                text += f"• Система автоматически выберет лучший протокол\n"
                text += f"• Для России обычно выбирается VLESS\n"
                text += f"• Учитываются особенности вашего региона"
            
            # Логируем изменение
            await user_service.log_user_action(
                user_id=user.id,
                action="protocol_preference_changed",
                details={
                    "new_protocol": protocol_choice,
                    "auto_select": auto_select
                }
            )
        else:
            text = "❌ Ошибка при изменении настроек протокола"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Изменить снова", callback_data="settings_protocol"),
                InlineKeyboardButton(text="🔙 К настройкам", callback_data="profile_settings")
            ]
        ])
        
        await callback.message.edit_text(
            text=text,
            reply_markup=keyboard
        )
        
    except Exception as e:
        logger.error(f"Error setting protocol preference: {e}")
        await callback.answer("❌ Ошибка при изменении протокола", show_alert=True)


@router.callback_query(F.data == "settings_notifications")
async def notification_settings(callback: CallbackQuery, state: FSMContext, session, **kwargs):
    """Настройки уведомлений"""
    try:
        await callback.answer()
        
        user_service = UserService(session)
        user = await user_service.get_user_by_telegram_id(callback.from_user.id)
        
        # Получаем текущие настройки уведомлений
        notification_settings = await user_service.get_notification_settings(user.id)
        
        text = "🔔 <b>Настройки уведомлений</b>\n\n"
        text += "Выберите типы уведомлений, которые хотите получать:\n\n"
        
        expiry_notifications = notification_settings.get('expiry_notifications', True)
        maintenance_notifications = notification_settings.get('maintenance_notifications', True)
        news_notifications = notification_settings.get('news_notifications', False)
        security_notifications = notification_settings.get('security_notifications', True)
        
        # Текущие настройки с эмодзи
        text += f"⏰ <b>Истечение подписки</b>\n"
        text += f"   {'✅ Включено' if expiry_notifications else '❌ Выключено'}\n"
        text += f"   Уведомления за 3 дня и в день истечения\n\n"
        
        text += f"🔧 <b>Технические работы</b>\n"
        text += f"   {'✅ Включено' if maintenance_notifications else '❌ Выключено'}\n"
        text += f"   Уведомления о плановых работах на серверах\n\n"
        
        text += f"📢 <b>Новости и обновления</b>\n"
        text += f"   {'✅ Включено' if news_notifications else '❌ Выключено'}\n"
        text += f"   Информация о новых функциях и улучшениях\n\n"
        
        text += f"🔒 <b>Безопасность</b>\n"
        text += f"   {'✅ Включено' if security_notifications else '❌ Выключено'}\n"
        text += f"   Уведомления о входах и изменениях настроек"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"⏰ Подписка: {'✅' if expiry_notifications else '❌'}",
                    callback_data="toggle_expiry_notifications"
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"🔧 Техработы: {'✅' if maintenance_notifications else '❌'}",
                    callback_data="toggle_maintenance_notifications"
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"📢 Новости: {'✅' if news_notifications else '❌'}",
                    callback_data="toggle_news_notifications"
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"🔒 Безопасность: {'✅' if security_notifications else '❌'}",
                    callback_data="toggle_security_notifications"
                )
            ],
            [
                InlineKeyboardButton(text="🔕 Отключить все", callback_data="disable_all_notifications"),
                InlineKeyboardButton(text="🔔 Включить все", callback_data="enable_all_notifications")
            ],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="profile_settings")]
        ])
        
        await callback.message.edit_text(
            text=text,
            reply_markup=keyboard
        )
        
    except Exception as e:
        logger.error(f"Error showing notification settings: {e}")
        await callback.answer("❌ Ошибка при загрузке настроек", show_alert=True)


@router.callback_query(F.data.startswith("toggle_"))
async def toggle_notification_setting(callback: CallbackQuery, state: FSMContext, session, **kwargs):
    """Переключить настройку уведомлений"""
    try:
        await callback.answer()
        
        setting_type = callback.data.replace("toggle_", "")
        
        user_service = UserService(session)
        user = await user_service.get_user_by_telegram_id(callback.from_user.id)
        
        # Получаем текущие настройки
        current_settings = await user_service.get_notification_settings(user.id)
        
        # Переключаем настройку
        current_value = current_settings.get(setting_type, True)
        new_value = not current_value
        
        # Обновляем настройки
        success = await user_service.update_notification_settings(
            user_id=user.id,
            **{setting_type: new_value}
        )
        
        if success:
            setting_names = {
                "expiry_notifications": "уведомления об истечении подписки",
                "maintenance_notifications": "уведомления о технических работах",
                "news_notifications": "новости и обновления",
                "security_notifications": "уведомления безопасности"
            }
            
            setting_name = setting_names.get(setting_type, setting_type)
            status = "включены" if new_value else "выключены"
            
            await callback.answer(f"✅ {setting_name.capitalize()} {status}", show_alert=False)
            
            # Логируем изменение
            await user_service.log_user_action(
                user_id=user.id,
                action="notification_setting_changed",
                details={
                    "setting": setting_type,
                    "new_value": new_value
                }
            )
        else:
            await callback.answer("❌ Ошибка при изменении настройки", show_alert=True)
        
        # Обновляем отображение настроек
        await notification_settings(callback, state, session, **kwargs)
        
    except Exception as e:
        logger.error(f"Error toggling notification setting: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data == "disable_all_notifications")
async def disable_all_notifications(callback: CallbackQuery, state: FSMContext, session, **kwargs):
    """Отключить все уведомления"""
    try:
        await callback.answer()
        
        user_service = UserService(session)
        user = await user_service.get_user_by_telegram_id(callback.from_user.id)
        
        # Отключаем все уведомления
        success = await user_service.update_notification_settings(
            user_id=user.id,
            expiry_notifications=False,
            maintenance_notifications=False,
            news_notifications=False,
            security_notifications=False
        )
        
        if success:
            await callback.answer("🔕 Все уведомления отключены", show_alert=False)
            
            # Логируем изменение
            await user_service.log_user_action(
                user_id=user.id,
                action="all_notifications_disabled"
            )
        else:
            await callback.answer("❌ Ошибка при отключении", show_alert=True)
        
        # Обновляем отображение
        await notification_settings(callback, state, session, **kwargs)
        
    except Exception as e:
        logger.error(f"Error disabling all notifications: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data == "enable_all_notifications")
async def enable_all_notifications(callback: CallbackQuery, state: FSMContext, session, **kwargs):
    """Включить все уведомления"""
    try:
        await callback.answer()
        
        user_service = UserService(session)
        user = await user_service.get_user_by_telegram_id(callback.from_user.id)
        
        # Включаем все уведомления
        success = await user_service.update_notification_settings(
            user_id=user.id,
            expiry_notifications=True,
            maintenance_notifications=True,
            news_notifications=True,
            security_notifications=True
        )
        
        if success:
            await callback.answer("🔔 Все уведомления включены", show_alert=False)
            
            # Логируем изменение
            await user_service.log_user_action(
                user_id=user.id,
                action="all_notifications_enabled"
            )
        else:
            await callback.answer("❌ Ошибка при включении", show_alert=True)
        
        # Обновляем отображение
        await notification_settings(callback, state, session, **kwargs)
        
    except Exception as e:
        logger.error(f"Error enabling all notifications: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data == "settings_privacy")
async def privacy_settings(callback: CallbackQuery, state: FSMContext, session, **kwargs):
    """Настройки приватности"""
    try:
        await callback.answer()
        
        user_service = UserService(session)
        user = await user_service.get_user_by_telegram_id(callback.from_user.id)
        
        # Получаем настройки приватности
        privacy_settings = await user_service.get_privacy_settings(user.id)
        
        text = "🔒 <b>Настройки приватности</b>\n\n"
        
        analytics_enabled = privacy_settings.get('analytics_enabled', True)
        error_reporting = privacy_settings.get('error_reporting', True)
        usage_statistics = privacy_settings.get('usage_statistics', True)
        
        text += f"📊 <b>Аналитика использования</b>\n"
        text += f"   {'✅ Разрешено' if analytics_enabled else '❌ Запрещено'}\n"
        text += f"   Помогает улучшать сервис\n\n"
        
        text += f"🐛 <b>Отчеты об ошибках</b>\n"
        text += f"   {'✅ Разрешено' if error_reporting else '❌ Запрещено'}\n"
        text += f"   Автоматическая отправка отчетов о сбоях\n\n"
        
        text += f"📈 <b>Статистика использования</b>\n"
        text += f"   {'✅ Разрешено' if usage_statistics else '❌ Запрещено'}\n"
        text += f"   Сбор анонимной статистики подключений\n\n"
        
        text += "🛡️ <b>Ваши данные защищены:</b>\n"
        text += "• Не передаются третьим лицам\n"
        text += "• Хранятся в зашифрованном виде\n"
        text += "• Используются только для улучшения сервиса"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"📊 Аналитика: {'✅' if analytics_enabled else '❌'}",
                    callback_data="toggle_analytics"
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"🐛 Отчеты: {'✅' if error_reporting else '❌'}",
                    callback_data="toggle_error_reporting"
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"📈 Статистика: {'✅' if usage_statistics else '❌'}",
                    callback_data="toggle_usage_stats"
                )
            ],
            [
                InlineKeyboardButton(text="📄 Политика конфиденциальности", callback_data="privacy_policy"),
            ],
            [
                InlineKeyboardButton(text="🗑️ Удалить данные", callback_data="delete_user_data"),
                InlineKeyboardButton(text="📊 Экспорт данных", callback_data="export_user_data")
            ],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="profile_settings")]
        ])
        
        await callback.message.edit_text(
            text=text,
            reply_markup=keyboard
        )
        
    except Exception as e:
        logger.error(f"Error showing privacy settings: {e}")
        await callback.answer("❌ Ошибка при загрузке настроек", show_alert=True)


@router.callback_query(F.data.startswith("toggle_analytics"))
@router.callback_query(F.data.startswith("toggle_error_reporting"))
@router.callback_query(F.data.startswith("toggle_usage_stats"))
async def toggle_privacy_setting(callback: CallbackQuery, state: FSMContext, session, **kwargs):
    """Переключить настройку приватности"""
    try:
        await callback.answer()
        
        setting_mapping = {
            "toggle_analytics": "analytics_enabled",
            "toggle_error_reporting": "error_reporting", 
            "toggle_usage_stats": "usage_statistics"
        }
        
        setting_type = setting_mapping.get(callback.data)
        if not setting_type:
            return
        
        user_service = UserService(session)
        user = await user_service.get_user_by_telegram_id(callback.from_user.id)
        
        # Получаем текущие настройки
        current_settings = await user_service.get_privacy_settings(user.id)
        
        # Переключаем настройку
        current_value = current_settings.get(setting_type, True)
        new_value = not current_value
        
        # Обновляем настройки
        success = await user_service.update_privacy_settings(
            user_id=user.id,
            **{setting_type: new_value}
        )
        
        if success:
            setting_names = {
                "analytics_enabled": "аналитика",
                "error_reporting": "отчеты об ошибках",
                "usage_statistics": "статистика использования"
            }
            
            setting_name = setting_names.get(setting_type, setting_type)
            status = "включена" if new_value else "отключена"
            
            await callback.answer(f"✅ {setting_name.capitalize()} {status}", show_alert=False)
            
            # Логируем изменение
            await user_service.log_user_action(
                user_id=user.id,
                action="privacy_setting_changed",
                details={
                    "setting": setting_type,
                    "new_value": new_value
                }
            )
        else:
            await callback.answer("❌ Ошибка при изменении настройки", show_alert=True)
        
        # Обновляем отображение
        await privacy_settings(callback, state, session, **kwargs)
        
    except Exception as e:
        logger.error(f"Error toggling privacy setting: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data == "export_user_data")
async def export_user_data(callback: CallbackQuery, state: FSMContext, session, **kwargs):
    """Экспорт пользовательских данных"""
    try:
        await callback.answer("Подготавливаем экспорт данных...")
        
        user_service = UserService(session)
        user = await user_service.get_user_by_telegram_id(callback.from_user.id)
        
        # Собираем все данные пользователя
        user_data = await user_service.export_user_data(user.id)
        
        # Создаем JSON файл
        import json
        import tempfile
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            json.dump(user_data, f, ensure_ascii=False, indent=2, default=str)
            temp_path = f.name
        
        # Отправляем файл
        from aiogram.types import FSInputFile
        file = FSInputFile(temp_path, filename=f"user_data_{user.telegram_id}.json")
        
        caption = (
            f"📊 <b>Экспорт ваших данных</b>\n\n"
            f"🗓️ Дата создания: {datetime.utcnow().strftime('%d.%m.%Y %H:%M')}\n"
            f"📁 Включает:\n"
            f"• Профиль и настройки\n"
            f"• История подписок\n"
            f"• Статистика использования\n"
            f"• Конфигурации VPN\n"
            f"• Логи активности\n\n"
            f"🔒 Данные в зашифрованном формате JSON"
        )
        
        await callback.message.answer_document(
            document=file,
            caption=caption
        )
        
        # Удаляем временный файл
        import os
        os.unlink(temp_path)
        
        # Логируем экспорт
        await user_service.log_user_action(
            user_id=user.id,
            action="user_data_exported"
        )
        
        await callback.answer("✅ Данные экспортированы", show_alert=False)
        
    except Exception as e:
        logger.error(f"Error exporting user data: {e}")
        await callback.answer("❌ Ошибка при экспорте данных", show_alert=True)


@router.callback_query(F.data == "delete_user_data")
async def delete_user_data_request(callback: CallbackQuery, state: FSMContext, session, **kwargs):
    """Запрос на удаление данных пользователя"""
    try:
        await callback.answer()
        
        text = (
            "🗑️ <b>Удаление данных пользователя</b>\n\n"
            "⚠️ <b>ВНИМАНИЕ!</b> Это действие необратимо.\n\n"
            "При удалении данных будут стерты:\n"
            "• Ваш профиль и настройки\n"
            "• Все VPN конфигурации\n"
            "• История подписок\n"
            "• Статистика использования\n"
            "• Сообщения в поддержке\n\n"
            "🔒 Активные подписки будут деактивированы.\n"
            "💰 Возврат средств не предусмотрен.\n\n"
            "Вы действительно хотите удалить все свои данные?"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="❌ НЕТ, отмена", callback_data="profile_settings"),
                InlineKeyboardButton(text="🗑️ ДА, удалить", callback_data="confirm_delete_user_data")
            ]
        ])
        
        await callback.message.edit_text(text=text, reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Error in delete user data request: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data == "confirm_delete_user_data")
async def confirm_delete_user_data(callback: CallbackQuery, state: FSMContext, session, **kwargs):
    """Подтверждение удаления данных пользователя"""
    try:
        await callback.answer("Удаляем ваши данные...")
        
        user_service = UserService(session)
        user = await user_service.get_user_by_telegram_id(callback.from_user.id)
        
        # Логируем удаление ПЕРЕД удалением
        await user_service.log_user_action(
            user_id=user.id,
            action="user_data_deletion_requested"
        )
        
        # Выполняем удаление данных
        success = await user_service.delete_user_data(user.id)
        
        if success:
            text = (
                "✅ <b>Данные удалены</b>\n\n"
                "Все ваши данные были успешно удалены из системы.\n\n"
                "Спасибо за использование нашего сервиса! 👋\n\n"
                "Вы можете создать новый аккаунт в любое время, отправив команду /start"
            )
            
            keyboard = None
        else:
            text = (
                "❌ <b>Ошибка при удалении данных</b>\n\n"
                "Не удалось полностью удалить ваши данные.\n"
                "Обратитесь в поддержку для решения этой проблемы."
            )
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🎧 Поддержка", callback_data="support")]
            ])
        
        await callback.message.edit_text(text=text, reply_markup=keyboard)
        await state.clear()
        
    except Exception as e:
        logger.error(f"Error confirming delete user data: {e}")
        await callback.answer("❌ Ошибка при удалении данных", show_alert=True)


@router.callback_query(F.data == "privacy_policy")
async def show_privacy_policy(callback: CallbackQuery, state: FSMContext, session, **kwargs):
    """Показать политику конфиденциальности"""
    try:
        await callback.answer()
        
        text = (
            "📄 <b>Политика конфиденциальности</b>\n\n"
            
            "🔒 <b>Какие данные мы собираем:</b>\n"
            "• Telegram ID и имя пользователя\n"
            "• Настройки и предпочтения VPN\n"
            "• Статистика использования сервиса\n"
            "• Логи подключений (без личных данных)\n\n"
            
            "🛡️ <b>Как мы защищаем данные:</b>\n"
            "• Шифрование всех данных в базе\n"
            "• Безопасные каналы передачи\n"
            "• Регулярные проверки безопасности\n"
            "• Доступ только авторизованного персонала\n\n"
            
            "📊 <b>Как мы используем данные:</b>\n"
            "• Предоставление VPN услуг\n"
            "• Улучшение качества сервиса\n"
            "• Техническая поддержка\n"
            "• Уведомления о сервисе\n\n"
            
            "🚫 <b>Что мы НЕ делаем:</b>\n"
            "• Не продаем данные третьим лицам\n"
            "• Не отслеживаем интернет-активность\n"
            "• Не логируем посещаемые сайты\n"
            "• Не сохраняем контент трафика\n\n"
            
            "📧 <b>Связь:</b> @support_bot"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 Экспорт данных", callback_data="export_user_data"),
                InlineKeyboardButton(text="🗑️ Удалить данные", callback_data="delete_user_data")
            ],
            [InlineKeyboardButton(text="🔙 К настройкам", callback_data="settings_privacy")]
        ])
        
        await callback.message.edit_text(text=text, reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Error showing privacy policy: {e}")
        await callback.answer("❌ Ошибка при загрузке", show_alert=True)


@router.callback_query(F.data == "referral_program")
async def show_referral_program(callback: CallbackQuery, state: FSMContext, session, **kwargs):
    """Показать реферальную программу"""
    try:
        await callback.answer()
        
        user_service = UserService(session)
        user = await user_service.get_user_by_telegram_id(callback.from_user.id)
        
        # Получаем реферальную статистику
        referral_stats = await user_service.get_referral_statistics(user.id)
        
        referral_link = f"https://t.me/{callback.bot.username}?start=ref_{user.telegram_id}"
        
        text = (
            "🎁 <b>Реферальная программа</b>\n\n"
            
            "💰 <b>Получайте бонусы за друзей!</b>\n\n"
            
            "🎯 <b>Как это работает:</b>\n"
            "1️⃣ Пригласите друга по вашей ссылке\n"
            "2️⃣ Друг регистрируется и покупает подписку\n"
            "3️⃣ Вы получаете 30% с его первого платежа\n"
            "4️⃣ Друг получает скидку 10% на первую покупку\n\n"
            
            f"📊 <b>Ваша статистика:</b>\n"
            f"• Приглашено: {referral_stats.get('total_referrals', 0)} человек\n"
            f"• Активных: {referral_stats.get('active_referrals', 0)} человек\n"
            f"• Заработано: {referral_stats.get('total_earned', 0)} ₽\n"
            f"• Доступно к выводу: {referral_stats.get('available_balance', 0)} ₽\n\n"
            
            f"🔗 <b>Ваша реферальная ссылка:</b>\n"
            f"<code>{referral_link}</code>\n\n"
            
            "💡 <b>Советы для успеха:</b>\n"
            "• Делитесь ссылкой в соцсетях\n"
            "• Рассказывайте о преимуществах VPN\n"
            "• Помогайте друзьям с настройкой"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="📋 Копировать ссылку", callback_data="copy_referral_link"),
                InlineKeyboardButton(text="📤 Поделиться", callback_data="share_referral_link")
            ],
            [
                InlineKeyboardButton(text="💰 Вывести средства", callback_data="withdraw_referral_earnings"),
                InlineKeyboardButton(text="📊 Детальная статистика", callback_data="detailed_referral_stats")
            ],
            [InlineKeyboardButton(text="🔙 К профилю", callback_data="profile")]
        ])
        
        await callback.message.edit_text(text=text, reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Error showing referral program: {e}")
        await callback.answer("❌ Ошибка при загрузке", show_alert=True)