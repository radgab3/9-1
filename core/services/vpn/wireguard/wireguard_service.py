"""
Сервис для работы с WireGuard протоколом
"""

import ipaddress
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from core.database.models import Server, VpnConfig, VpnProtocol
from core.services.vpn.base_vpn_service import BaseVpnService, VpnServiceMixin
from core.services.vpn.wireguard.key_service import WireGuardKeyService
from core.exceptions.vpn_exceptions import VpnConfigurationError
from config.settings import vpn_settings


class WireguardService(BaseVpnService, VpnServiceMixin):
    """Сервис для работы с WireGuard протоколом"""
    
    def __init__(self, session: AsyncSession, server: Server):
        super().__init__(session, server)
        self.key_service = WireGuardKeyService()
        
    def get_protocol(self) -> VpnProtocol:
        """Получить протокол сервиса"""
        return VpnProtocol.WIREGUARD
    
    async def create_config(
        self, 
        subscription_id: int, 
        client_name: Optional[str] = None,
        additional_params: Optional[Dict[str, Any]] = None
    ) -> VpnConfig:
        """Создать WireGuard конфигурацию"""
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
            wg_config = self.server.wireguard_config or {}
            
            # Генерируем ключи для клиента
            client_keys = await self.key_service.generate_keypair()
            
            # Выделяем IP адрес клиенту
            client_ip = await self._allocate_client_ip(subscription_id)
            
            # Формируем данные конфигурации
            config_data = {
                "client_name": client_name,
                "client_id": client_id,
                "private_key": client_keys["private_key"],
                "public_key": client_keys["public_key"],
                "client_ip": client_ip,
                "server_public_key": wg_config.get("server_public_key"),
                "server_endpoint": f"{self.server.domain or self.server.ip_address}:{wg_config.get('port', vpn_settings.WIREGUARD_PORT)}",
                "allowed_ips": wg_config.get("allowed_ips", "0.0.0.0/0"),
                "dns": wg_config.get("dns", "1.1.1.1, 8.8.8.8"),
                "persistent_keepalive": wg_config.get("keepalive", 25)
            }
            
            # Генерируем .conf файл
            wg_content = await self._generate_wg_config(config_data)
            
            # Создаем базовую конфигурацию
            vpn_config = await self.create_base_config(
                subscription_id=subscription_id,
                protocol_specific_data=config_data,
                connection_string=wg_content,
                client_id=client_id
            )
            
            # Генерируем QR код
            qr_path = await self.generate_qr_code(wg_content, vpn_config.id)
            if qr_path:
                await self.repos.vpn_configs.update(
                    vpn_config.id,
                    qr_code_path=qr_path,
                    qr_code_data=wg_content
                )
            
            logger.info(f"WireGuard config created: {vpn_config.id}")
            return vpn_config
            
        except Exception as e:
            logger.error(f"Error creating WireGuard config: {e}")
            raise VpnConfigurationError(f"Failed to create WireGuard config: {e}")
    
    async def delete_config(self, config_id: int) -> bool:
        """Удалить WireGuard конфигурацию"""
        try:
            config = await self.repos.vpn_configs.get_by_id(config_id)
            if not config:
                return False
            
            # Освобождаем IP адрес
            client_ip = config.config_data.get("client_ip")
            if client_ip:
                await self._release_client_ip(client_ip)
            
            # Деактивируем конфигурацию
            success = await self.deactivate_config(config_id)
            
            # Удаляем QR код
            if config.qr_code_path:
                import os
                if os.path.exists(config.qr_code_path):
                    os.remove(config.qr_code_path)
            
            await self.log_config_action(config_id, "config_deleted")
            return success
            
        except Exception as e:
            logger.error(f"Error deleting WireGuard config {config_id}: {e}")
            return False
    
    async def get_connection_string(self, config_id: int) -> str:
        """Получить .conf конфигурацию"""
        try:
            config = await self.repos.vpn_configs.get_by_id(config_id)
            if not config or not config.is_active:
                return ""
            
            return config.connection_string
            
        except Exception as e:
            logger.error(f"Error getting WireGuard connection string: {e}")
            return ""
    
    async def get_config_data(self, config_id: int) -> Dict[str, Any]:
        """Получить данные конфигурации"""
        try:
            config = await self.repos.vpn_configs.get_by_id(config_id)
            return config.config_data if config else {}
        except Exception as e:
            logger.error(f"Error getting WireGuard config data: {e}")
            return {}
    
    async def update_config(self, config_id: int, params: Dict[str, Any]) -> bool:
        """Обновить конфигурацию"""
        try:
            config = await self.repos.vpn_configs.get_by_id(config_id)
            if not config:
                return False
            
            updated_config_data = config.config_data.copy()
            updated_config_data.update(params)
            
            # Если изменились критичные параметры - перегенерируем .conf
            critical_params = ['server_endpoint', 'allowed_ips', 'dns']
            if any(param in params for param in critical_params):
                wg_content = await self._generate_wg_config(updated_config_data)
                
                success = await self.repos.vpn_configs.update(
                    config_id,
                    config_data=updated_config_data,
                    connection_string=wg_content
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
            logger.error(f"Error updating WireGuard config: {e}")
            return False
    
    async def get_usage_stats(self, config_id: int) -> Dict[str, Any]:
        """Получить статистику использования"""
        try:
            config = await self.repos.vpn_configs.get_by_id(config_id)
            if not config:
                return {}
            
            # WireGuard статистика получается через wg команды
            # Пока возвращаем базовую информацию
            return {
                "total_gb": float(config.total_traffic_gb),
                "last_used": config.last_used.isoformat() if config.last_used else None,
                "active": config.is_active,
                "protocol": "WireGuard",
                "client_ip": config.config_data.get("client_ip")
            }
            
        except Exception as e:
            logger.error(f"Error getting WireGuard usage stats: {e}")
            return {}
    
    async def test_connection(self, config_id: int) -> bool:
        """Тестировать WireGuard соединение"""
        try:
            config = await self.repos.vpn_configs.get_by_id(config_id)
            if not config or not config.is_active:
                return False
            
            # Проверяем доступность сервера
            endpoint = config.config_data.get("server_endpoint", "")
            if ":" in endpoint:
                host, port = endpoint.rsplit(":", 1)
                from core.utils.helpers import test_network_connectivity
                return await test_network_connectivity(host, int(port))
            
            return False
            
        except Exception as e:
            logger.error(f"Error testing WireGuard connection: {e}")
            return False
    
    async def _generate_wg_config(self, config_data: Dict[str, Any]) -> str:
        """Генерировать .conf файл WireGuard"""
        try:
            wg_lines = [
                "[Interface]",
                f"PrivateKey = {config_data['private_key']}",
                f"Address = {config_data['client_ip']}/32",
                f"DNS = {config_data.get('dns', '1.1.1.1, 8.8.8.8')}",
                "",
                "[Peer]",
                f"PublicKey = {config_data['server_public_key']}",
                f"Endpoint = {config_data['server_endpoint']}",
                f"AllowedIPs = {config_data.get('allowed_ips', '0.0.0.0/0')}",
                f"PersistentKeepalive = {config_data.get('persistent_keepalive', 25)}"
            ]
            
            return "\n".join(wg_lines)
            
        except Exception as e:
            logger.error(f"Error generating WireGuard config: {e}")
            return ""
    
    async def _allocate_client_ip(self, subscription_id: int) -> str:
        """Выделить IP адрес клиенту"""
        try:
            wg_config = self.server.wireguard_config or {}
            network = wg_config.get("client_network", vpn_settings.WIREGUARD_NETWORK)
            
            # Простая логика выделения IP - используем subscription_id
            net = ipaddress.ip_network(network)
            
            # Пропускаем сетевой адрес и адрес сервера (обычно .1)
            client_num = (subscription_id % (net.num_addresses - 10)) + 10
            client_ip = str(net.network_address + client_num)
            
            return client_ip
            
        except Exception as e:
            logger.error(f"Error allocating client IP: {e}")
            return "10.0.0.100"  # Fallback IP
    
    async def _release_client_ip(self, client_ip: str):
        """Освободить IP адрес клиента"""
        # В полной реализации здесь было бы управление пулом IP
        logger.info(f"Released client IP: {client_ip}")
        pass