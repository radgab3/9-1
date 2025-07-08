"""
Сервис для работы с OpenVPN протоколом
"""

import os
import tempfile
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from core.database.models import Server, VpnConfig, VpnProtocol
from core.services.vpn.base_vpn_service import BaseVpnService, VpnServiceMixin
from core.services.vpn.openvpn.certificate_service import CertificateService
from core.exceptions.vpn_exceptions import VpnConfigurationError
from config.settings import vpn_settings


class OpenVpnService(BaseVpnService, VpnServiceMixin):
    """Сервис для работы с OpenVPN протоколом"""
    
    def __init__(self, session: AsyncSession, server: Server):
        super().__init__(session, server)
        self.cert_service = CertificateService()
    
    def get_protocol(self) -> VpnProtocol:
        """Получить протокол сервиса"""
        return VpnProtocol.OPENVPN
    
    async def create_config(
        self, 
        subscription_id: int, 
        client_name: Optional[str] = None,
        additional_params: Optional[Dict[str, Any]] = None
    ) -> VpnConfig:
        """Создать OpenVPN конфигурацию"""
        try:
            if not await self.validate_server_config():
                raise VpnConfigurationError("Server configuration is invalid")
            
            if not await self.check_server_capacity():
                raise VpnConfigurationError("Server is at capacity")
            
            # Генерируем client_id
            client_id = await self.generate_client_id(subscription_id)
            
            if client_name:
                client_name = self.sanitize_client_name(client_name)
            else:
                client_name = f"client_{subscription_id}"
            
            # Получаем конфигурацию сервера
            ovpn_config = self.server.openvpn_config or {}
            
            # Генерируем сертификаты для клиента
            client_cert_data = await self.cert_service.generate_client_certificate(
                client_name=client_name,
                server_ca=ovpn_config.get("ca_cert"),
                server_key=ovpn_config.get("ca_key")
            )
            
            # Формируем данные конфигурации
            config_data = {
                "client_name": client_name,
                "client_id": client_id,
                "remote": self.server.domain or self.server.ip_address,
                "port": ovpn_config.get("port", vpn_settings.OPENVPN_PORT),
                "proto": ovpn_config.get("protocol", vpn_settings.OPENVPN_PROTOCOL),
                "cipher": ovpn_config.get("cipher", vpn_settings.OPENVPN_CIPHER),
                "auth": ovpn_config.get("auth", "SHA256"),
                "client_cert": client_cert_data["certificate"],
                "client_key": client_cert_data["private_key"],
                "ca_cert": ovpn_config.get("ca_cert"),
                "ta_key": ovpn_config.get("ta_key")
            }
            
            # Генерируем .ovpn файл
            ovpn_content = await self._generate_ovpn_config(config_data)
            
            # Создаем базовую конфигурацию
            vpn_config = await self.create_base_config(
                subscription_id=subscription_id,
                protocol_specific_data=config_data,
                connection_string=ovpn_content,
                client_id=client_id
            )
            
            # Генерируем QR код
            qr_path = await self.generate_qr_code(ovpn_content, vpn_config.id)
            if qr_path:
                await self.repos.vpn_configs.update(
                    vpn_config.id,
                    qr_code_path=qr_path,
                    qr_code_data=ovpn_content
                )
            
            logger.info(f"OpenVPN config created: {vpn_config.id}")
            return vpn_config
            
        except Exception as e:
            logger.error(f"Error creating OpenVPN config: {e}")
            raise VpnConfigurationError(f"Failed to create OpenVPN config: {e}")
    
    async def delete_config(self, config_id: int) -> bool:
        """Удалить OpenVPN конфигурацию"""
        try:
            config = await self.repos.vpn_configs.get_by_id(config_id)
            if not config:
                return False
            
            # Отзываем сертификат клиента
            client_cert = config.config_data.get("client_cert")
            if client_cert:
                await self.cert_service.revoke_certificate(client_cert)
            
            # Деактивируем конфигурацию
            success = await self.deactivate_config(config_id)
            
            # Удаляем файлы
            if config.qr_code_path and os.path.exists(config.qr_code_path):
                os.remove(config.qr_code_path)
            
            await self.log_config_action(config_id, "config_deleted")
            return success
            
        except Exception as e:
            logger.error(f"Error deleting OpenVPN config {config_id}: {e}")
            return False
    
    async def get_connection_string(self, config_id: int) -> str:
        """Получить .ovpn конфигурацию"""
        try:
            config = await self.repos.vpn_configs.get_by_id(config_id)
            if not config or not config.is_active:
                return ""
            
            return config.connection_string
            
        except Exception as e:
            logger.error(f"Error getting OpenVPN connection string: {e}")
            return ""
    
    async def get_config_data(self, config_id: int) -> Dict[str, Any]:
        """Получить данные конфигурации"""
        try:
            config = await self.repos.vpn_configs.get_by_id(config_id)
            return config.config_data if config else {}
        except Exception as e:
            logger.error(f"Error getting OpenVPN config data: {e}")
            return {}
    
    async def update_config(self, config_id: int, params: Dict[str, Any]) -> bool:
        """Обновить конфигурацию"""
        try:
            config = await self.repos.vpn_configs.get_by_id(config_id)
            if not config:
                return False
            
            # Обновляем данные
            updated_config_data = config.config_data.copy()
            updated_config_data.update(params)
            
            # Если изменились критичные параметры - перегенерируем .ovpn
            critical_params = ['remote', 'port', 'proto', 'cipher']
            if any(param in params for param in critical_params):
                ovpn_content = await self._generate_ovpn_config(updated_config_data)
                
                success = await self.repos.vpn_configs.update(
                    config_id,
                    config_data=updated_config_data,
                    connection_string=ovpn_content
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
            logger.error(f"Error updating OpenVPN config: {e}")
            return False
    
    async def get_usage_stats(self, config_id: int) -> Dict[str, Any]:
        """Получить статистику использования"""
        try:
            config = await self.repos.vpn_configs.get_by_id(config_id)
            if not config:
                return {}
            
            # OpenVPN статистика обычно получается из логов сервера
            # Пока возвращаем базовую информацию из БД
            return {
                "total_gb": float(config.total_traffic_gb),
                "last_used": config.last_used.isoformat() if config.last_used else None,
                "active": config.is_active,
                "protocol": "OpenVPN"
            }
            
        except Exception as e:
            logger.error(f"Error getting OpenVPN usage stats: {e}")
            return {}
    
    async def test_connection(self, config_id: int) -> bool:
        """Тестировать OpenVPN соединение"""
        try:
            config = await self.repos.vpn_configs.get_by_id(config_id)
            if not config or not config.is_active:
                return False
            
            # Проверяем доступность сервера
            remote = config.config_data.get("remote")
            port = config.config_data.get("port", 1194)
            
            from core.utils.helpers import test_network_connectivity
            return await test_network_connectivity(remote, port)
            
        except Exception as e:
            logger.error(f"Error testing OpenVPN connection: {e}")
            return False
    
    async def _generate_ovpn_config(self, config_data: Dict[str, Any]) -> str:
        """Генерировать .ovpn файл"""
        try:
            ovpn_lines = [
                "client",
                "dev tun",
                "proto " + config_data.get("proto", "udp"),
                "remote " + config_data["remote"] + " " + str(config_data.get("port", 1194)),
                "resolv-retry infinite",
                "nobind",
                "persist-key",
                "persist-tun",
                "cipher " + config_data.get("cipher", "AES-256-GCM"),
                "auth " + config_data.get("auth", "SHA256"),
                "verb 3"
            ]
            
            # Добавляем сертификаты
            if config_data.get("ca_cert"):
                ovpn_lines.extend([
                    "<ca>",
                    config_data["ca_cert"],
                    "</ca>"
                ])
            
            if config_data.get("client_cert"):
                ovpn_lines.extend([
                    "<cert>",
                    config_data["client_cert"],
                    "</cert>"
                ])
            
            if config_data.get("client_key"):
                ovpn_lines.extend([
                    "<key>",
                    config_data["client_key"],
                    "</key>"
                ])
            
            if config_data.get("ta_key"):
                ovpn_lines.extend([
                    "<tls-auth>",
                    config_data["ta_key"],
                    "</tls-auth>",
                    "key-direction 1"
                ])
            
            return "\n".join(ovpn_lines)
            
        except Exception as e:
            logger.error(f"Error generating .ovpn config: {e}")
            return ""