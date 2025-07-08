"""
Обработчик команды /start и начальных взаимодействий
"""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from loguru import logger

from bots.client.states.client_states import RegistrationStates, MainMenuStates
from bots.client.keyboards.inline import get_main_menu_keyboard, get_registration_keyboard
from bots.client.keyboards.reply import get_language_keyboard
from bots.shared.utils.formatters import format_user_greeting, format_welcome_message
from core.services.user_service import UserService
from core.services.subscription_service import SubscriptionService
from config.settings import settings

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, session, **kwargs):
    """Обработчик команды /start"""
    try:
        user_service = UserService(session)
        
        # Получаем или создаем пользователя
        user = await user_service.get_or_create_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
            language_code=message.from_user.language_code
        )
        
        # Проверяем, новый ли пользователь
        if not user.last_activity:
            # Новый пользователь - показываем приветствие
            await show_welcome_message(message, user, state)
        else:
            # Существующий пользователь - главное меню
            await show_main_menu(message, user, state)
        
        # Логируем активность
        await user_service.log_user_action(
            user_id=user.id,
            action="start_command",
            details={"first_visit": not user.last_activity}
        )
        
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        await message.answer(
            "❌ Произошла ошибка при запуске. Попробуйте позже.",
            reply_markup=None
        )


async def show_welcome_message(message: Message, user, state: FSMContext):
    """Показать приветственное сообщение для нового пользователя"""
    try:
        welcome_text = format_welcome_message(user)
        
        # Показываем приветствие
        await message.answer(
            text=welcome_text,
            reply_markup=get_registration_keyboard()
        )
        
        # Устанавливаем состояние регистрации
        await state.set_state(RegistrationStates.waiting_for_agreement)
        
    except Exception as e:
        logger.error(f"Error showing welcome message: {e}")
        await message.answer("❌ Ошибка при загрузке приветствия")


async def show_main_menu(message: Message, user, state: FSMContext):
    """Показать главное меню"""
    try:
        subscription_service = SubscriptionService(message.bot.session)
        
        # Проверяем активную подписку
        active_subscription = await subscription_service.get_active_subscription(user.id)
        
        # Формируем приветствие
        greeting = format_user_greeting(user, active_subscription)
        
        # Показываем главное меню
        await message.answer(
            text=greeting,
            reply_markup=get_main_menu_keyboard(user, active_subscription)
        )
        
        # Устанавливаем состояние главного меню
        await state.set_state(MainMenuStates.main_menu)
        
    except Exception as e:
        logger.error(f"Error showing main menu: {e}")
        await message.answer("❌ Ошибка при загрузке главного меню")


@router.callback_query(F.data == "registration_agree")
async def registration_agree(callback: CallbackQuery, state: FSMContext, session, **kwargs):
    """Пользователь согласился с условиями"""
    try:
        await callback.answer()
        
        user_service = UserService(session)
        user = await user_service.get_user_by_telegram_id(callback.from_user.id)
        
        # Логируем согласие
        await user_service.log_user_action(
            user_id=user.id,
            action="terms_accepted",
            details={"accepted_at": "registration"}
        )
        
        # Переходим к выбору языка
        await callback.message.edit_text(
            "🌍 <b>Выберите язык / Choose language:</b>",
            reply_markup=get_language_keyboard()
        )
        
        await state.set_state(RegistrationStates.waiting_for_language)
        
    except Exception as e:
        logger.error(f"Error in registration agree: {e}")
        await callback.answer("❌ Ошибка при регистрации", show_alert=True)


@router.callback_query(F.data.startswith("lang_"))
async def set_language(callback: CallbackQuery, state: FSMContext, session, **kwargs):
    """Установка языка пользователя"""
    try:
        await callback.answer()
        
        language = callback.data.split("_")[1]
        
        user_service = UserService(session)
        user = await user_service.get_user_by_telegram_id(callback.from_user.id)
        
        # Обновляем язык пользователя
        await user_service.update_user_preferences(
            user_id=user.id,
            language_code=language
        )
        
        # Показываем сообщение о завершении регистрации
        complete_text = (
            "✅ <b>Регистрация завершена!</b>\n\n"
            "Добро пожаловать в VPN Bot! 🚀\n\n"
            "Теперь вы можете:\n"
            "🔸 Выбрать тарифный план\n"
            "🔸 Получить VPN конфигурацию\n"
            "🔸 Подключиться к серверам по всему миру\n\n"
            "Нажмите кнопку ниже, чтобы начать:"
        )
        
        from bots.client.keyboards.inline import get_start_journey_keyboard
        
        await callback.message.edit_text(
            text=complete_text,
            reply_markup=get_start_journey_keyboard()
        )
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"Error setting language: {e}")
        await callback.answer("❌ Ошибка при установке языка", show_alert=True)


@router.callback_query(F.data == "start_journey")
async def start_journey(callback: CallbackQuery, state: FSMContext, session, **kwargs):
    """Начать использование бота"""
    try:
        await callback.answer()
        
        user_service = UserService(session)
        user = await user_service.get_user_by_telegram_id(callback.from_user.id)
        
        # Переходим к главному меню
        await show_main_menu(callback.message, user, state)
        
        # Логируем начало использования
        await user_service.log_user_action(
            user_id=user.id,
            action="journey_started"
        )
        
    except Exception as e:
        logger.error(f"Error starting journey: {e}")
        await callback.answer("❌ Ошибка при переходе", show_alert=True)


@router.message(Command("help"))
async def cmd_help(message: Message, **kwargs):
    """Обработчик команды /help"""
    try:
        help_text = (
            "📋 <b>Справка по командам:</b>\n\n"
            
            "🚀 /start - Главное меню\n"
            "👤 /profile - Мой профиль\n"
            "📦 /subscription - Подписки\n"
            "🌍 /servers - Серверы\n"
            "⚙️ /configs - Конфигурации\n"
            "🎧 /support - Поддержка\n\n"
            
            "❓ <b>Как пользоваться ботом:</b>\n\n"
            "1️⃣ Выберите тарифный план\n"
            "2️⃣ Оплатите подписку\n"
            "3️⃣ Скачайте конфигурацию\n"
            "4️⃣ Настройте VPN в приложении\n\n"
            
            "🔗 <b>Поддерживаемые протоколы:</b>\n"
            "• VLESS (рекомендуется)\n"
            "• OpenVPN\n"
            "• WireGuard\n\n"
            
            "💬 Если у вас вопросы - обращайтесь в поддержку!"
        )
        
        await message.answer(
            text=help_text,
            reply_markup=get_main_menu_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Error in help command: {e}")
        await message.answer("❌ Ошибка при загрузке справки")


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext, session, **kwargs):
    """Обработчик команды /menu - возврат в главное меню"""
    try:
        user_service = UserService(session)
        user = await user_service.get_user_by_telegram_id(message.from_user.id)
        
        if user:
            await show_main_menu(message, user, state)
        else:
            await cmd_start(message, state, session, **kwargs)
            
    except Exception as e:
        logger.error(f"Error in menu command: {e}")
        await message.answer("❌ Ошибка при загрузке меню")


@router.callback_query(F.data == "main_menu")
async def back_to_main_menu(callback: CallbackQuery, state: FSMContext, session, **kwargs):
    """Возврат в главное меню через callback"""
    try:
        await callback.answer()
        
        user_service = UserService(session)
        user = await user_service.get_user_by_telegram_id(callback.from_user.id)
        
        if user:
            # Обновляем сообщение с главным меню
            subscription_service = SubscriptionService(session)
            active_subscription = await subscription_service.get_active_subscription(user.id)
            
            greeting = format_user_greeting(user, active_subscription)
            
            await callback.message.edit_text(
                text=greeting,
                reply_markup=get_main_menu_keyboard(user, active_subscription)
            )
            
            await state.set_state(MainMenuStates.main_menu)
        
    except Exception as e:
        logger.error(f"Error returning to main menu: {e}")
        await callback.answer("❌ Ошибка при переходе", show_alert=True)