"""
Обработчик конфигураций для клиентского бота (доработанная версия)
"""

import os
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from loguru import logger

from bots.client.states.client_states import ConfigStates
from bots.client.keyboards.inline import (
    get_configs_keyboard, get_config_actions_keyboard, 
    get_back_button, get_protocols_keyboard
)
from core.services.subscription_service import SubscriptionService
from core.services.user_service import UserService
from core.services.vpn.vpn_factory import VpnServiceManager
from core.database.repositories import RepositoryManager

router = Router()


@router.callback_query(F.data == "my_configs")
async def show_my_configs(callback: CallbackQuery, state: FSMContext, session, **kwargs):
    """Показать конфигурации пользователя"""
    try:
        await callback.answer()
        
        user_service = UserService(session)
        user = await user_service.get_user_by_telegram_id(callback.from_user.id)
        
        repos = RepositoryManager(session)
        
        # Получаем активную подписку
        subscription_service = SubscriptionService(session)
        active_subscription = await subscription_service.get_active_subscription(user.id)
        
        if not active_subscription:
            text = (
                "❌ <b>У вас нет активной подписки</b>\n\n"
                "Для получения VPN конфигураций необходимо:\n"
                "🔸 Приобрести подписку\n"
                "🔸 Или активировать пробный период\n\n"
                "Выберите подходящий вариант:"
            )
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🆓 Пробный период", callback_data="trial_period")],
                [InlineKeyboardButton(text="💎 Купить подписку", callback_data="buy_subscription")],
                [InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")]
            ])
            
            await callback.message.edit_text(text=text, reply_markup=keyboard)
            return
        
        # Получаем конфигурации подписки
        configs = await repos.vpn_configs.get_by_subscription(active_subscription.id)
        
        if not configs:
            text = (
                "⚙️ <b>Конфигурации не найдены</b>\n\n"
                "Создаем вашу первую конфигурацию...\n"
                "Это может занять несколько секунд."
            )
            
            await callback.message.edit_text(text=text)
            
            # Создаем конфигурацию автоматически
            vpn_manager = VpnServiceManager(session)
            try:
                config = await vpn_manager.create_config_for_best_protocol(
                    server=active_subscription.server,
                    subscription_id=active_subscription.id,
                    preferred_protocol=active_subscription.active_protocol
                )
                
                # Обновляем список конфигураций
                configs = [config]
                
            except Exception as e:
                logger.error(f"Error creating config: {e}")
                await callback.message.edit_text(
                    "❌ Ошибка при создании конфигурации. Обратитесь в поддержку.",
                    reply_markup=get_back_button("main_menu")
                )
                return
        
        # Показываем конфигурации
        text = "⚙️ <b>Ваши VPN конфигурации:</b>\n\n"
        
        for config in configs:
            status_emoji = "✅" if config.is_active else "❌"
            protocol_emoji = {
                "vless": "🔥",
                "vmess": "💙", 
                "trojan": "💜",
                "openvpn": "🛡️", 
                "wireguard": "⚡"
            }.get(config.protocol.value, "🔧")
            
            text += f"{status_emoji} {protocol_emoji} <b>{config.protocol.value.upper()}</b>\n"
            text += f"🌍 {config.server.name} ({config.server.country})\n"
            
            if config.last_used:
                text += f"🕐 Последнее использование: {config.last_used.strftime('%d.%m.%Y')}\n"
            
            # Показываем статистику трафика
            if config.total_traffic_gb > 0:
                text += f"📊 Использовано: {config.total_traffic_gb:.2f} ГБ\n"
            
            text += "\n"
        
        # Информация о подписке
        expires_at = active_subscription.expires_at
        if expires_at:
            days_left = (expires_at - datetime.utcnow()).days
            if days_left > 0:
                text += f"⏰ <b>Подписка истекает через {days_left} дней</b>\n\n"
            else:
                text += f"⚠️ <b>Подписка истекла!</b>\n\n"
        
        text += "Выберите конфигурацию для управления:"
        
        await callback.message.edit_text(
            text=text,
            reply_markup=get_configs_keyboard(configs)
        )
        
        await state.set_state(ConfigStates.viewing_configs)
        
    except Exception as e:
        logger.error(f"Error showing configs: {e}")
        await callback.answer("❌ Ошибка при загрузке конфигураций", show_alert=True)


@router.callback_query(F.data.startswith("config_"))
async def show_config_details(callback: CallbackQuery, state: FSMContext, session, **kwargs):
    """Показать детали конфигурации"""
    try:
        await callback.answer()
        
        config_id = int(callback.data.split("_")[1])
        
        repos = RepositoryManager(session)
        config = await repos.vpn_configs.get_by_id(config_id)
        
        if not config:
            await callback.answer("❌ Конфигурация не найдена", show_alert=True)
            return
        
        # Проверяем принадлежность конфигурации пользователю
        user_service = UserService(session)
        user = await user_service.get_user_by_telegram_id(callback.from_user.id)
        
        if config.subscription.user_id != user.id:
            await callback.answer("❌ Доступ запрещен", show_alert=True)
            return
        
        # Формируем информацию о конфигурации
        status_emoji = "✅ Активна" if config.is_active else "❌ Неактивна"
        protocol_emoji = {
            "vless": "🔥",
            "vmess": "💙",
            "trojan": "💜", 
            "openvpn": "🛡️", 
            "wireguard": "⚡"
        }.get(config.protocol.value, "🔧")
        
        text = f"{protocol_emoji} <b>{config.protocol.value.upper()} Конфигурация</b>\n\n"
        text += f"📊 Статус: {status_emoji}\n"
        text += f"🌍 Сервер: {config.server.name}\n"
        text += f"📍 Местоположение: {config.server.country}, {config.server.city}\n"
        text += f"🆔 ID клиента: {config.client_id}\n"
        
        # Статистика использования
        if config.total_traffic_gb > 0:
            text += f"📈 Использовано: {config.total_traffic_gb:.2f} ГБ\n"
        else:
            text += f"📈 Использовано: 0 ГБ\n"
        
        if config.last_used:
            text += f"🕐 Последнее использование: {config.last_used.strftime('%d.%m.%Y %H:%M')}\n"
        else:
            text += f"🕐 Ещё не использовалась\n"
        
        # Информация о подписке
        subscription = config.subscription
        if subscription.expires_at:
            days_left = (subscription.expires_at - datetime.utcnow()).days
            if days_left > 0:
                text += f"⏰ Подписка: {days_left} дней\n"
            else:
                text += f"⚠️ Подписка истекла\n"
        
        text += "\nВыберите действие:"
        
        await callback.message.edit_text(
            text=text,
            reply_markup=get_config_actions_keyboard(config_id)
        )
        
        await state.update_data(current_config_id=config_id)
        
    except Exception as e:
        logger.error(f"Error showing config details: {e}")
        await callback.answer("❌ Ошибка при загрузке конфигурации", show_alert=True)


@router.callback_query(F.data.startswith("download_"))
async def download_config(callback: CallbackQuery, state: FSMContext, session, **kwargs):
    """Скачать конфигурационный файл"""
    try:
        await callback.answer("Подготавливаем файл...")
        
        config_id = int(callback.data.split("_")[1])
        
        repos = RepositoryManager(session)
        config = await repos.vpn_configs.get_by_id(config_id)
        
        if not config or not config.is_active:
            await callback.answer("❌ Конфигурация недоступна", show_alert=True)
            return
        
        # Проверяем принадлежность
        user_service = UserService(session)
        user = await user_service.get_user_by_telegram_id(callback.from_user.id)
        
        if config.subscription.user_id != user.id:
            await callback.answer("❌ Доступ запрещен", show_alert=True)
            return
        
        # Определяем расширение файла
        file_extensions = {
            "vless": ".txt",
            "vmess": ".txt",
            "trojan": ".txt",
            "openvpn": ".ovpn",
            "wireguard": ".conf"
        }
        
        extension = file_extensions.get(config.protocol.value, ".txt")
        filename = f"{config.protocol.value}_config_{config.id}{extension}"
        
        # Создаем временный файл
        temp_dir = "/tmp/vpn_configs"
        os.makedirs(temp_dir, exist_ok=True)
        temp_path = os.path.join(temp_dir, filename)
        
        with open(temp_path, 'w', encoding='utf-8') as f:
            f.write(config.connection_string)
        
        # Отправляем файл
        file = FSInputFile(temp_path, filename=filename)
        
        caption = (
            f"📁 <b>{config.protocol.value.upper()} конфигурация</b>\n"
            f"🌍 Сервер: {config.server.name}\n"
            f"📍 {config.server.country}, {config.server.city}\n\n"
            f"📱 Импортируйте этот файл в ваше VPN приложение"
        )
        
        await callback.message.answer_document(
            document=file,
            caption=caption
        )
        
        # Удаляем временный файл
        try:
            os.remove(temp_path)
        except:
            pass
        
        # Логируем скачивание
        await user_service.log_user_action(
            user_id=user.id,
            action="config_downloaded",
            details={
                "config_id": config_id,
                "protocol": config.protocol.value,
                "server": config.server.name
            }
        )
        
        # Обновляем время последнего использования
        await repos.vpn_configs.update(config_id, last_used=datetime.utcnow())
        await repos.commit()
        
        await callback.answer("✅ Файл отправлен!")
        
    except Exception as e:
        logger.error(f"Error downloading config: {e}")
        await callback.answer("❌ Ошибка при скачивании файла", show_alert=True)


@router.callback_query(F.data.startswith("qr_"))
async def show_qr_code(callback: CallbackQuery, state: FSMContext, session, **kwargs):
    """Показать QR код конфигурации"""
    try:
        await callback.answer("Генерируем QR код...")
        
        config_id = int(callback.data.split("_")[1])
        
        repos = RepositoryManager(session)
        config = await repos.vpn_configs.get_by_id(config_id)
        
        if not config or not config.is_active:
            await callback.answer("❌ Конфигурация недоступна", show_alert=True)
            return
        
        # Проверяем принадлежность
        user_service = UserService(session)
        user = await user_service.get_user_by_telegram_id(callback.from_user.id)
        
        if config.subscription.user_id != user.id:
            await callback.answer("❌ Доступ запрещен", show_alert=True)
            return
        
        # Проверяем наличие QR кода
        if not config.qr_code_path or not os.path.exists(config.qr_code_path):
            # Генерируем QR код
            from core.utils.qr_generator import generate_config_qr
            
            qr_path = await generate_config_qr(
                connection_string=config.connection_string,
                config_id=config.id,
                protocol=config.protocol.value
            )
            
            if qr_path:
                await repos.vpn_configs.update(config_id, qr_code_path=qr_path)
                await repos.commit()
                config.qr_code_path = qr_path
        
        if config.qr_code_path and os.path.exists(config.qr_code_path):
            # Отправляем QR код
            qr_file = FSInputFile(config.qr_code_path)
            
            caption = (
                f"📷 <b>QR код для {config.protocol.value.upper()}</b>\n"
                f"🌍 Сервер: {config.server.name}\n"
                f"📍 {config.server.country}, {config.server.city}\n\n"
                f"📱 Отсканируйте этот код в VPN приложении:\n"
                f"• V2rayNG (Android)\n"
                f"• V2Box (iOS)\n"
                f"• OpenVPN Connect\n"
                f"• WireGuard"
            )
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="📋 Инструкция", callback_data=f"instruction_{config_id}"),
                    InlineKeyboardButton(text="📱 Скачать файл", callback_data=f"download_{config_id}")
                ],
                [InlineKeyboardButton(text="🔙 К конфигурации", callback_data=f"config_{config_id}")]
            ])
            
            await callback.message.answer_photo(
                photo=qr_file,
                caption=caption,
                reply_markup=keyboard
            )
            
            # Логируем просмотр QR кода
            await user_service.log_user_action(
                user_id=user.id,
                action="qr_code_viewed",
                details={
                    "config_id": config_id,
                    "protocol": config.protocol.value
                }
            )
            
            # Обновляем время использования
            await repos.vpn_configs.update(config_id, last_used=datetime.utcnow())
            await repos.commit()
            
        else:
            await callback.answer("❌ Ошибка при генерации QR кода", show_alert=True)
        
    except Exception as e:
        logger.error(f"Error showing QR code: {e}")
        await callback.answer("❌ Ошибка при загрузке QR кода", show_alert=True)


@router.callback_query(F.data.startswith("instruction_"))
async def show_instruction(callback: CallbackQuery, state: FSMContext, session, **kwargs):
    """Показать инструкцию по настройке"""
    try:
        await callback.answer()
        
        config_id = int(callback.data.split("_")[1])
        
        repos = RepositoryManager(session)
        config = await repos.vpn_configs.get_by_id(config_id)
        
        if not config:
            await callback.answer("❌ Конфигурация не найдена", show_alert=True)
            return
        
        protocol = config.protocol.value
        
        # Инструкции для разных протоколов
        instructions = {
            "vless": [
                "📱 Скачайте приложение V2rayNG (Android) или V2Box (iOS)",
                "📂 Импортируйте конфигурацию через QR код или файл",
                "🔌 Нажмите кнопку подключения",
                "✅ Проверьте подключение на сайте 2ip.ru"
            ],
            "vmess": [
                "📱 Скачайте приложение V2rayNG (Android) или V2Box (iOS)",
                "📂 Импортируйте VMess конфигурацию через QR код",
                "🔌 Нажмите кнопку подключения",
                "✅ Проверьте подключение"
            ],
            "trojan": [
                "📱 Скачайте приложение V2rayNG или Clash",
                "📂 Импортируйте Trojan конфигурацию",
                "🔌 Подключитесь к серверу",
                "✅ Проверьте подключение"
            ],
            "openvpn": [
                "📱 Скачайте OpenVPN Connect из App Store/Google Play",
                "📂 Импортируйте .ovpn файл в приложение",
                "🔌 Нажмите кнопку подключения",
                "🔐 При необходимости введите логин и пароль",
                "✅ Проверьте подключение"
            ],
            "wireguard": [
                "📱 Скачайте WireGuard из App Store/Google Play",
                "📂 Импортируйте конфигурацию через QR код или файл",
                "🔌 Активируйте туннель",
                "✅ Проверьте подключение"
            ]
        }
        
        protocol_instructions = instructions.get(protocol, [
            "📱 Скачайте подходящее VPN приложение",
            "📂 Импортируйте конфигурацию",
            "🔌 Подключитесь к VPN"
        ])
        
        text = f"📖 <b>Инструкция для {protocol.upper()}</b>\n\n"
        
        for i, step in enumerate(protocol_instructions, 1):
            text += f"{i}. {step}\n"
        
        text += f"\n🌍 <b>Сервер:</b> {config.server.name}\n"
        text += f"📍 <b>Местоположение:</b> {config.server.country}\n\n"
        text += "💡 <b>Полезные ссылки:</b>\n"
        text += "• 2ip.ru - проверка IP адреса\n"
        text += "• speedtest.net - тест скорости\n\n"
        text += "❓ Если возникли проблемы - обратитесь в поддержку!"
        
        # Кнопки с дополнительными действиями
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="📱 Скачать файл", callback_data=f"download_{config_id}"),
                InlineKeyboardButton(text="📷 QR код", callback_data=f"qr_{config_id}")
            ],
            [
                InlineKeyboardButton(text="🔄 Обновить", callback_data=f"refresh_{config_id}"),
                InlineKeyboardButton(text="🧪 Тест", callback_data=f"test_{config_id}")
            ],
            [InlineKeyboardButton(text="🔙 К конфигурации", callback_data=f"config_{config_id}")]
        ])
        
        await callback.message.edit_text(
            text=text,
            reply_markup=keyboard
        )
        
    except Exception as e:
        logger.error(f"Error showing instruction: {e}")
        await callback.answer("❌ Ошибка при загрузке инструкции", show_alert=True)


@router.callback_query(F.data.startswith("refresh_"))
async def refresh_config(callback: CallbackQuery, state: FSMContext, session, **kwargs):
    """Обновить конфигурацию"""
    try:
        await callback.answer("Обновляем конфигурацию...")
        
        config_id = int(callback.data.split("_")[1])
        
        repos = RepositoryManager(session)
        config = await repos.vpn_configs.get_by_id(config_id)
        
        if not config:
            await callback.answer("❌ Конфигурация не найдена", show_alert=True)
            return
        
        # Получаем VPN сервис
        vpn_manager = VpnServiceManager(session)
        vpn_service = vpn_manager.get_service(config.protocol, config.server)
        
        # Получаем актуальную статистику
        usage_stats = await vpn_service.get_usage_stats(config_id)
        
        if usage_stats:
            # Обновляем статистику в базе
            await repos.vpn_configs.update_usage(
                config_id, 
                usage_stats.get("total_gb", 0)
            )
            await repos.commit()
        
        # Показываем обновленную информацию
        await show_config_details(callback, state, session, **kwargs)
        
        await callback.answer("✅ Конфигурация обновлена", show_alert=False)
        
        # Логируем обновление
        user_service = UserService(session)
        user = await user_service.get_user_by_telegram_id(callback.from_user.id)
        
        await user_service.log_user_action(
            user_id=user.id,
            action="config_refreshed",
            details={"config_id": config_id}
        )
        
    except Exception as e:
        logger.error(f"Error refreshing config: {e}")
        await callback.answer("❌ Ошибка при обновлении", show_alert=True)


@router.callback_query(F.data.startswith("test_"))
async def test_config_connection(callback: CallbackQuery, state: FSMContext, session, **kwargs):
    """Тестировать соединение конфигурации"""
    try:
        await callback.answer("Тестируем соединение...")
        
        config_id = int(callback.data.split("_")[1])
        
        repos = RepositoryManager(session)
        config = await repos.vpn_configs.get_by_id(config_id)
        
        if not config:
            await callback.answer("❌ Конфигурация не найдена", show_alert=True)
            return
        
        # Получаем VPN сервис и тестируем соединение
        vpn_manager = VpnServiceManager(session)
        vpn_service = vpn_manager.get_service(config.protocol, config.server)
        
        connection_ok = await vpn_service.test_connection(config_id)
        
        if connection_ok:
            test_result = "✅ <b>Соединение работает!</b>\n\n"
            test_result += f"🌍 Сервер {config.server.name} доступен\n"
            test_result += f"🔐 Протокол {config.protocol.value.upper()} функционирует\n"
            test_result += f"📡 Конфигурация готова к использованию"
        else:
            test_result = "❌ <b>Проблемы с соединением</b>\n\n"
            test_result += f"🌍 Сервер {config.server.name} недоступен\n"
            test_result += f"⚠️ Возможные причины:\n"
            test_result += f"• Технические работы на сервере\n"
            test_result += f"• Проблемы с интернет-соединением\n"
            test_result += f"• Блокировка провайдером\n\n"
            test_result += f"💡 Попробуйте позже или обратитесь в поддержку"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Повторить тест", callback_data=f"test_{config_id}"),
                InlineKeyboardButton(text="🎧 Поддержка", callback_data="support")
            ],
            [InlineKeyboardButton(text="🔙 К конфигурации", callback_data=f"config_{config_id}")]
        ])
        
        await callback.message.edit_text(
            text=test_result,
            reply_markup=keyboard
        )
        
        # Логируем тест
        user_service = UserService(session)
        user = await user_service.get_user_by_telegram_id(callback.from_user.id)
        
        await user_service.log_user_action(
            user_id=user.id,
            action="config_tested",
            details={
                "config_id": config_id,
                "test_result": "success" if connection_ok else "failed"
            }
        )
        
    except Exception as e:
        logger.error(f"Error testing config connection: {e}")
        await callback.answer("❌ Ошибка при тестировании", show_alert=True)


@router.callback_query(F.data.startswith("delete_config_"))
async def delete_config_request(callback: CallbackQuery, state: FSMContext, session, **kwargs):
    """Запрос на удаление конфигурации"""
    try:
        await callback.answer()
        
        config_id = int(callback.data.split("_")[2])
        
        repos = RepositoryManager(session)
        config = await repos.vpn_configs.get_by_id(config_id)
        
        if not config:
            await callback.answer("❌ Конфигурация не найдена", show_alert=True)
            return
        
        text = (
            f"🗑️ <b>Удаление конфигурации</b>\n\n"
            f"Вы действительно хотите удалить конфигурацию?\n\n"
            f"🔐 Протокол: {config.protocol.value.upper()}\n"
            f"🌍 Сервер: {config.server.name}\n\n"
            f"⚠️ <b>Внимание!</b> Это действие нельзя отменить."
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"confirm_delete_{config_id}"),
                InlineKeyboardButton(text="❌ Отмена", callback_data=f"config_{config_id}")
            ]
        ])
        
        await callback.message.edit_text(text=text, reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Error in delete config request: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data.startswith("confirm_delete_"))
async def confirm_delete_config(callback: CallbackQuery, state: FSMContext, session, **kwargs):
    """Подтверждение удаления конфигурации"""
    try:
        await callback.answer("Удаляем конфигурацию...")
        
        config_id = int(callback.data.split("_")[2])
        
        # Получаем VPN сервис и удаляем конфигурацию
        repos = RepositoryManager(session)
        config = await repos.vpn_configs.get_by_id(config_id)
        
        if not config:
            await callback.answer("❌ Конфигурация не найдена", show_alert=True)
            return
        
        vpn_manager = VpnServiceManager(session)
        vpn_service = vpn_manager.get_service(config.protocol, config.server)
        
        # Удаляем конфигурацию
        success = await vpn_service.delete_config(config_id)
        
        if success:
            text = (
                "✅ <b>Конфигурация удалена</b