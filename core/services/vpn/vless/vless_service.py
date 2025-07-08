"""
Сервис для работы с VLESS протоколом
"""

import json
import uuid
from typing import Dict, Any, Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from core.database.models import Server, VpnConfig, VpnProtocol
from core.services.vpn.base_vpn_service import BaseVpnService, VpnServiceMixin
from core.services.vpn.vless.x3ui_service import X3UIService
from core.exceptions.vpn_exceptions import VpnConfigurationError, VpnConnectionError
from config.settings import vpn_settings


class VlessService(BaseVpnService, VpnServiceMixin):
    """
    Сервис для работы с VLESS протоколом через 3X-UI
    """
    
    def __init__(self, session: AsyncSession, server: Server):
        super().__init__(session, server)
        self.x3ui_service = X3UIService(server)
    
    def get_protocol(self) -> VpnProtocol:
        """Получить протокол сервиса"""
        return VpnProtocol.VLESS
    
    async def create_config(
        self, 
        subscription_id: int, 
        client_name: Optional[str] = None,
        additional_params: Optional[Dict[str, Any]] = None
    ) -> VpnConfig:
        """Создать VLESS конфигурацию"""
        try:
            if not await self.validate_server_config():
                raise VpnConfigurationError("Server configuration is invalid")
            
            if not await self.check_server_capacity():
                raise VpnConfigurationError("Server is at capacity")
            
            # Проверяем доступность 3X-UI
            if not await self.x3ui_service.test_connection():
                raise VpnConnectionError("Cannot connect to 3X-UI panel")
            
            # Генерируем client_id и UUID
            client_id = await self.generate_client_id(subscription_id)
            client_uuid = self.generate_uuid()
            
            if client_name:
                client_name = self.sanitize_client_name(client_name)
            else:
                client_name = f"client_{subscription_id}"
            
            # Получаем конфигурацию VLESS сервера
            vless_config = self.server.vless_config or {}
            
            # Создаем клиента в 3X-UI
            x3ui_client = await self.x3ui_service.create_client(
                email=client_name,
                uuid=client_uuid,
                limit_ip=1,
                total_gb=0,  # Безлимит, ограничения на уровне подписки
                expiry_time=0,  # Истечение контролируется подпиской
                enable=True,
                subId=str(subscription_id)
            )
            
            if not x3ui_client or not x3ui_client.get("success"):
                raise VpnConfigurationError("Failed to create client in 3X-UI")
            
            # Формируем данные конфигурации
            config_data = {
                "client_name": client_name,
                "client_id": client_id,
                "uuid": client_uuid,
                "address": self.server.domain or self.server.ip_address,
                "port": vless_config.get("port", 443),
                "encryption": vless_config.get("encryption", "none"),
                "network": vless_config.get("network", "tcp"),
                "header_type": vless_config.get("header_type", "none"),
                "flow": vless_config.get("flow", "xtls-rprx-vision"),
                "security": vless_config.get("security", "reality"),
                "reality": vless_config.get("reality", {}),
                "x3ui_inbound_id": x3ui_client.get("inbound_id"),
                "server_name": self.server.name
            }
            
            # Генерируем строку подключения VLESS
            connection_string = await self._generate_vless_link(config_data)
            
            # Создаем базовую конфигурацию
            vpn_config = await self.create_base_config(
                subscription_id=subscription_id,
                protocol_specific_data=config_data,
                connection_string=connection_string,
                client_id=client_id
            )
            
            # Генерируем QR код
            qr_path = await self.generate_qr_code(connection_string, vpn_config.id)
            if qr_path:
                await self.repos.vpn_configs.update(
                    vpn_config.id,
                    qr_code_path=qr_path,
                    qr_code_data=connection_string
                )
            
            logger.info(f"VLESS config created: {vpn_config.id} with UUID: {client_uuid}")
            return vpn_config
            
        except Exception as e:
            logger.error(f"Error creating VLESS config: {e}")
            raise VpnConfigurationError(f"Failed to create VLESS config: {e}")
    
    async def delete_config(self, config_id: int) -> bool:
        """Удалить VLESS конфигурацию"""
        try:
            config = await self.repos.vpn_configs.get_by_id(config_id)
            if not config:
                return False
            
            # Удаляем клиента из 3X-UI
            client_uuid = config.config_data.get("uuid")
            if client_uuid:
                success = await self.x3ui_service.delete_client(client_uuid)
                if not success:
                    logger.warning(f"Failed to delete client {client_uuid} from 3X-UI")
            
            # Деактивируем конфигурацию в базе данных
            success = await self.deactivate_config(config_id)
            
            # Удаляем QR код файл
            if config.qr_code_path:
                import os
                if os.path.exists(config.qr_code_path):
                    os.remove(config.qr_code_path)
            
            await self.log_config_action(config_id, "config_deleted")
            return success
            
        except Exception as e:
            logger.error(f"Error deleting VLESS config {config_id}: {e}")
            return False
    
    async def get_connection_string(self, config_id: int) -> str:
        """Получить VLESS ссылку"""
        try:
            config = await self.repos.vpn_configs.get_by_id(config_id)
            if not config or not config.is_active:
                return ""
            
            return config.connection_string
            
        except Exception as e:
            logger.error(f"Error getting VLESS connection string: {e}")
            return ""
    
    async def get_config_data(self, config_id: int) -> Dict[str, Any]:
        """Получить данные конфигурации"""
        try:
            config = await self.repos.vpn_configs.get_by_id(config_id)
            return config.config_data if config else {}
        except Exception as e:
            logger.error(f"Error getting VLESS config data: {e}")
            return {}
    
    async def update_config(self, config_id: int, params: Dict[str, Any]) -> bool:
        """Обновить конфигурацию"""
        try:
            config = await self.repos.vpn_configs.get_by_id(config_id)
            if not config:
                return False
            
            # Обновляем данные в 3X-UI если необходимо
            client_uuid = config.config_data.get("uuid")
            if client_uuid and any(key in params for key in ["enable", "limit_ip", "total_gb", "expiry_time"]):
                x3ui_params = {}
                if "enable" in params:
                    x3ui_params["enable"] = params["enable"]
                if "limit_ip" in params:
                    x3ui_params["limitIp"] = params["limit_ip"]
                if "total_gb" in params:
                    x3ui_params["totalGB"] = params["total_gb"]
                if "expiry_time" in params:
                    x3ui_params["expiryTime"] = params["expiry_time"]
                
                if x3ui_params:
                    await self.x3ui_service.update_client(client_uuid, x3ui_params)
            
            # Обновляем локальные данные
            updated_config_data = config.config_data.copy()
            updated_config_data.update(params)
            
            # Если изменились критичные параметры - перегенерируем ссылку
            critical_params = ['address', 'port', 'security', 'network']
            if any(param in params for param in critical_params):
                connection_string = await self._generate_vless_link(updated_config_data)
                
                success = await self.repos.vpn_configs.update(
                    config_id,
                    config_data=updated_config_data,
                    connection_string=connection_string
                )
            else:
                success = await self.repos.vpn_configs.update(
                    config_id,
                    config_data=updated_config_data
                )
            
            if success:
                await self.log_config_action(config_id, "config_updated")
            
            return success
            
        except Exception as e:
            logger.error(f"Error updating VLESS config: {e}")
            return False
    
    async def get_usage_stats(self, config_id: int) -> Dict[str, Any]:
        """Получить статистику использования"""
        try:
            config = await self.repos.vpn_configs.get_by_id(config_id)
            if not config:
                return {}
            
            # Пытаемся получить статистику из 3X-UI
            client_uuid = config.config_data.get("uuid")
            x3ui_stats = {}
            
            if client_uuid:
                client_info = await self.x3ui_service.get_client_info(client_uuid)
                if client_info:
                    x3ui_stats = {
                        "up_traffic": client_info.get("up", 0),
                        "down_traffic": client_info.get("down", 0),
                        "total_traffic": client_info.get("total", 0),
                        "enable": client_info.get("enable", True),
                        "expiry_time": client_info.get("expiryTime", 0)
                    }
            
            # Базовая статистика
            base_stats = {
                "total_gb": float(config.total_traffic_gb),
                "last_used": config.last_used.isoformat() if config.last_used else None,
                "active": config.is_active,
                "protocol": "VLESS",
                "uuid": config.config_data.get("uuid"),
                "client_name": config.config_data.get("client_name")
            }
            
            # Объединяем статистику
            base_stats.update(x3ui_stats)
            return base_stats
            
        except Exception as e:
            logger.error(f"Error getting VLESS usage stats: {e}")
            return {}
    
    async def test_connection(self, config_id: int) -> bool:
        """Тестировать VLESS соединение"""
        try:
            config = await self.repos.vpn_configs.get_by_id(config_id)
            if not config or not config.is_active:
                return False
            
            # Проверяем доступность 3X-UI
            if not await self.x3ui_service.test_connection():
                return False
            
            # Проверяем состояние клиента в 3X-UI
            client_uuid = config.config_data.get("uuid")
            if client_uuid:
                client_info = await self.x3ui_service.get_client_info(client_uuid)
                if client_info and client_info.get("enable"):
                    return True
            
            # Проверяем доступность сервера
            address = config.config_data.get("address")
            port = config.config_data.get("port", 443)
            
            from core.utils.helpers import test_network_connectivity
            return await test_network_connectivity(address, port)
            
        except Exception as e:
            logger.error(f"Error testing VLESS connection: {e}")
            return False
    
    async def _generate_vless_link(self, config_data: Dict[str, Any]) -> str:
        """Генерировать VLESS ссылку"""
        try:
            # Базовые параметры
            uuid = config_data["uuid"]
            address = config_data["address"]
            port = config_data["port"]
            
            # Параметры запроса
            query_params = {
                "encryption": config_data.get("encryption", "none"),
                "security": config_data.get("security", "reality"),
                "type": config_data.get("network", "tcp"),
                "headerType": config_data.get("header_type", "none"),
                "flow": config_data.get("flow", "xtls-rprx-vision")
            }
            
            # Добавляем Reality параметры если используется
            if config_data.get("security") == "reality":
                reality_config = config_data.get("reality", {})
                if reality_config.get("server_names"):
                    query_params["sni"] = reality_config["server_names"][0]
                if reality_config.get("public_key"):
                    query_params["pbk"] = reality_config["public_key"]
                if reality_config.get("short_ids"):
                    query_params["sid"] = reality_config["short_ids"][0]
                if reality_config.get("finger_print"):
                    query_params["fp"] = reality_config["finger_print"]
                if reality_config.get("spider_x"):
                    query_params["spx"] = reality_config["spider_x"]
            
            # Формируем URL
            vless_url = self.format_connection_url("vless", {
                "address": address,
                "port": port,
                "fragment": config_data.get("client_name", "vless-config"),
                **query_params
            })
            
            # Добавляем UUID в начало
            if "://" in vless_url:
                protocol_part, rest = vless_url.split("://", 1)
                vless_url = f"{protocol_part}://{uuid}@{rest}"
            
            return vless_url
            
        except Exception as e:
            logger.error(f"Error generating VLESS link: {e}")
            return ""
    
    async def get_server_info(self) -> Optional[Dict[str, Any]]:
        """Получить информацию о сервере через 3X-UI"""
        try:
            return await self.x3ui_service.get_server_info()
        except Exception as e:
            logger.error(f"Error getting server info: {e}")
            return None
    
    async def regenerate_uuid(self, config_id: int) -> bool:
        """Перегенерировать UUID для конфигурации"""
        try:
            config = await self.repos.vpn_configs.get_by_id(config_id)
            if not config:
                return False
            
            old_uuid = config.config_data.get("uuid")
            new_uuid = self.generate_uuid()
            
            # Обновляем клиента в 3X-UI
            if old_uuid:
                # Удаляем старого клиента
                await self.x3ui_service.delete_client(old_uuid)
                
                # Создаем нового клиента с новым UUID
                client_name = config.config_data.get("client_name", "regenerated_client")
                x3ui_client = await self.x3ui_service.create_client(
                    email=client_name,
                    uuid=new_uuid,
                    limit_ip=1,
                    enable=True,
                    subId=str(config.subscription_id)
                )
                
                if not x3ui_client or not x3ui_client.get("success"):
                    logger.error("Failed to create new client in 3X-UI")
                    return False
            
            # Обновляем конфигурацию
            updated_config_data = config.config_data.copy()
            updated_config_data["uuid"] = new_uuid
            
            # Генерируем новую ссылку
            connection_string = await self._generate_vless_link(updated_config_data)
            
            success = await self.repos.vpn_configs.update(
                config_id,
                config_data=updated_config_data,
                connection_string=connection_string
            )
            
            if success:
                await self.log_config_action(
                    config_id, 
                    "uuid_regenerated",
                    {"old_uuid": old_uuid, "new_uuid": new_uuid}
                )
            
            return success
            
        except Exception as e:
            logger.error(f"Error regenerating UUID for config {config_id}: {e}")
            return False
    
    async def get_client_list(self) -> List[Dict[str, Any]]:
        """Получить список всех клиентов на сервере"""
        try:
            return await self.x3ui_service.get_all_clients()
        except Exception as e:
            logger.error(f"Error getting client list: {e}")
            return []
    
    async def validate_server_config(self) -> bool:
        """Расширенная валидация конфигурации VLESS сервера"""
        try:
            # Базовая валидация
            if not await super().validate_server_config():
                return False
            
            # Проверяем конфигурацию VLESS
            vless_config = self.server.vless_config or {}
            
            # Проверяем наличие обязательных полей
            if not vless_config.get("port"):
                logger.error("VLESS port not configured")
                return False
            
            # Проверяем доступность 3X-UI
            if not await self.x3ui_service.test_connection():
                logger.error("3X-UI panel is not accessible")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"VLESS server config validation failed: {e}")
            return False