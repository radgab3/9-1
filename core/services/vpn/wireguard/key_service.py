"""
Сервис управления ключами для WireGuard
"""

import base64
import secrets
from typing import Dict, Any, Optional
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives import serialization
from loguru import logger


class WireGuardKeyService:
    """Сервис для управления WireGuard ключами"""
    
    def __init__(self):
        self.key_size = 32  # WireGuard использует 32-байтовые ключи
    
    async def generate_keypair(self) -> Dict[str, str]:
        """
        Генерировать пару ключей WireGuard (приватный/публичный)
        
        Returns:
            Dict[str, str]: Приватный и публичный ключи
        """
        try:
            # Генерируем X25519 ключи для WireGuard
            private_key = x25519.X25519PrivateKey.generate()
            public_key = private_key.public_key()
            
            # Получаем сырые байты ключей
            private_bytes = private_key.private_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PrivateFormat.Raw,
                encryption_algorithm=serialization.NoEncryption()
            )
            
            public_bytes = public_key.public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw
            )
            
            # WireGuard использует base64 кодирование
            private_key_b64 = base64.b64encode(private_bytes).decode('ascii')
            public_key_b64 = base64.b64encode(public_bytes).decode('ascii')
            
            logger.info("WireGuard keypair generated successfully")
            
            return {
                "private_key": private_key_b64,
                "public_key": public_key_b64
            }
            
        except Exception as e:
            logger.error(f"Error generating WireGuard keypair: {e}")
            raise
    
    async def generate_preshared_key(self) -> str:
        """
        Генерировать Preshared ключ для дополнительной безопасности
        
        Returns:
            str: Preshared ключ в base64
        """
        try:
            # Генерируем 32 случайных байта
            psk_bytes = secrets.token_bytes(32)
            
            # Кодируем в base64
            psk_b64 = base64.b64encode(psk_bytes).decode('ascii')
            
            logger.info("WireGuard preshared key generated")
            return psk_b64
            
        except Exception as e:
            logger.error(f"Error generating preshared key: {e}")
            raise
    
    async def generate_server_keys(self) -> Dict[str, str]:
        """
        Генерировать ключи для WireGuard сервера
        
        Returns:
            Dict[str, str]: Серверные ключи и конфигурация
        """
        try:
            # Генерируем основную пару ключей сервера
            server_keys = await self.generate_keypair()
            
            # Генерируем preshared ключ
            preshared_key = await self.generate_preshared_key()
            
            logger.info("WireGuard server keys generated")
            
            return {
                "server_private_key": server_keys["private_key"],
                "server_public_key": server_keys["public_key"],
                "preshared_key": preshared_key
            }
            
        except Exception as e:
            logger.error(f"Error generating server keys: {e}")
            raise
    
    def validate_key(self, key: str) -> bool:
        """
        Валидировать WireGuard ключ
        
        Args:
            key: Ключ для валидации
            
        Returns:
            bool: Валидность ключа
        """
        try:
            # Проверяем base64 декодирование
            decoded = base64.b64decode(key)
            
            # WireGuard ключи должны быть 32 байта
            if len(decoded) != 32:
                return False
            
            return True
            
        except Exception:
            return False
    
    def derive_public_key(self, private_key: str) -> Optional[str]:
        """
        Вывести публичный ключ из приватного
        
        Args:
            private_key: Приватный ключ в base64
            
        Returns:
            Optional[str]: Публичный ключ или None
        """
        try:
            # Декодируем приватный ключ
            private_bytes = base64.b64decode(private_key)
            
            # Создаем объект приватного ключа
            private_key_obj = x25519.X25519PrivateKey.from_private_bytes(private_bytes)
            
            # Получаем публичный ключ
            public_key_obj = private_key_obj.public_key()
            
            # Кодируем в base64
            public_bytes = public_key_obj.public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw
            )
            
            return base64.b64encode(public_bytes).decode('ascii')
            
        except Exception as e:
            logger.error(f"Error deriving public key: {e}")
            return None
    
    async def rotate_server_keys(self, old_private_key: str) -> Dict[str, str]:
        """
        Ротация серверных ключей (генерация новых)
        
        Args:
            old_private_key: Старый приватный ключ сервера
            
        Returns:
            Dict[str, str]: Новые ключи сервера
        """
        try:
            logger.info("Rotating WireGuard server keys")
            
            # Генерируем новые ключи
            new_keys = await self.generate_server_keys()
            
            # Логируем ротацию (без вывода ключей)
            logger.info("Server keys rotated successfully")
            
            return new_keys
            
        except Exception as e:
            logger.error(f"Error rotating server keys: {e}")
            raise
    
    def generate_wg_quick_config(
        self,
        interface_config: Dict[str, Any],
        peer_configs: list[Dict[str, Any]]
    ) -> str:
        """
        Генерировать полную конфигурацию сервера для wg-quick
        
        Args:
            interface_config: Конфигурация интерфейса
            peer_configs: Список конфигураций пиров
            
        Returns:
            str: Конфигурация wg-quick
        """
        try:
            config_lines = ["[Interface]"]
            
            # Настройки интерфейса
            if "private_key" in interface_config:
                config_lines.append(f"PrivateKey = {interface_config['private_key']}")
            
            if "address" in interface_config:
                config_lines.append(f"Address = {interface_config['address']}")
            
            if "listen_port" in interface_config:
                config_lines.append(f"ListenPort = {interface_config['listen_port']}")
            
            if "post_up" in interface_config:
                config_lines.append(f"PostUp = {interface_config['post_up']}")
            
            if "post_down" in interface_config:
                config_lines.append(f"PostDown = {interface_config['post_down']}")
            
            # Добавляем пиров
            for peer in peer_configs:
                config_lines.extend(["", "[Peer]"])
                
                if "public_key" in peer:
                    config_lines.append(f"PublicKey = {peer['public_key']}")
                
                if "preshared_key" in peer:
                    config_lines.append(f"PresharedKey = {peer['preshared_key']}")
                
                if "allowed_ips" in peer:
                    config_lines.append(f"AllowedIPs = {peer['allowed_ips']}")
                
                if "endpoint" in peer:
                    config_lines.append(f"Endpoint = {peer['endpoint']}")
                
                if "persistent_keepalive" in peer:
                    config_lines.append(f"PersistentKeepalive = {peer['persistent_keepalive']}")
            
            return "\n".join(config_lines)
            
        except Exception as e:
            logger.error(f"Error generating wg-quick config: {e}")
            return ""
    
    def mask_key(self, key: str, visible_chars: int = 8) -> str:
        """
        Замаскировать ключ для логирования
        
        Args:
            key: Ключ для маскировки
            visible_chars: Количество видимых символов
            
        Returns:
            str: Замаскированный ключ
        """
        if len(key) <= visible_chars:
            return "*" * len(key)
        
        return f"{key[:visible_chars//2]}***{key[-visible_chars//2:]}"


# Глобальный экземпляр сервиса
wireguard_key_service = WireGuardKeyService()


async def generate_wg_keypair() -> Dict[str, str]:
    """
    Быстрая функция для генерации WireGuard ключей
    
    Returns:
        Dict[str, str]: Пара ключей
    """
    return await wireguard_key_service.generate_keypair()


async def generate_wg_preshared_key() -> str:
    """
    Быстрая функция для генерации preshared ключа
    
    Returns:
        str: Preshared ключ
    """
    return await wireguard_key_service.generate_preshared_key()


def validate_wg_key(key: str) -> bool:
    """
    Быстрая функция валидации WireGuard ключа
    
    Args:
        key: Ключ для валидации
        
    Returns:
        bool: Валидность ключа
    """
    return wireguard_key_service.validate_key(key)