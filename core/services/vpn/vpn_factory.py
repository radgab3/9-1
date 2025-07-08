"""
Фабрика VPN сервисов для создания экземпляров различных протоколов
"""

from typing import Dict, Type, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from core.database.models import Server, VpnProtocol
from core.services.vpn.base_vpn_service import BaseVpnService
from core.exceptions.vpn_exceptions import VpnProtocolNotSupportedError


class VpnServiceFactory:
    """
    Фабрика для создания сервисов VPN протоколов
    """
    
    _services: Dict[VpnProtocol, Type[BaseVpnService]] = {}
    
    @classmethod
    def register_service(cls, protocol: VpnProtocol, service_class: Type[BaseVpnService]):
        """
        Регистрировать сервис для протокола
        
        Args:
            protocol: VPN протокол
            service_class: Класс сервиса
        """
        cls._services[protocol] = service_class
        logger.info(f"Registered VPN service for protocol: {protocol.value}")
    
    @classmethod
    def get_service(
        cls, 
        protocol: VpnProtocol, 
        session: AsyncSession, 
        server: Server
    ) -> BaseVpnService:
        """
        Получить сервис для протокола
        
        Args:
            protocol: VPN протокол
            session: Сессия базы данных
            server: Сервер
            
        Returns:
            BaseVpnService: Экземпляр сервиса
            
        Raises:
            VpnProtocolNotSupportedError: Если протокол не поддерживается
        """
        if protocol not in cls._services:
            raise VpnProtocolNotSupportedError(f"Protocol {protocol.value} not supported")
        
        service_class = cls._services[protocol]
        return service_class(session, server)
    
    @classmethod
    def get_supported_protocols(cls) -> list[VpnProtocol]:
        """
        Получить список поддерживаемых протоколов
        
        Returns:
            list[VpnProtocol]: Список протоколов
        """
        return list(cls._services.keys())
    
    @classmethod
    def is_protocol_supported(cls, protocol: VpnProtocol) -> bool:
        """
        Проверить поддержку протокола
        
        Args:
            protocol: VPN протокол
            
        Returns:
            bool: Поддерживается ли протокол
        """
        return protocol in cls._services


class VpnServiceManager:
    """
    Менеджер VPN сервисов для работы с множественными протоколами
    """
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self._service_cache: Dict[str, BaseVpnService] = {}
    
    def get_service(self, protocol: VpnProtocol, server: Server) -> BaseVpnService:
        """
        Получить сервис с кешированием
        
        Args:
            protocol: VPN протокол
            server: Сервер
            
        Returns:
            BaseVpnService: Экземпляр сервиса
        """
        cache_key = f"{protocol.value}_{server.id}"
        
        if cache_key not in self._service_cache:
            self._service_cache[cache_key] = VpnServiceFactory.get_service(
                protocol, self.session, server
            )
        
        return self._service_cache[cache_key]
    
    async def create_config_for_best_protocol(
        self,
        server: Server,
        subscription_id: int,
        preferred_protocol: Optional[VpnProtocol] = None,
        client_name: Optional[str] = None
    ):
        """
        Создать конфигурацию для лучшего доступного протокола
        
        Args:
            server: Сервер
            subscription_id: ID подписки
            preferred_protocol: Предпочитаемый протокол
            client_name: Имя клиента
            
        Returns:
            VpnConfig: Созданная конфигурация
        """
        try:
            # Определяем приоритет протоколов
            protocols_priority = self._get_protocols_priority(server, preferred_protocol)
            
            last_error = None
            for protocol in protocols_priority:
                try:
                    service = self.get_service(protocol, server)
                    
                    # Проверяем валидность конфигурации сервера
                    if not await service.validate_server_config():
                        continue
                    
                    # Создаем конфигурацию
                    config = await service.create_config(
                        subscription_id=subscription_id,
                        client_name=client_name
                    )
                    
                    logger.info(f"Config created with protocol {protocol.value}")
                    return config
                    
                except Exception as e:
                    last_error = e
                    logger.warning(f"Failed to create config with {protocol.value}: {e}")
                    continue
            
            # Если все протоколы не сработали
            raise Exception(f"Failed to create config with any protocol. Last error: {last_error}")
            
        except Exception as e:
            logger.error(f"Error creating config for best protocol: {e}")
            raise
    
    def _get_protocols_priority(
        self, 
        server: Server, 
        preferred_protocol: Optional[VpnProtocol] = None
    ) -> list[VpnProtocol]:
        """
        Получить приоритет протоколов для сервера
        
        Args:
            server: Сервер
            preferred_protocol: Предпочитаемый протокол
            
        Returns:
            list[VpnProtocol]: Список протоколов в порядке приоритета
        """
        available_protocols = []
        
        # Добавляем поддерживаемые сервером протоколы
        for protocol_str in server.supported_protocols:
            try:
                protocol = VpnProtocol(protocol_str)
                if VpnServiceFactory.is_protocol_supported(protocol):
                    available_protocols.append(protocol)
            except ValueError:
                logger.warning(f"Unknown protocol in server config: {protocol_str}")
        
        # Сортируем по приоритету (убрали VMESS и TROJAN)
        priority_order = [
            VpnProtocol.VLESS,    # Приоритет для российских пользователей
            VpnProtocol.OPENVPN,  # Классический протокол
            VpnProtocol.WIREGUARD # Быстрый протокол
        ]
        
        # Если есть предпочитаемый протокол, ставим его первым
        if preferred_protocol and preferred_protocol in available_protocols:
            protocols = [preferred_protocol]
            protocols.extend([p for p in priority_order if p != preferred_protocol and p in available_protocols])
            return protocols
        
        # Иначе используем стандартный приоритет
        return [p for p in priority_order if p in available_protocols]
    
    async def migrate_config(
        self,
        config_id: int,
        target_server: Server,
        target_protocol: Optional[VpnProtocol] = None
    ):
        """
        Мигрировать конфигурацию на другой сервер/протокол
        
        Args:
            config_id: ID конфигурации
            target_server: Целевой сервер
            target_protocol: Целевой протокол (опционально)
            
        Returns:
            VpnConfig: Новая конфигурация
        """
        try:
            from core.database.repositories import RepositoryManager
            repos = RepositoryManager(self.session)
            
            # Получаем старую конфигурацию
            old_config = await repos.vpn_configs.get_by_id(config_id)
            if not old_config:
                raise ValueError(f"Config {config_id} not found")
            
            # Определяем протокол для миграции
            migration_protocol = target_protocol or old_config.protocol
            
            # Создаем новую конфигурацию
            new_config = await self.create_config_for_best_protocol(
                server=target_server,
                subscription_id=old_config.subscription_id,
                preferred_protocol=migration_protocol,
                client_name=old_config.client_id
            )
            
            # Деактивируем старую конфигурацию
            old_service = self.get_service(old_config.protocol, old_config.server)
            await old_service.delete_config(config_id)
            
            logger.info(f"Config migrated from {old_config.server.id} to {target_server.id}")
            return new_config
            
        except Exception as e:
            logger.error(f"Error migrating config {config_id}: {e}")
            raise
    
    async def get_server_protocols_status(self, server: Server) -> Dict[str, Dict[str, Any]]:
        """
        Получить статус протоколов на сервере
        
        Args:
            server: Сервер
            
        Returns:
            Dict[str, Dict[str, Any]]: Статус каждого протокола
        """
        status = {}
        
        for protocol_str in server.supported_protocols:
            try:
                protocol = VpnProtocol(protocol_str)
                
                if not VpnServiceFactory.is_protocol_supported(protocol):
                    status[protocol_str] = {
                        "supported": False,
                        "available": False,
                        "error": "Protocol not implemented"
                    }
                    continue
                
                service = self.get_service(protocol, server)
                
                # Проверяем доступность протокола
                is_valid = await service.validate_server_config()
                has_capacity = await service.check_server_capacity()
                
                status[protocol_str] = {
                    "supported": True,
                    "available": is_valid and has_capacity,
                    "valid_config": is_valid,
                    "has_capacity": has_capacity,
                    "load_info": await service.get_server_load()
                }
                
            except Exception as e:
                status[protocol_str] = {
                    "supported": False,
                    "available": False,
                    "error": str(e)
                }
        
        return status
    
    def clear_cache(self):
        """Очистить кеш сервисов"""
        self._service_cache.clear()
        logger.info("VPN services cache cleared")


# Автоматическая регистрация сервисов при импорте модулей
def register_all_services():
    """
    Регистрация всех доступных VPN сервисов
    """
    try:
        # Регистрируем VLESS сервис
        from core.services.vpn.vless.vless_service import VlessService
        VpnServiceFactory.register_service(VpnProtocol.VLESS, VlessService)
        
        # Регистрируем OpenVPN (если доступен)
        try:
            from core.services.vpn.openvpn.openvpn_service import OpenVpnService
            VpnServiceFactory.register_service(VpnProtocol.OPENVPN, OpenVpnService)
        except ImportError:
            logger.info("OpenVPN service not available")
        
        # Регистрируем WireGuard (если доступен)
        try:
            from core.services.vpn.wireguard.wireguard_service import WireguardService
            VpnServiceFactory.register_service(VpnProtocol.WIREGUARD, WireguardService)
        except ImportError:
            logger.info("WireGuard service not available")
            
        logger.info(f"Registered {len(VpnServiceFactory._services)} VPN services")
        
    except Exception as e:
        logger.error(f"Error registering VPN services: {e}")


# Инициализация при импорте
register_all_services()