"""
Inline клавиатуры для клиентского бота
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import Optional, List


def get_main_menu_keyboard(user=None, active_subscription=None) -> InlineKeyboardMarkup:
    """Главное меню"""
    buttons = []
    
    if active_subscription:
        # У пользователя есть активная подписка
        buttons.extend([
            [InlineKeyboardButton(text="⚙️ Мои конфигурации", callback_data="my_configs")],
            [InlineKeyboardButton(text="📊 Статистика", callback_data="my_stats")],
            [
                InlineKeyboardButton(text="📦 Подписки", callback_data="subscriptions"),
                InlineKeyboardButton(text="🌍 Серверы", callback_data="servers")
            ]
        ])
    else:
        # Нет активной подписки
        buttons.extend([
            [InlineKeyboardButton(text="🆓 Пробный период", callback_data="trial_period")],
            [InlineKeyboardButton(text="💎 Купить подписку", callback_data="buy_subscription")],
            [InlineKeyboardButton(text="🌍 Посмотреть серверы", callback_data="view_servers")]
        ])
    
    # Общие кнопки
    buttons.extend([
        [
            InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
            InlineKeyboardButton(text="🎧 Поддержка", callback_data="support")
        ],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")]
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_registration_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для регистрации"""
    buttons = [
        [InlineKeyboardButton(text="✅ Принимаю условия", callback_data="registration_agree")],
        [InlineKeyboardButton(text="📋 Читать условия", callback_data="view_terms")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_language_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора языка"""
    buttons = [
        [
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru"),
            InlineKeyboardButton(text="🇺🇸 English", callback_data="lang_en")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_start_journey_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для начала использования"""
    buttons = [
        [InlineKeyboardButton(text="🚀 Начать!", callback_data="start_journey")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_subscription_plans_keyboard(plans: List) -> InlineKeyboardMarkup:
    """Клавиатура тарифных планов"""
    buttons = []
    
    for plan in plans:
        emoji = "⭐" if plan.is_popular else "📦"
        text = f"{emoji} {plan.name} - {plan.price} {plan.currency}"
        buttons.append([InlineKeyboardButton(
            text=text, 
            callback_data=f"plan_{plan.id}"
        )])
    
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_servers_keyboard(servers: List, selected_server_id: Optional[int] = None) -> InlineKeyboardMarkup:
    """Клавиатура выбора серверов"""
    buttons = []
    
    for server in servers:
        emoji = "✅" if server.id == selected_server_id else "🌍"
        load_percent = (server.current_users / server.max_users) * 100
        load_emoji = "🟢" if load_percent < 50 else "🟡" if load_percent < 80 else "🔴"
        
        text = f"{emoji} {server.country} {server.city} {load_emoji}"
        buttons.append([InlineKeyboardButton(
            text=text,
            callback_data=f"server_{server.id}"
        )])
    
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def create_servers_keyboard(servers: List, page: int = 1, per_page: int = 5) -> InlineKeyboardMarkup:
    """Создать клавиатуру серверов с пагинацией"""
    buttons = []
    
    # Пагинация серверов
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    page_servers = servers[start_idx:end_idx]
    
    for server in page_servers:
        # Определяем статус сервера
        load_percent = (server.current_users / server.max_users) * 100 if server.max_users > 0 else 0
        if load_percent < 50:
            status_emoji = "🟢"
        elif load_percent < 80:
            status_emoji = "🟡"
        else:
            status_emoji = "🔴"
        
        # Определяем доступные протоколы
        protocols_text = ", ".join([p.upper() for p in server.supported_protocols[:2]])
        if len(server.supported_protocols) > 2:
            protocols_text += "..."
        
        text = f"{status_emoji} {server.country} - {server.city} ({protocols_text})"
        buttons.append([InlineKeyboardButton(
            text=text,
            callback_data=f"select_server_{server.id}"
        )])
    
    # Кнопки пагинации
    nav_buttons = []
    total_pages = (len(servers) + per_page - 1) // per_page
    
    if page > 1:
        nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"servers_page_{page-1}"))
    
    if total_pages > 1:
        nav_buttons.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="current_page"))
    
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"servers_page_{page+1}"))
    
    if nav_buttons:
        buttons.append(nav_buttons)
    
    buttons.append([InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def create_server_details_keyboard(server_id: int, available_protocols: List[str]) -> InlineKeyboardMarkup:
    """Клавиатура деталей сервера"""
    buttons = []
    
    # Кнопки выбора протокола
    if len(available_protocols) > 1:
        buttons.append([InlineKeyboardButton(
            text="🔧 Выбрать протокол",
            callback_data=f"select_protocol_{server_id}"
        )])
    
    # Кнопка создания конфигурации
    protocol = available_protocols[0] if available_protocols else "vless"
    buttons.append([InlineKeyboardButton(
        text="✅ Создать конфигурацию",
        callback_data=f"create_config_{server_id}_{protocol}"
    )])
    
    # Кнопка тестирования соединения
    buttons.append([InlineKeyboardButton(
        text="🔍 Проверить соединение",
        callback_data=f"test_server_{server_id}"
    )])
    
    buttons.append([InlineKeyboardButton(text="🔙 К серверам", callback_data="servers")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def create_protocol_selection_keyboard(server_id: int, protocols: List[str]) -> InlineKeyboardMarkup:
    """Клавиатура выбора протокола"""
    buttons = []
    
    protocol_info = {
        "vless": {"name": "VLESS", "emoji": "🔥", "desc": "Рекомендуется для России"},
        "openvpn": {"name": "OpenVPN", "emoji": "🛡️", "desc": "Универсальный"},
        "wireguard": {"name": "WireGuard", "emoji": "⚡", "desc": "Быстрый"}
    }
    
    for protocol in protocols:
        info = protocol_info.get(protocol, {"name": protocol.upper(), "emoji": "🔧", "desc": ""})
        text = f"{info['emoji']} {info['name']}"
        if info['desc']:
            text += f" - {info['desc']}"
        
        buttons.append([InlineKeyboardButton(
            text=text,
            callback_data=f"create_config_{server_id}_{protocol}"
        )])
    
    buttons.append([InlineKeyboardButton(text="🔙 К серверу", callback_data=f"server_details_{server_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_protocols_keyboard(protocols: List[str], selected: Optional[str] = None) -> InlineKeyboardMarkup:
    """Клавиатура выбора протоколов"""
    buttons = []
    
    protocol_emojis = {
        "vless": "🔥",
        "openvpn": "🛡️", 
        "wireguard": "⚡"
    }
    
    protocol_names = {
        "vless": "VLESS (рекомендуется)",
        "openvpn": "OpenVPN",
        "wireguard": "WireGuard"
    }
    
    for protocol in protocols:
        emoji = protocol_emojis.get(protocol, "🔧")
        name = protocol_names.get(protocol, protocol.upper())
        check = "✅ " if protocol == selected else ""
        
        buttons.append([InlineKeyboardButton(
            text=f"{check}{emoji} {name}",
            callback_data=f"protocol_{protocol}"
        )])
    
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="select_server")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_configs_keyboard(configs: List) -> InlineKeyboardMarkup:
    """Клавиатура конфигураций"""
    buttons = []
    
    for config in configs:
        protocol_emoji = {"vless": "🔥", "openvpn": "🛡️", "wireguard": "⚡"}.get(config.protocol.value, "🔧")
        status_emoji = "✅" if config.is_active else "❌"
        
        text = f"{status_emoji} {protocol_emoji} {config.server.name}"
        buttons.append([InlineKeyboardButton(
            text=text,
            callback_data=f"config_{config.id}"
        )])
    
    if not configs:
        buttons.append([InlineKeyboardButton(
            text="📦 Купить подписку",
            callback_data="buy_subscription"
        )])
    
    buttons.append([InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_config_actions_keyboard(config_id: int) -> InlineKeyboardMarkup:
    """Действия с конфигурацией"""
    buttons = [
        [
            InlineKeyboardButton(text="📱 Скачать", callback_data=f"download_{config_id}"),
            InlineKeyboardButton(text="📷 QR код", callback_data=f"qr_{config_id}")
        ],
        [
            InlineKeyboardButton(text="📋 Инструкция", callback_data=f"instruction_{config_id}"),
            InlineKeyboardButton(text="🔄 Обновить", callback_data=f"refresh_{config_id}")
        ],
        [InlineKeyboardButton(text="🔙 К конфигурациям", callback_data="my_configs")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_payment_methods_keyboard(plan_id: int) -> InlineKeyboardMarkup:
    """Способы оплаты"""
    buttons = [
        [InlineKeyboardButton(text="💳 Банковская карта", callback_data=f"pay_card_{plan_id}")],
        [InlineKeyboardButton(text="₿ Криптовалюта", callback_data=f"pay_crypto_{plan_id}")],
        [InlineKeyboardButton(text="🔙 Назад к планам", callback_data="subscriptions")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_payment_status_keyboard(payment_id: int) -> InlineKeyboardMarkup:
    """Клавиатура статуса платежа"""
    buttons = [
        [InlineKeyboardButton(text="🔄 Проверить статус", callback_data=f"check_payment_{payment_id}")],
        [InlineKeyboardButton(text="❌ Отменить платеж", callback_data=f"cancel_payment_{payment_id}")],
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def create_support_menu_keyboard() -> InlineKeyboardMarkup:
    """Меню поддержки"""
    buttons = [
        [InlineKeyboardButton(text="📝 Создать обращение", callback_data="create_ticket")],
        [InlineKeyboardButton(text="📋 Мои обращения", callback_data="my_tickets")],
        [
            InlineKeyboardButton(text="❓ FAQ", callback_data="show_faq"),
            InlineKeyboardButton(text="📖 Инструкции", callback_data="show_instructions")
        ],
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_support_keyboard() -> InlineKeyboardMarkup:
    """Меню поддержки (альтернативное название для совместимости)"""
    return create_support_menu_keyboard()


def create_ticket_categories_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура категорий обращений"""
    buttons = [
        [InlineKeyboardButton(text="🔧 Технические проблемы", callback_data="ticket_cat_technical")],
        [InlineKeyboardButton(text="💳 Вопросы по оплате", callback_data="ticket_cat_payment")],
        [InlineKeyboardButton(text="📱 Настройка приложений", callback_data="ticket_cat_setup")],
        [InlineKeyboardButton(text="🌍 Проблемы с серверами", callback_data="ticket_cat_servers")],
        [InlineKeyboardButton(text="❓ Общие вопросы", callback_data="ticket_cat_general")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="support")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def create_faq_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура FAQ"""
    buttons = [
        [InlineKeyboardButton(text="🚀 Как начать работу?", callback_data="faq_getting_started")],
        [InlineKeyboardButton(text="📱 Настройка на телефоне", callback_data="faq_mobile_setup")],
        [InlineKeyboardButton(text="💻 Настройка на компьютере", callback_data="faq_desktop_setup")],
        [InlineKeyboardButton(text="🐌 Медленное соединение", callback_data="faq_slow_connection")],
        [InlineKeyboardButton(text="🚫 Не подключается", callback_data="faq_connection_issues")],
        [InlineKeyboardButton(text="💰 Вопросы по тарифам", callback_data="faq_billing")],
        [InlineKeyboardButton(text="🔙 К поддержке", callback_data="support")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_trial_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура пробного периода"""
    buttons = [
        [InlineKeyboardButton(text="🆓 Активировать пробный период", callback_data="activate_trial")],
        [InlineKeyboardButton(text="📋 Условия пробного периода", callback_data="trial_terms")],
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_confirmation_keyboard(action: str, item_id: int) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения действия"""
    buttons = [
        [
            InlineKeyboardButton(text="✅ Да", callback_data=f"confirm_{action}_{item_id}"),
            InlineKeyboardButton(text="❌ Нет", callback_data=f"cancel_{action}")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_settings_keyboard() -> InlineKeyboardMarkup:
    """Меню настроек"""
    buttons = [
        [
            InlineKeyboardButton(text="🌍 Язык", callback_data="settings_language"),
            InlineKeyboardButton(text="🔔 Уведомления", callback_data="settings_notifications")
        ],
        [
            InlineKeyboardButton(text="🔐 Протокол по умолчанию", callback_data="settings_protocol")
        ],
        [
            InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_pagination_keyboard(
    current_page: int, 
    total_pages: int, 
    callback_prefix: str
) -> InlineKeyboardMarkup:
    """Клавиатура пагинации"""
    buttons = []
    
    if total_pages > 1:
        nav_buttons = []
        
        if current_page > 1:
            nav_buttons.append(InlineKeyboardButton(
                text="⬅️", 
                callback_data=f"{callback_prefix}_page_{current_page - 1}"
            ))
        
        nav_buttons.append(InlineKeyboardButton(
            text=f"{current_page}/{total_pages}",
            callback_data="current_page"
        ))
        
        if current_page < total_pages:
            nav_buttons.append(InlineKeyboardButton(
                text="➡️",
                callback_data=f"{callback_prefix}_page_{current_page + 1}"
            ))
        
        buttons.append(nav_buttons)
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_back_button(callback_data: str = "main_menu") -> InlineKeyboardMarkup:
    """Простая кнопка назад"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data=callback_data)]
    ]) callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_profile_keyboard() -> InlineKeyboardMarkup:
    """Меню профиля"""
    buttons = [
        [
            InlineKeyboardButton(text="📊 Статистика", callback_data="profile_stats"),
            InlineKeyboardButton(text="⚙️ Настройки", callback_data="profile_settings")
        ],
        [
            InlineKeyboardButton(text="🎁 Реферальная программа", callback_data="referral_program")
        ],
        [InlineKeyboardButton(text="🔙 Главное меню",