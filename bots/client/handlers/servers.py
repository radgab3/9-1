"""
Handlers для управления серверами в Client Bot
"""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict, Any
from loguru import logger

from core.database.models import Server, VpnProtocol, SubscriptionStatus
from core.services.server_service import ServerService
from core.services.subscription_service import SubscriptionService
from core.services.user_service import UserService
from bots.shared.utils.formatters import format_server_info, format_server_load
from bots.client.keyboards.inline import (
    create_servers_keyboard, 
    create_server_details_keyboard,
    create_protocol_selection_keyboard
)
from bots.client.states.client_states import ServerSelectionStates


router = Router(name="servers")


@router.message(Command("servers"))
async def cmd_servers(message: Message, session: AsyncSession, state: FSMContext):
    """Показать список доступных серверов"""
    try:
        await state.clear()
        
        user_service = UserService(session)
        user = await user_service.get_user_by_telegram_id(message.from_user.id)
        
        if not user:
            await message.answer("❌ Пользователь не найден. Используйте /start")
            return
        
        server_service = ServerService(session)
        servers = await server_service.get_all_servers()
        
        if not servers:
            await message.answer(
                "🔍 Серверы временно недоступны\n\n"
                "Мы работаем над добавлением новых серверов. "
                "Попробуйте позже или обратитесь в поддержку."
            )
            return
        
        # Группируем серверы по странам
        servers_by_country = {}
        for server in servers:
            country = server.country
            if country not in servers_by_country:
                servers_by_country[country] = []
            servers_by_country[country].append(server)
        
        text = "🌍 **Доступные серверы**\n\n"
        
        for country, country_servers in servers_by_country.items():
            text += f"🇺🇸 **{country}**\n"
            
            for server in country_servers:
                # Рассчитываем нагрузку
                load_percentage = (server.current_users / server.max_users * 100) if server.max_users > 0 else 0
                load_icon = "🟢" if load_percentage < 70 else "🟡" if load_percentage < 90 else "🔴"
                
                # Показываем поддерживаемые протоколы
                protocols_text = ", ".join([p.upper() for p in server.supported_protocols])
                
                text += (
                    f"{load_icon} **{server.name}**\n"
                    f"   📍 {server.city}\n"
                    f"   🔐 {protocols_text}\n"
                    f"   👥 {server.current_users}/{server.max_users}\n\n"
                )
        
        text += (
            "ℹ️ **Обозначения:**\n"
            "🟢 Низкая нагрузка\n"
            "🟡 Средняя нагрузка\n"
            "🔴 Высокая нагрузка\n\n"
            "Выберите сервер для подробной информации:"
        )
        
        keyboard = create_servers_keyboard(servers)
        
        await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
        await state.set_state(ServerSelectionStates.selecting_server)
        
    except Exception as e:
        logger.error(f"Error in cmd_servers: {e}")
        await message.answer("❌ Произошла ошибка при загрузке серверов")


@router.callback_query(F.data.startswith("server_info:"))
async def show_server_info(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    """Показать подробную информацию о сервере"""
    try:
        server_id = int(callback.data.split(":")[1])
        
        server_service = ServerService(session)
        server = await server_service.get_server_by_id(server_id)
        
        if not server:
            await callback.answer("❌ Сервер не найден", show_alert=True)
            return
        
        # Получаем детальную информацию
        load = await server_service._calculate_server_load(server)
        health = await server_service.check_server_health(server_id)
        
        # Формируем информацию о сервере
        text = f"🌍 **Сервер {server.name}**\n\n"
        
        # Основная информация
        text += f"📍 **Расположение:** {server.city}, {server.country}\n"
        text += f"🔗 **IP:** `{server.ip_address}`\n"
        if server.domain:
            text += f"🌐 **Домен:** `{server.domain}`\n"
        
        # Статус
        status_icon = "🟢" if health.get("healthy", False) else "🔴"
        status_text = "Доступен" if health.get("healthy", False) else "Недоступен"
        text += f"\n📊 **Статус:** {status_icon} {status_text}\n"
        
        # Нагрузка
        load_percentage = load * 100
        load_icon = "🟢" if load_percentage < 70 else "🟡" if load_percentage < 90 else "🔴"
        text += f"⚡ **Нагрузка:** {load_icon} {load_percentage:.1f}%\n"
        text += f"👥 **Пользователи:** {server.current_users}/{server.max_users}\n"
        
        # Технические характеристики
        text += f"\n💻 **Технические характеристики:**\n"
        text += f"   🖥 CPU: {server.cpu_usage:.1f}%\n"
        text += f"   💾 RAM: {server.memory_usage:.1f}%\n"
        text += f"   💿 Диск: {server.disk_usage:.1f}%\n"
        
        # Поддерживаемые протоколы
        text += f"\n🔐 **Поддерживаемые протоколы:**\n"
        for protocol in server.supported_protocols:
            protocol_icon = "✅" if protocol in ["vless", "vmess"] else "🔧"
            text += f"   {protocol_icon} {protocol.upper()}\n"
        
        # Рекомендации
        if server.country_code in ["NL", "DE", "FI"]:
            text += f"\n⭐ **Рекомендуется для России**\n"
        
        if server.primary_protocol == VpnProtocol.VLESS:
            text += f"🚀 **Оптимизирован для VLESS**\n"
        
        keyboard = create_server_details_keyboard(server_id, server.supported_protocols)
        
        await callback.message.edit_text(
            text, 
            reply_markup=keyboard, 
            parse_mode="Markdown"
        )
        
        # Сохраняем выбранный сервер в состоянии
        await state.update_data(selected_server_id=server_id)
        await state.set_state(ServerSelectionStates.viewing_server)
        
    except Exception as e:
        logger.error(f"Error in show_server_info: {e}")
        await callback.answer("❌ Ошибка загрузки информации о сервере", show_alert=True)


@router.callback_query(F.data.startswith("test_server:"))
async def test_server_connection(callback: CallbackQuery, session: AsyncSession):
    """Тестировать подключение к серверу"""
    try:
        server_id = int(callback.data.split(":")[1])
        
        await callback.answer("🔄 Тестируем подключение...", show_alert=False)
        
        server_service = ServerService(session)
        health_status = await server_service.check_server_health(server_id)
        
        if health_status.get("healthy", False):
            overall_status = health_status.get("overall_status", "unknown")
            
            if overall_status == "healthy":
                text = "✅ Сервер работает отлично!"
            elif overall_status == "degraded":
                text = "⚠️ Сервер работает с предупреждениями"
            else:
                text = "❌ Сервер недоступен"
            
            # Добавляем детали проверки
            checks = health_status.get("checks", {})
            if checks:
                text += "\n\n📋 **Результаты проверки:**\n"
                for check_name, check_result in checks.items():
                    status_icon = "✅" if check_result.get("status") == "pass" else "⚠️" if check_result.get("status") == "warn" else "❌"
                    text += f"{status_icon} {check_result.get('message', check_name)}\n"
        else:
            text = "❌ Сервер недоступен или не отвечает"
        
        await callback.answer(text, show_alert=True)
        
    except Exception as e:
        logger.error(f"Error in test_server_connection: {e}")
        await callback.answer("❌ Ошибка тестирования", show_alert=True)


@router.callback_query(F.data.startswith("select_protocol:"))
async def select_protocol_for_server(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    """Выбрать протокол для сервера"""
    try:
        server_id = int(callback.data.split(":")[1])
        
        server_service = ServerService(session)
        server = await server_service.get_server_by_id(server_id)
        
        if not server:
            await callback.answer("❌ Сервер не найден", show_alert=True)
            return
        
        text = f"🔐 **Выбор протокола для {server.name}**\n\n"
        text += f"📍 {server.city}, {server.country}\n\n"
        
        # Информация о протоколах
        protocol_info = {
            "vless": {
                "name": "VLESS",
                "description": "Современный протокол с поддержкой Reality",
                "icon": "🚀",
                "recommended": True
            },
            "vmess": {
                "name": "VMess", 
                "description": "Классический протокол V2Ray",
                "icon": "🔧",
                "recommended": False
            },
            "trojan": {
                "name": "Trojan",
                "description": "Протокол маскировки под HTTPS",
                "icon": "🛡",
                "recommended": False
            },
            "openvpn": {
                "name": "OpenVPN",
                "description": "Проверенный временем протокол",
                "icon": "🔒",
                "recommended": False
            },
            "wireguard": {
                "name": "WireGuard",
                "description": "Быстрый современный протокол",
                "icon": "⚡",
                "recommended": False
            }
        }
        
        text += "Доступные протоколы:\n\n"
        
        for protocol_str in server.supported_protocols:
            info = protocol_info.get(protocol_str, {})
            icon = info.get("icon", "🔧")
            name = info.get("name", protocol_str.upper())
            description = info.get("description", "")
            recommended = info.get("recommended", False)
            
            text += f"{icon} **{name}**"
            if recommended:
                text += " ⭐ *Рекомендуется*"
            text += f"\n   {description}\n\n"
        
        # Рекомендация для российских пользователей
        user_service = UserService(session)
        user = await user_service.get_user_by_telegram_id(callback.from_user.id)
        
        if user and user.country_code in ["RU", "BY", "KZ"]:
            text += "🇷🇺 **Для пользователей из России рекомендуется VLESS** - "
            text += "лучше всего обходит блокировки\n\n"
        
        keyboard = create_protocol_selection_keyboard(server_id, server.supported_protocols)
        
        await callback.message.edit_text(
            text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        
        await state.set_state(ServerSelectionStates.selecting_protocol)
        
    except Exception as e:
        logger.error(f"Error in select_protocol_for_server: {e}")
        await callback.answer("❌ Ошибка выбора протокола", show_alert=True)


@router.callback_query(F.data.startswith("create_config:"))
async def create_config_for_server(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    """Создать конфигурацию для выбранного сервера и протокола"""
    try:
        # Парсим данные: create_config:server_id:protocol
        data_parts = callback.data.split(":")
        server_id = int(data_parts[1])
        protocol_str = data_parts[2]
        
        await callback.answer("🔄 Создаем конфигурацию...", show_alert=False)
        
        user_service = UserService(session)
        user = await user_service.get_user_by_telegram_id(callback.from_user.id)
        
        if not user:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return
        
        # Проверяем активную подписку
        subscription_service = SubscriptionService(session)
        active_subscription = await subscription_service.get_active_subscription(user.id)
        
        if not active_subscription:
            text = (
                "❌ **Нет активной подписки**\n\n"
                "Для создания VPN конфигурации необходима активная подписка.\n\n"
                "Перейдите в раздел 'Подписки' для оформления."
            )
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📦 Оформить подписку", callback_data="subscriptions")],
                [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_servers")]
            ])
            
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
            return
        
        # Проверяем статус подписки
        if active_subscription.status != SubscriptionStatus.ACTIVE:
            status_text = {
                SubscriptionStatus.EXPIRED: "истекла",
                SubscriptionStatus.SUSPENDED: "приостановлена", 
                SubscriptionStatus.PENDING: "ожидает активации"
            }.get(active_subscription.status, "неактивна")
            
            text = f"❌ **Подписка {status_text}**\n\n"
            
            if active_subscription.status == SubscriptionStatus.EXPIRED:
                text += "Продлите подписку для продолжения использования VPN."
            elif active_subscription.status == SubscriptionStatus.PENDING:
                text += "Дождитесь активации подписки после оплаты."
            else:
                text += "Обратитесь в поддержку для разрешения проблемы."
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📦 Мои подписки", callback_data="my_subscriptions")],
                [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_servers")]
            ])
            
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
            return
        
        try:
            # Создаем VPN конфигурацию через VPN Factory
            from core.services.vpn.vpn_factory import VpnServiceManager
            
            protocol = VpnProtocol(protocol_str)
            server_service = ServerService(session)
            server = await server_service.get_server_by_id(server_id)
            
            vpn_manager = VpnServiceManager(session)
            
            # Создаем конфигурацию
            config = await vpn_manager.create_config_for_best_protocol(
                server=server,
                subscription_id=active_subscription.id,
                preferred_protocol=protocol,
                client_name=f"{user.first_name or user.username}_{protocol_str}"
            )
            
            if config:
                text = (
                    "✅ **Конфигурация создана!**\n\n"
                    f"🌍 **Сервер:** {server.name}\n"
                    f"📍 **Расположение:** {server.city}, {server.country}\n"
                    f"🔐 **Протокол:** {protocol_str.upper()}\n"
                    f"🆔 **ID конфигурации:** `{config.client_id}`\n\n"
                    "Конфигурация готова к использованию. "
                    "Вы можете скачать её в разделе 'Мои подписки'."
                )
                
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📱 Скачать конфигурацию", callback_data=f"download_config:{config.id}")],
                    [InlineKeyboardButton(text="📦 Мои подписки", callback_data="my_subscriptions")],
                    [InlineKeyboardButton(text="🌍 Выбрать другой сервер", callback_data="back_to_servers")]
                ])
                
                # Логируем создание конфигурации
                await user_service.log_user_action(
                    user_id=user.id,
                    action="config_created_via_servers",
                    details={
                        "server_id": server_id,
                        "protocol": protocol_str,
                        "config_id": config.id
                    }
                )
                
            else:
                text = (
                    "❌ **Ошибка создания конфигурации**\n\n"
                    "Не удалось создать VPN конфигурацию. "
                    "Попробуйте другой протокол или обратитесь в поддержку."
                )
                
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔄 Попробовать снова", callback_data=f"select_protocol:{server_id}")],
                    [InlineKeyboardButton(text="🆘 Поддержка", callback_data="support")],
                    [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_servers")]
                ])
                
        except Exception as config_error:
            logger.error(f"Error creating VPN config: {config_error}")
            text = (
                "❌ **Техническая ошибка**\n\n"
                f"Произошла ошибка при создании конфигурации: {str(config_error)[:100]}\n\n"
                "Попробуйте позже или обратитесь в поддержку."
            )
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Попробовать снова", callback_data=f"select_protocol:{server_id}")],
                [InlineKeyboardButton(text="🆘 Поддержка", callback_data="support")],
                [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_servers")]
            ])
        
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        await state.clear()
        
    except Exception as e:
        logger.error(f"Error in create_config_for_server: {e}")
        await callback.answer("❌ Ошибка создания конфигурации", show_alert=True)


@router.callback_query(F.data == "back_to_servers")
async def back_to_servers(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    """Вернуться к списку серверов"""
    try:
        await state.clear()
        
        # Перенаправляем на команду серверов
        # Создаем фейковое сообщение для повторного использования логики
        fake_message = callback.message
        fake_message.from_user = callback.from_user
        
        await cmd_servers(fake_message, session, state)
        
    except Exception as e:
        logger.error(f"Error in back_to_servers: {e}")
        await callback.answer("❌ Ошибка возврата к серверам", show_alert=True)


@router.callback_query(F.data.startswith("server_stats:"))
async def show_server_statistics(callback: CallbackQuery, session: AsyncSession):
    """Показать статистику сервера"""
    try:
        server_id = int(callback.data.split(":")[1])
        
        server_service = ServerService(session)
        stats = await server_service.get_server_statistics(server_id, days=7)
        
        if not stats:
            await callback.answer("❌ Статистика недоступна", show_alert=True)
            return
        
        server = await server_service.get_server_by_id(server_id)
        
        text = f"📊 **Статистика сервера {server.name}**\n\n"
        
        # Средние показатели за неделю
        averages = stats.get("averages", {})
        text += f"📈 **Средние показатели (7 дней):**\n"
        text += f"   🖥 CPU: {averages.get('cpu_usage', 0):.1f}%\n"
        text += f"   💾 RAM: {averages.get('memory_usage', 0):.1f}%\n"
        text += f"   💿 Диск: {averages.get('disk_usage', 0):.1f}%\n"
        text += f"   👥 Подключений: {averages.get('connections', 0):.1f}\n\n"
        
        # Пиковые значения
        text += f"🔥 **Пиковые значения:**\n"
        text += f"   👥 Максимум подключений: {stats.get('peak_connections', 0)}\n"
        text += f"   🖥 Максимум CPU: {stats.get('peak_cpu', 0):.1f}%\n\n"
        
        # Общая информация
        text += f"📋 **Общая информация:**\n"
        text += f"   📊 Точек данных: {stats.get('total_data_points', 0)}\n"
        text += f"   📅 Период: {stats.get('period_days', 0)} дней\n"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Обновить", callback_data=f"server_stats:{server_id}")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data=f"server_info:{server_id}")]
        ])
        
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Error in show_server_statistics: {e}")
        await callback.answer("❌ Ошибка загрузки статистики", show_alert=True)


@router.callback_query(F.data.startswith("download_config:"))
async def download_config_quick(callback: CallbackQuery, session: AsyncSession):
    """Быстрое скачивание конфигурации"""
    try:
        config_id = int(callback.data.split(":")[1])
        
        # Перенаправляем на обработчик конфигураций
        from bots.client.handlers.configs import download_config_file
        
        # Изменяем callback data для соответствия обработчику конфигураций
        callback.data = f"config_download:{config_id}"
        
        await download_config_file(callback, session)
        
    except Exception as e:
        logger.error(f"Error in download_config_quick: {e}")
        await callback.answer("❌ Ошибка скачивания конфигурации", show_alert=True)


@router.message(F.text.lower().contains("сервер"))
async def handle_server_mention(message: Message, session: AsyncSession, state: FSMContext):
    """Обработка упоминания серверов в сообщениях"""
    try:
        # Если пользователь пишет что-то про серверы, показываем быструю помощь
        text = (
            "🌍 **Управление серверами**\n\n"
            "Доступные команды:\n"
            "• /servers - Список всех серверов\n"
            "• Выбор сервера и протокола\n"
            "• Создание VPN конфигураций\n"
            "• Тестирование подключения\n\n"
            "Нажмите кнопку ниже для просмотра серверов:"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🌍 Показать серверы", callback_data="show_servers")],
            [InlineKeyboardButton(text="📦 Мои подписки", callback_data="my_subscriptions")]
        ])
        
        await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Error in handle_server_mention: {e}")


@router.callback_query(F.data == "show_servers")
async def show_servers_callback(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    """Показать серверы через callback"""
    try:
        # Создаем фейковое сообщение для повторного использования логики
        fake_message = callback.message
        fake_message.from_user = callback.from_user
        
        await cmd_servers(fake_message, session, state)
        
    except Exception as e:
        logger.error(f"Error in show_servers_callback: {e}")
        await callback.answer("❌ Ошибка загрузки серверов", show_alert=True)


# Вспомогательные функции для форматирования

def format_server_card(server: Server) -> str:
    """Форматировать карточку сервера"""
    load_percentage = (server.current_users / server.max_users * 100) if server.max_users > 0 else 0
    load_icon = "🟢" if load_percentage < 70 else "🟡" if load_percentage < 90 else "🔴"
    
    protocols = ", ".join([p.upper() for p in server.supported_protocols])
    
    return (
        f"{load_icon} **{server.name}**\n"
        f"📍 {server.city}, {server.country}\n"
        f"🔐 {protocols}\n"
        f"👥 {server.current_users}/{server.max_users} ({load_percentage:.0f}%)\n"
    )


def get_protocol_recommendation(user_country: str, server_protocols: List[str]) -> str:
    """Получить рекомендацию по протоколу"""
    # Для российских пользователей приоритет VLESS
    if user_country in ["RU", "BY", "KZ"]:
        if "vless" in server_protocols:
            return "vless"
        elif "vmess" in server_protocols:
            return "vmess"
        elif "trojan" in server_protocols:
            return "trojan"
    
    # Для остальных - по порядку приоритета
    protocol_priority = ["vless", "wireguard", "openvpn", "vmess", "trojan"]
    
    for protocol in protocol_priority:
        if protocol in server_protocols:
            return protocol
    
    return server_protocols[0] if server_protocols else "vless"


def get_country_flag(country_code: str) -> str:
    """Получить флаг страны по коду"""
    flags = {
        "US": "🇺🇸", "DE": "🇩🇪", "NL": "🇳🇱", "GB": "🇬🇧",
        "FR": "🇫🇷", "JP": "🇯🇵", "SG": "🇸🇬", "CA": "🇨🇦",
        "AU": "🇦🇺", "FI": "🇫🇮", "SE": "🇸🇪", "NO": "🇳🇴",
        "CH": "🇨🇭", "AT": "🇦🇹", "IT": "🇮🇹", "ES": "🇪🇸",
        "LV": "🇱🇻", "EE": "🇪🇪", "LT": "🇱🇹", "PL": "🇵🇱"
    }
    return flags.get(country_code.upper(), "🌍")


async def suggest_best_server(session: AsyncSession, user_id: int) -> Optional[Server]:
    """Предложить лучший сервер для пользователя"""
    try:
        user_service = UserService(session)
        server_service = ServerService(session)
        
        user = await user_service.get_user_by_id(user_id)
        if not user:
            return None
        
        return await server_service.get_best_server_for_user(user)
        
    except Exception as e:
        logger.error(f"Error suggesting best server: {e}")
        return None


# Экспорт роутера
__all__ = ["router"]