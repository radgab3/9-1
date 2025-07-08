"""
Сервис для интеграции с 3X-UI панелью
"""

import aiohttp
import asyncio
import json
from typing import Dict, Any, Optional, List
from datetime import datetime
from loguru import logger

from core.database.models import Server
from core.exceptions.vpn_exceptions import VpnConnectionError, VpnConfigurationError
from config.settings import vpn_settings


class X3UIService:
    """
    Сервис для работы с 3X-UI панелью управления
    """
    
    def __init__(self, server: Server):
        self.server = server
        self.base_url = self._get_base_url()
        self.session_cookie = None
        self.login_time = None
        
        # Настройки подключения
        self.timeout = aiohttp.ClientTimeout(total=30)
        self.max_retries = 3
        self.retry_delay = 1
    
    def _get_base_url(self) -> str:
        """Получить базовый URL для 3X-UI"""
        domain = self.server.domain or self.server.ip_address
        port = self.server.vless_config.get("x3ui_port", vpn_settings.X3UI_DEFAULT_PORT)
        return f"https://{domain}:{port}"
    
    def _get_credentials(self) -> tuple[str, str]:
        """Получить учетные данные для 3X-UI"""
        config = self.server.vless_config or {}
        username = config.get("x3ui_username", vpn_settings.X3UI_USERNAME)
        password = config.get("x3ui_password", vpn_settings.X3UI_PASSWORD)
        return username, password
    
    async def _ensure_authenticated(self) -> bool:
        """
        Убедиться что сессия аутентифицирована
        
        Returns:
            bool: Успешность аутентификации
        """
        try:
            # Проверяем валидность существующей сессии
            if self.session_cookie and self.login_time:
                time_since_login = (datetime.utcnow() - self.login_time).total_seconds()
                if time_since_login < 3600:  # Сессия валидна 1 час
                    return True
            
            # Выполняем новую аутентификацию
            return await self._login()
            
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return False
    
    async def _login(self) -> bool:
        """
        Войти в 3X-UI панель
        
        Returns:
            bool: Успешность входа
        """
        try:
            username, password = self._get_credentials()
            
            login_data = {
                "username": username,
                "password": password
            }
            
            async with aiohttp.ClientSession(
                timeout=self.timeout,
                connector=aiohttp.TCPConnector(ssl=False)
            ) as session:
                
                async with session.post(
                    f"{self.base_url}/login",
                    data=login_data
                ) as response:
                    
                    if response.status == 200:
                        # Извлекаем cookie сессии
                        cookies = response.cookies
                        if 'session' in cookies or '3x-ui' in cookies:
                            self.session_cookie = dict(response.cookies)
                            self.login_time = datetime.utcnow()
                            logger.info(f"Successfully logged into 3X-UI: {self.server.id}")
                            return True
                    
                    logger.error(f"3X-UI login failed: {response.status}")
                    return False
                    
        except Exception as e:
            logger.error(f"3X-UI login error: {e}")
            return False
    
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Выполнить HTTP запрос к 3X-UI API
        
        Args:
            method: HTTP метод
            endpoint: Конечная точка API
            data: Данные для отправки
            params: Параметры запроса
            
        Returns:
            Optional[Dict[str, Any]]: Ответ API
        """
        for attempt in range(self.max_retries):
            try:
                # Убеждаемся что аутентифицированы
                if not await self._ensure_authenticated():
                    raise VpnConnectionError("Failed to authenticate with 3X-UI")
                
                url = f"{self.base_url}{endpoint}"
                
                async with aiohttp.ClientSession(
                    timeout=self.timeout,
                    cookies=self.session_cookie,
                    connector=aiohttp.TCPConnector(ssl=False)
                ) as session:
                    
                    request_kwargs = {
                        "url": url,
                        "params": params
                    }
                    
                    if data is not None:
                        if method.upper() == "POST":
                            request_kwargs["json"] = data
                        else:
                            request_kwargs["data"] = data
                    
                    async with session.request(method, **request_kwargs) as response:
                        
                        if response.status == 401:
                            # Сессия истекла, повторяем аутентификацию
                            self.session_cookie = None
                            self.login_time = None
                            continue
                        
                        if response.status == 200:
                            try:
                                return await response.json()
                            except:
                                return {"success": True, "data": await response.text()}
                        
                        logger.warning(f"3X-UI request failed: {response.status} - {await response.text()}")
                        return None
                        
            except Exception as e:
                logger.error(f"3X-UI request error (attempt {attempt + 1}): {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                continue
        
        return None
    
    async def test_connection(self) -> bool:
        """
        Тестировать подключение к 3X-UI
        
        Returns:
            bool: Доступность 3X-UI
        """
        try:
            response = await self._make_request("GET", "/server/status")
            return response is not None
            
        except Exception as e:
            logger.error(f"3X-UI connection test failed: {e}")
            return False
    
    async def get_server_info(self) -> Optional[Dict[str, Any]]:
        """
        Получить информацию о сервере
        
        Returns:
            Optional[Dict[str, Any]]: Информация о сервере
        """
        try:
            response = await self._make_request("GET", "/server/status")
            if response and response.get("success"):
                return response.get("obj", {})
            return None
            
        except Exception as e:
            logger.error(f"Error getting server info: {e}")
            return None
    
    async def create_client(
        self,
        email: str,
        uuid: str,
        flow: str = "xtls-rprx-vision",
        limit_ip: int = 1,
        total_gb: int = 0,
        expiry_time: int = 0,
        enable: bool = True,
        tgId: str = "",
        subId: str = "",
        reset: int = 0
    ) -> Optional[Dict[str, Any]]:
        """
        Создать клиента VLESS
        
        Args:
            email: Email клиента
            uuid: UUID клиента
            flow: Поток VLESS
            limit_ip: Лимит IP адресов
            total_gb: Лимит трафика в байтах
            expiry_time: Время истечения (timestamp)
            enable: Включен ли клиент
            tgId: Telegram ID
            subId: ID подписки
            reset: Сброс статистики
            
        Returns:
            Optional[Dict[str, Any]]: Информация о созданном клиенте
        """
        try:
            # Получаем ID инбаунда VLESS
            inbound_id = await self._get_vless_inbound_id()
            if not inbound_id:
                raise VpnConfigurationError("VLESS inbound not found")
            
            client_data = {
                "id": inbound_id,
                "settings": json.dumps({
                    "clients": [{
                        "id": uuid,
                        "email": email,
                        "limitIp": limit_ip,
                        "totalGB": total_gb,
                        "expiryTime": expiry_time,
                        "enable": enable,
                        "tgId": tgId,
                        "subId": subId,
                        "reset": reset,
                        "flow": flow
                    }]
                })
            }
            
            response = await self._make_request("POST", "/panel/inbound/addClient", client_data)
            
            if response and response.get("success"):
                logger.info(f"3X-UI client created: {email}")
                return {
                    "id": uuid,
                    "email": email,
                    "inbound_id": inbound_id,
                    "success": True
                }
            
            logger.error(f"Failed to create 3X-UI client: {response}")
            return None
            
        except Exception as e:
            logger.error(f"Error creating 3X-UI client: {e}")
            return None
    
    async def delete_client(self, client_uuid: str) -> bool:
        """
        Удалить клиента
        
        Args:
            client_uuid: UUID клиента
            
        Returns:
            bool: Успешность удаления
        """
        try:
            # Получаем ID инбаунда
            inbound_id = await self._get_vless_inbound_id()
            if not inbound_id:
                return False
            
            delete_data = {
                "id": inbound_id,
                "uuid": client_uuid
            }
            
            response = await self._make_request("POST", f"/panel/inbound/{inbound_id}/delClient", delete_data)
            
            if response and response.get("success"):
                logger.info(f"3X-UI client deleted: {client_uuid}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error deleting 3X-UI client: {e}")
            return False
    
    async def update_client(self, client_uuid: str, params: Dict[str, Any]) -> bool:
        """
        Обновить клиента
        
        Args:
            client_uuid: UUID клиента
            params: Параметры для обновления
            
        Returns:
            bool: Успешность обновления
        """
        try:
            inbound_id = await self._get_vless_inbound_id()
            if not inbound_id:
                return False
            
            # Получаем текущую информацию о клиенте
            client_info = await self.get_client_info(client_uuid)
            if not client_info:
                return False
            
            # Обновляем параметры
            updated_client = client_info.copy()
            updated_client.update(params)
            
            update_data = {
                "id": inbound_id,
                "uuid": client_uuid,
                "settings": json.dumps({
                    "clients": [updated_client]
                })
            }
            
            response = await self._make_request("POST", f"/panel/inbound/{inbound_id}/updateClient", update_data)
            
            if response and response.get("success"):
                logger.info(f"3X-UI client updated: {client_uuid}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error updating 3X-UI client: {e}")
            return False
    
    async def get_client_info(self, client_uuid: str) -> Optional[Dict[str, Any]]:
        """
        Получить информацию о клиенте
        
        Args:
            client_uuid: UUID клиента
            
        Returns:
        Optional[Dict[str, Any]]: Информация о клиенте
        """
        try:
            # Получаем ID инбаунда
            inbound_id = await self._get_vless_inbound_id()
            if not inbound_id:
                return None
            
            # Получаем информацию об инбаунде
            response = await self._make_request("GET", f"/panel/inbound/get/{inbound_id}")
            
            if response and response.get("success"):
                inbound_data = response.get("obj", {})
                settings = inbound_data.get("settings", "{}")
                
                try:
                    settings_data = json.loads(settings)
                    clients = settings_data.get("clients", [])
                    
                    # Ищем клиента по UUID
                    for client in clients:
                        if client.get("id") == client_uuid:
                            return client
                    
                except json.JSONDecodeError:
                    logger.error("Failed to parse inbound settings")
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting client info: {e}")
            return None
    
    async def get_all_clients(self) -> List[Dict[str, Any]]:
        """
        Получить всех клиентов VLESS инбаунда
        
        Returns:
            List[Dict[str, Any]]: Список клиентов
        """
        try:
            inbound_id = await self._get_vless_inbound_id()
            if not inbound_id:
                return []
            
            response = await self._make_request("GET", f"/panel/inbound/get/{inbound_id}")
            
            if response and response.get("success"):
                inbound_data = response.get("obj", {})
                settings = inbound_data.get("settings", "{}")
                
                try:
                    settings_data = json.loads(settings)
                    return settings_data.get("clients", [])
                except json.JSONDecodeError:
                    logger.error("Failed to parse inbound settings")
            
            return []
            
        except Exception as e:
            logger.error(f"Error getting all clients: {e}")
            return []
    
    async def get_client_traffic_stats(self, client_email: str) -> Optional[Dict[str, Any]]:
        """
        Получить статистику трафика клиента
        
        Args:
            client_email: Email клиента
            
        Returns:
            Optional[Dict[str, Any]]: Статистика трафика
        """
        try:
            response = await self._make_request("GET", f"/panel/inbound/clientStat/{client_email}")
            
            if response and response.get("success"):
                return response.get("obj", {})
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting client traffic stats: {e}")
            return None
    
    async def reset_client_traffic(self, inbound_id: int, client_email: str) -> bool:
        """
        Сбросить статистику трафика клиента
        
        Args:
            inbound_id: ID инбаунда
            client_email: Email клиента
            
        Returns:
            bool: Успешность сброса
        """
        try:
            reset_data = {
                "id": inbound_id,
                "email": client_email
            }
            
            response = await self._make_request("POST", "/panel/inbound/resetClientTraffic", reset_data)
            
            if response and response.get("success"):
                logger.info(f"Traffic reset for client: {client_email}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error resetting client traffic: {e}")
            return False
    
    async def enable_client(self, client_uuid: str) -> bool:
        """
        Включить клиента
        
        Args:
            client_uuid: UUID клиента
            
        Returns:
            bool: Успешность включения
        """
        try:
            return await self.update_client(client_uuid, {"enable": True})
        except Exception as e:
            logger.error(f"Error enabling client: {e}")
            return False
    
    async def disable_client(self, client_uuid: str) -> bool:
        """
        Отключить клиента
        
        Args:
            client_uuid: UUID клиента
            
        Returns:
            bool: Успешность отключения
        """
        try:
            return await self.update_client(client_uuid, {"enable": False})
        except Exception as e:
            logger.error(f"Error disabling client: {e}")
            return False
    
    async def _get_vless_inbound_id(self) -> Optional[int]:
        """
        Получить ID VLESS инбаунда
        
        Returns:
            Optional[int]: ID инбаунда или None
        """
        try:
            response = await self._make_request("GET", "/panel/inbound/list")
            
            if response and response.get("success"):
                inbounds = response.get("obj", [])
                
                # Ищем VLESS инбаунд
                for inbound in inbounds:
                    if inbound.get("protocol") == "vless":
                        return inbound.get("id")
                
                # Если VLESS инбаунд не найден, создаем его
                logger.info("VLESS inbound not found, creating new one")
                return await self._create_vless_inbound()
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting VLESS inbound ID: {e}")
            return None
    
    async def _create_vless_inbound(self) -> Optional[int]:
        """
        Создать VLESS инбаунд
        
        Returns:
            Optional[int]: ID созданного инбаунда
        """
        try:
            vless_config = self.server.vless_config or {}
            
            # Базовая конфигурация VLESS инбаунда
            inbound_data = {
                "remark": f"VLESS-{self.server.name}",
                "enable": True,
                "protocol": "vless",
                "port": vless_config.get("port", 443),
                "settings": json.dumps({
                    "clients": [],
                    "decryption": "none",
                    "fallbacks": []
                }),
                "streamSettings": json.dumps({
                    "network": vless_config.get("network", "tcp"),
                    "security": vless_config.get("security", "reality"),
                    "realitySettings": {
                        "serverNames": vless_config.get("reality", {}).get("server_names", ["microsoft.com"]),
                        "privateKey": vless_config.get("reality", {}).get("private_key", ""),
                        "publicKey": vless_config.get("reality", {}).get("public_key", ""),
                        "shortIds": vless_config.get("reality", {}).get("short_ids", [""]),
                        "fingerprint": vless_config.get("reality", {}).get("finger_print", "chrome")
                    }
                }),
                "sniffing": json.dumps({
                    "enabled": True,
                    "destOverride": ["http", "tls"]
                })
            }
            
            response = await self._make_request("POST", "/panel/inbound/add", inbound_data)
            
            if response and response.get("success"):
                # Получаем ID созданного инбаунда
                return await self._get_vless_inbound_id()
            
            return None
            
        except Exception as e:
            logger.error(f"Error creating VLESS inbound: {e}")
            return None
    
    async def get_inbound_list(self) -> List[Dict[str, Any]]:
        """
        Получить список всех инбаундов
        
        Returns:
            List[Dict[str, Any]]: Список инбаундов
        """
        try:
            response = await self._make_request("GET", "/panel/inbound/list")
            
            if response and response.get("success"):
                return response.get("obj", [])
            
            return []
            
        except Exception as e:
            logger.error(f"Error getting inbound list: {e}")
            return []
    
    async def get_inbound_stats(self, inbound_id: int) -> Optional[Dict[str, Any]]:
        """
        Получить статистику инбаунда
        
        Args:
            inbound_id: ID инбаунда
            
        Returns:
            Optional[Dict[str, Any]]: Статистика инбаунда
        """
        try:
            response = await self._make_request("GET", f"/panel/inbound/get/{inbound_id}")
            
            if response and response.get("success"):
                inbound_data = response.get("obj", {})
                return {
                    "up": inbound_data.get("up", 0),
                    "down": inbound_data.get("down", 0),
                    "total": inbound_data.get("total", 0),
                    "enable": inbound_data.get("enable", False),
                    "client_count": len(self._parse_clients_from_settings(inbound_data.get("settings", "{}")))
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting inbound stats: {e}")
            return None
    
    def _parse_clients_from_settings(self, settings_json: str) -> List[Dict[str, Any]]:
        """
        Парсить клиентов из настроек инбаунда
        
        Args:
            settings_json: JSON строка с настройками
            
        Returns:
            List[Dict[str, Any]]: Список клиентов
        """
        try:
            settings = json.loads(settings_json)
            return settings.get("clients", [])
        except json.JSONDecodeError:
            return []
    
    async def backup_configs(self) -> Optional[Dict[str, Any]]:
        """
        Создать резервную копию конфигураций
        
        Returns:
            Optional[Dict[str, Any]]: Данные резервной копии
        """
        try:
            response = await self._make_request("GET", "/panel/setting/all")
            
            if response and response.get("success"):
                backup_data = response.get("obj", {})
                return backup_data
            
            return None
            
        except Exception as e:
            logger.error(f"Error creating backup: {e}")
            return None