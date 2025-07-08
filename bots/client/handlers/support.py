"""
Handlers для системы поддержки в Client Bot
"""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict, Any, Optional
from datetime import datetime
from loguru import logger

from core.database.models import SupportTicket, TicketStatus, TicketPriority, User
from core.services.support_service import SupportService
from core.services.user_service import UserService
from bots.client.keyboards.inline import (
    create_support_menu_keyboard,
    create_ticket_categories_keyboard,
    create_ticket_actions_keyboard,
    create_faq_keyboard
)
from bots.client.states.client_states import SupportStates


router = Router(name="support")


@router.message(Command("support"))
async def cmd_support(message: Message, session: AsyncSession, state: FSMContext):
    """Главное меню поддержки"""
    try:
        await state.clear()
        
        user_service = UserService(session)
        user = await user_service.get_user_by_telegram_id(message.from_user.id)
        
        if not user:
            await message.answer("❌ Пользователь не найден. Используйте /start")
            return
        
        # Получаем количество открытых тикетов
        support_service = SupportService(session)
        open_tickets = await support_service.get_user_tickets(
            user.id, 
            status_filter=[TicketStatus.OPEN, TicketStatus.IN_PROGRESS, TicketStatus.WAITING_CLIENT]
        )
        
        text = "🆘 **Центр поддержки**\n\n"
        
        if open_tickets:
            text += f"📋 У вас {len(open_tickets)} открытых обращений\n\n"
        
        text += (
            "Мы готовы помочь вам с любыми вопросами:\n\n"
            "🔍 **Часто задаваемые вопросы** - быстрые ответы\n"
            "💬 **Новое обращение** - персональная помощь\n"
            "📋 **Мои обращения** - история вопросов\n"
            "📞 **Контакты** - альтернативные способы связи\n\n"
            "⏰ **Время ответа:** обычно в течение 1-3 часов\n"
            "🕐 **Режим работы:** 24/7"
        )
        
        keyboard = create_support_menu_keyboard(len(open_tickets))
        
        await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Error in cmd_support: {e}")
        await message.answer("❌ Произошла ошибка при загрузке поддержки")


@router.callback_query(F.data == "support_faq")
async def show_faq(callback: CallbackQuery, session: AsyncSession):
    """Показать часто задаваемые вопросы"""
    try:
        text = "🔍 **Часто задаваемые вопросы**\n\n"
        text += "Выберите категорию вопроса:"
        
        keyboard = create_faq_keyboard()
        
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Error in show_faq: {e}")
        await callback.answer("❌ Ошибка загрузки FAQ", show_alert=True)


@router.callback_query(F.data.startswith("faq_"))
async def show_faq_category(callback: CallbackQuery):
    """Показать FAQ по категории"""
    try:
        category = callback.data.split("_", 1)[1]
        
        faq_data = {
            "setup": {
                "title": "🔧 Настройка и подключение",
                "items": [
                    {
                        "q": "Как настроить VPN на Android?",
                        "a": (
                            "1. Скачайте приложение v2rayNG из Google Play\n"
                            "2. Нажмите + в правом верхнем углу\n"
                            "3. Выберите 'Импорт конфигурации из QR-кода'\n"
                            "4. Отсканируйте QR-код из бота\n"
                            "5. Нажмите на конфигурацию и выберите 'Подключить'"
                        )
                    },
                    {
                        "q": "Как настроить VPN на iPhone?",
                        "a": (
                            "1. Скачайте Shadowrocket из App Store\n"
                            "2. Откройте приложение\n"
                            "3. Нажмите + в правом верхнем углу\n"
                            "4. Выберите 'QR Code'\n"
                            "5. Отсканируйте QR-код из бота\n"
                            "6. Нажмите на переключатель для подключения"
                        )
                    },
                    {
                        "q": "Как настроить VPN на Windows?",
                        "a": (
                            "1. Скачайте v2rayN с GitHub\n"
                            "2. Запустите программу\n"
                            "3. Нажмите Ctrl+V для вставки ссылки конфигурации\n"
                            "4. Выберите сервер в списке\n"
                            "5. Нажмите Enter для подключения"
                        )
                    }
                ]
            },
            "problems": {
                "title": "🚨 Проблемы с подключением",
                "items": [
                    {
                        "q": "VPN не подключается",
                        "a": (
                            "Попробуйте следующее:\n"
                            "1. Проверьте интернет-соединение\n"
                            "2. Попробуйте другой сервер\n"
                            "3. Перезагрузите приложение\n"
                            "4. Проверьте срок действия подписки\n"
                            "5. Обратитесь в поддержку, если проблема сохраняется"
                        )
                    },
                    {
                        "q": "Медленная скорость",
                        "a": (
                            "Для улучшения скорости:\n"
                            "1. Выберите ближайший сервер\n"
                            "2. Попробуйте другой протокол (VLESS рекомендуется)\n"
                            "3. Проверьте загрузку сервера\n"
                            "4. Убедитесь, что интернет провайдер не ограничивает скорость"
                        )
                    },
                    {
                        "q": "Часто отключается",
                        "a": (
                            "Если VPN часто отключается:\n"
                            "1. Включите автоподключение в настройках\n"
                            "2. Проверьте настройки энергосбережения\n"
                            "3. Попробуйте протокол с keep-alive\n"
                            "4. Обновите приложение до последней версии"
                        )
                    }
                ]
            },
            "account": {
                "title": "👤 Аккаунт и подписка",
                "items": [
                    {
                        "q": "Как продлить подписку?",
                        "a": (
                            "Для продления подписки:\n"
                            "1. Перейдите в раздел 'Подписки'\n"
                            "2. Выберите нужный тариф\n"
                            "3. Оплатите удобным способом\n"
                            "4. Подписка продлится автоматически"
                        )
                    },
                    {
                        "q": "Как изменить тариф?",
                        "a": (
                            "Изменение тарифа:\n"
                            "1. Свяжит