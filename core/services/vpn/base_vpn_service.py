"""
Базовый сервис для работы с VPN протоколами
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from core.database.models import Server, VpnConfig, VpnProtocol, Subscription
from core.database.repositories import RepositoryManager
from core.exceptions.vpn_exceptions import (
    VpnConfigurationError, VpnConnectionError, 
    VpnServerNotAvailableError, VpnProtocolNotSupportedError
)


class BaseVpnService(ABC):
    """
    Абстрактный базовый класс для всех VPN сервисов
    """
    
    def __init__(self, session: AsyncSession, server: Server):
        self.session = session
        self.server = server
        self.repos = RepositoryManager(session)
        self.protocol = self.get_protocol()
    
    @abstractmethod
    def get_protocol(self) -> VpnProtocol:
        """Получить протокол сервиса"""
        pass
    
    @abstractmethod
    async def create_config(
        self, 
        subscription_id: int, 
        client_name: Optional[str] = None,
        additional_params: Optional[Dict[str, Any]] = None
    ) -> VpnConfig:
        """
        Создать VPN конфигурацию для подписки
        
        Args:
            subscription_id: ID подписки
            client_name: Имя клиента (опционально)
            additional_params: Дополнительные параметры
            
        Returns:
            VpnConfig: Созданная конфигурация
        """
        pass
    
    @abstractmethod
    async def delete_config(self, config_id: int) -> bool:
        """
        Удалить VPN конфигурацию
        
        Args:
            config_id: ID конфигурации
            
        Returns:
            bool: Успешность удаления
        """
        pass
    
    @abstractmethod
    async def get_connection_string(self, config_id: int) -> str:
        """
        Получить строку подключения для конфигурации
        
        Args:
            config_id: ID конфигурации
            
        Returns:
            str: Строка подключения
        """
        pass
    
    @abstractmethod
    async def get_config_data(self, config_id: int) -> Dict[str, Any]:
        """
        Получить данные конфигурации
        
        Args:
            config_id: ID конфигурации
            
        Returns:
            Dict[str, Any]: Данные конфигурации
        """
        pass
    
    @abstractmethod
    async def update_config(
        self, 
        config_id: int, 
        params: Dict[str, Any]
    ) -> bool:
        """
        Обновить конфигурацию
        
        Args:
            config_id: ID конфигурации
            params: Новые параметры
            
        Returns:
            bool: Успешность обновления
        """
        pass
    
    @abstractmethod
    async def get_usage_stats(self, config_id: int) -> Dict[str, Any]:
        """
        Получить статистику использования конфигурации
        
        Args:
            config_id: ID конфигурации
            
        Returns:
            Dict[str, Any]: Статистика использования
        """
        pass
    
    @abstractmethod
    async def test_connection(self, config_id: int) -> bool:
        """
        Тестировать соединение с конфигурацией
        
        Args:
            config_id: ID конфигурации
            
        Returns:
            bool: Доступность соединения
        """
        pass
    
    async def validate_server_config(self) -> bool:
        """
        Валидация конфигурации сервера для протокола
        
        Returns:
            bool: Валидность конфигурации
        """
        try:
            # Проверяем, поддерживает ли сервер протокол
            if self.protocol.value not in self.server.supported_protocols:
                raise VpnProtocolNotSupportedError(
                    f"Server {self.server.id} doesn't support {self.protocol.value}"
                )
            
            # Проверяем активность сервера
            if not self.server.is_active or self.server.is_maintenance:
                raise VpnServerNotAvailableError(
                    f"Server {self.server.id} is not available"
                )
            
            return True
            
        except Exception as e:
            logger.error(f"Server config validation failed: {e}")
            return False
    
    async def generate_client_id(self, subscription_id: int) -> str:
        """
        Генерировать уникальный ID клиента
        
        Args:
            subscription_id: ID подписки
            
        Returns:
            str: Уникальный ID клиента
        """
        import uuid
        timestamp = int(datetime.utcnow().timestamp())
        unique_id = str(uuid.uuid4())[:8]
        return f"{self.protocol.value}_{subscription_id}_{timestamp}_{unique_id}"
    
    async def log_config_action(
        self, 
        config_id: int, 
        action: str, 
        details: Optional[Dict[str, Any]] = None
    ):
        """
        Логировать действие с конфигурацией
        
        Args:
            config_id: ID конфигурации
            action: Действие
            details: Дополнительные детали
        """
        try:
            config = await self.repos.vpn_configs.get_by_id(config_id)
            if config:
                await self.repos.user_activities.log_activity(
                    user_id=config.subscription.user_id,
                    action=f"vpn_{action}",
                    details={
                        "config_id": config_id,
                        "protocol": self.protocol.value,
                        "server_id": self.server.id,
                        **(details or {})
                    }
                )
        except Exception as e:
            logger.error(f"Error logging config action: {e}")
    
    async def create_base_config(
        self,
        subscription_id: int,
        protocol_specific_data: Dict[str, Any],
        connection_string: str,
        client_id: Optional[str] = None
    ) -> VpnConfig:
        """
        Создать базовую VPN конфигурацию
        
        Args:
            subscription_id: ID подписки
            protocol_specific_data: Данные специфичные для протокола
            connection_string: Строка подключения
            client_id: ID клиента (опционально)
            
        Returns:
            VpnConfig: Созданная конфигурация
        """
        try:
            # Генерируем client_id если не передан
            if not client_id:
                client_id = await self.generate_client_id(subscription_id)
            
            # Создаем конфигурацию в базе данных
            config_data = {
                "subscription_id": subscription_id,
                "server_id": self.server.id,
                "protocol": self.protocol,
                "config_data": protocol_specific_data,
                "connection_string": connection_string,
                "client_id": client_id,
                "is_active": True
            }
            
            config = await self.repos.vpn_configs.create(**config_data)
            
            # Логируем создание
            await self.log_config_action(
                config.id, 
                "config_created",
                {"client_id": client_id}
            )
            
            await self.repos.commit()
            logger.info(f"VPN config created: {config.id} for protocol {self.protocol.value}")
            
            return config
            
        except Exception as e:
            await self.repos.rollback()
            logger.error(f"Error creating base config: {e}")
            raise VpnConfigurationError(f"Failed to create config: {e}")
    
    async def deactivate_config(self, config_id: int) -> bool:
        """
        Деактивировать конфигурацию
        
        Args:
            config_id: ID конфигурации
            
        Returns:
            bool: Успешность деактивации
        """
        try:
            success = await self.repos.vpn_configs.deactivate(config_id)
            
            if success:
                await self.log_config_action(config_id, "config_deactivated")
                await self.repos.commit()
                logger.info(f"VPN config {config_id} deactivated")
            
            return success
            
        except Exception as e:
            await self.repos.rollback()
            logger.error(f"Error deactivating config {config_id}: {e}")
            return False
    
    async def get_server_load(self) -> Dict[str, Any]:
        """
        Получить загрузку сервера
        
        Returns:
            Dict[str, Any]: Информация о загрузке
        """
        try:
            load_percentage = (self.server.current_users / self.server.max_users) * 100
            
            return {
                "current_users": self.server.current_users,
                "max_users": self.server.max_users,
                "load_percentage": round(load_percentage, 2),
                "cpu_usage": float(self.server.cpu_usage),
                "memory_usage": float(self.server.memory_usage),
                "disk_usage": float(self.server.disk_usage),
                "is_overloaded": load_percentage > 90
            }
            
        except Exception as e:
            logger.error(f"Error getting server load: {e}")
            return {}
    
    async def check_server_capacity(self) -> bool:
        """
        Проверить, есть ли место на сервере для новых пользователей
        
        Returns:
            bool: Доступность места
        """
        try:
            load_info = await self.get_server_load()
            return not load_info.get("is_overloaded", True)
            
        except Exception as e:
            logger.error(f"Error checking server capacity: {e}")
            return False


class VpnServiceMixin:
    """
    Миксин с общими методами для VPN сервисов
    """
    
    def generate_uuid(self) -> str:
        """Генерировать UUID"""
        import uuid
        return str(uuid.uuid4())
    
    def encode_base64(self, data: str) -> str:
        """Кодировать в base64"""
        import base64
        return base64.b64encode(data.encode()).decode()
    
    def decode_base64(self, data: str) -> str:
        """Декодировать из base64"""
        import base64
        return base64.b64decode(data.encode()).decode()
    
    def format_connection_url(self, protocol: str, params: Dict[str, Any]) -> str:
        """
        Форматировать URL подключения
        
        Args:
            protocol: Протокол (vless, vmess, trojan, etc.)
            params: Параметры подключения
            
        Returns:
            str: URL подключения
        """
        try:
            import urllib.parse
            
            # Базовая структура URL
            url_parts = {
                "scheme": protocol,
                "netloc": f"{params.get('address', '')}:{params.get('port', '')}",
                "path": "",
                "params": "",
                "query": "",
                "fragment": params.get('fragment', '')
            }
            
            # Добавляем параметры в query
            query_params = {}
            for key, value in params.items():
                if key not in ["address", "port", "fragment"] and value is not None:
                    query_params[key] = str(value)
            
            url_parts["query"] = urllib.parse.urlencode(query_params)
            
            # Собираем URL
            url = urllib.parse.urlunparse(tuple(url_parts.values()))
            
            return url
            
        except Exception as e:
            logger.error(f"Error formatting connection URL: {e}")
            return ""
    
    async def generate_qr_code(self, connection_string: str, config_id: int) -> Optional[str]:
        """
        Генерировать QR код для конфигурации
        
        Args:
            connection_string: Строка подключения
            config_id: ID конфигурации
            
        Returns:
            Optional[str]: Путь к файлу QR кода
        """
        try:
            import qrcode
            from io import BytesIO
            from PIL import Image
            import os
            
            # Создаем QR код
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(connection_string)
            qr.make(fit=True)
            
            # Создаем изображение
            qr_image = qr.make_image(fill_color="black", back_color="white")
            
            # Сохраняем файл
            filename = f"qr_config_{config_id}.png"
            filepath = f"static/qr_codes/{filename}"
            
            os.makedirs("static/qr_codes", exist_ok=True)
            qr_image.save(filepath)
            
            logger.info(f"QR code generated: {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"Error generating QR code: {e}")
            return None
    
    def validate_ip_address(self, ip: str) -> bool:
        """
        Валидация IP адреса
        
        Args:
            ip: IP адрес
            
        Returns:
            bool: Валидность IP
        """
        import ipaddress
        try:
            ipaddress.ip_address(ip)
            return True
        except ValueError:
            return False
    
    def validate_port(self, port: int) -> bool:
        """
        Валидация порта
        
        Args:
            port: Номер порта
            
        Returns:
            bool: Валидность порта
        """
        return 1 <= port <= 65535
    
    def sanitize_client_name(self, name: str) -> str:
        """
        Очистка имени клиента от недопустимых символов
        
        Args:
            name: Исходное имя
            
        Returns:
            str: Очищенное имя
        """
        import re
        # Оставляем только буквы, цифры, дефисы и подчеркивания
        sanitized = re.sub(r'[^a-zA-Z0-9_-]', '', name)
        # Ограничиваем длину
        return sanitized[:50] if sanitized else "client"