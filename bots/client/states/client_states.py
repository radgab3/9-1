"""
Состояния (States) для клиентского бота
"""

from aiogram.fsm.state import State, StatesGroup


class RegistrationStates(StatesGroup):
    """Состояния регистрации пользователя"""
    waiting_for_name = State()
    waiting_for_contact = State()
    waiting_for_language = State()
    waiting_for_agreement = State()


class SubscriptionStates(StatesGroup):
    """Состояния работы с подписками"""
    selecting_plan = State()
    selecting_server = State()
    selecting_protocol = State()
    confirming_purchase = State()
    waiting_for_payment = State()


class ProfileStates(StatesGroup):
    """Состояния редактирования профиля"""
    editing_name = State()
    editing_language = State()
    changing_protocol = State()
    viewing_stats = State()


class ServerStates(StatesGroup):
    """Состояния работы с серверами"""
    viewing_list = State()
    viewing_details = State()
    testing_connection = State()
    changing_server = State()


class ConfigStates(StatesGroup):
    """Состояния работы с конфигурациями"""
    viewing_configs = State()
    downloading_config = State()
    viewing_qr_code = State()
    sharing_config = State()
    regenerating_config = State()


class SupportStates(StatesGroup):
    """Состояния работы с поддержкой"""
    creating_ticket = State()
    waiting_for_subject = State()
    waiting_for_description = State()
    waiting_for_message = State()
    viewing_tickets = State()
    ticket_conversation = State()


class PaymentStates(StatesGroup):
    """Состояния платежей"""
    selecting_method = State()
    waiting_for_payment = State()
    confirming_payment = State()
    payment_success = State()
    payment_failed = State()


class SettingsStates(StatesGroup):
    """Состояния настроек"""
    main_menu = State()
    language_settings = State()
    notification_settings = State()
    privacy_settings = State()
    protocol_settings = State()


class ReferralStates(StatesGroup):
    """Состояния реферальной системы"""
    viewing_stats = State()
    inviting_friends = State()
    claiming_bonus = State()


class FeedbackStates(StatesGroup):
    """Состояния обратной связи"""
    waiting_for_rating = State()
    waiting_for_review = State()
    waiting_for_suggestion = State()


class TrialStates(StatesGroup):
    """Состояния пробного периода"""
    requesting_trial = State()
    selecting_trial_server = State()
    activating_trial = State()


class MainMenuStates(StatesGroup):
    """Основные состояния меню"""
    main_menu = State()
    subscriptions_menu = State()
    servers_menu = State()
    profile_menu = State()
    support_menu = State()
    settings_menu = State()