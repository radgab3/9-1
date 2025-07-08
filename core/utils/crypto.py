"""
Криптографические утилиты для VPN Bot System
"""

import base64
import hashlib
import secrets
import uuid
from typing import Optional, Union, Dict, Any
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from loguru import logger

from config.settings import settings


class CryptoManager:
    """Менеджер криптографических операций"""
    
    def __init__(self):
        self.encryption_key = settings.ENCRYPTION_KEY.encode()
        self._fernet = None
    
    @property
    def fernet(self) -> Fernet:
        """Получить экземпляр Fernet для симметричного шифрования"""
        if self._fernet is None:
            # Создаем ключ из настроек
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=b'vpn_bot_salt',
                iterations=100000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(self.encryption_key))
            self._fernet = Fernet(key)
        
        return self._fernet
    
    def encrypt_data(self, data: Union[str, bytes]) -> str:
        """
        Зашифровать данные
        
        Args:
            data: Данные для шифрования
            
        Returns:
            str: Зашифрованные данные в base64
        """
        try:
            if isinstance(data, str):
                data = data.encode('utf-8')
            
            encrypted = self.fernet.encrypt(data)
            return base64.urlsafe_b64encode(encrypted).decode('utf-8')
            
        except Exception as e:
            logger.error(f"Error encrypting data: {e}")
            raise
    
    def decrypt_data(self, encrypted_data: str) -> str:
        """
        Расшифровать данные
        
        Args:
            encrypted_data: Зашифрованные данные в base64
            
        Returns:
            str: Расшифрованные данные
        """
        try:
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_data.encode('utf-8'))
            decrypted = self.fernet.decrypt(encrypted_bytes)
            return decrypted.decode('utf-8')
            
        except Exception as e:
            logger.error(f"Error decrypting data: {e}")
            raise
    
    def encrypt_sensitive_config(self, config: Dict[str, Any]) -> str:
        """
        Зашифровать чувствительную конфигурацию
        
        Args:
            config: Конфигурация для шифрования
            
        Returns:
            str: Зашифрованная конфигурация
        """
        try:
            import json
            config_json = json.dumps(config, ensure_ascii=False)
            return self.encrypt_data(config_json)
            
        except Exception as e:
            logger.error(f"Error encrypting config: {e}")
            raise
    
    def decrypt_sensitive_config(self, encrypted_config: str) -> Dict[str, Any]:
        """
        Расшифровать чувствительную конфигурацию
        
        Args:
            encrypted_config: Зашифрованная конфигурация
            
        Returns:
            Dict[str, Any]: Расшифрованная конфигурация
        """
        try:
            import json
            config_json = self.decrypt_data(encrypted_config)
            return json.loads(config_json)
            
        except Exception as e:
            logger.error(f"Error decrypting config: {e}")
            raise


class PasswordManager:
    """Менеджер паролей и хеширования"""
    
    @staticmethod
    def generate_password(length: int = 16, include_symbols: bool = True) -> str:
        """
        Генерировать безопасный пароль
        
        Args:
            length: Длина пароля
            include_symbols: Включать символы
            
        Returns:
            str: Сгенерированный пароль
        """
        import string
        
        characters = string.ascii_letters + string.digits
        if include_symbols:
            characters += "!@#$%^&*"
        
        return ''.join(secrets.choice(characters) for _ in range(length))
    
    @staticmethod
    def hash_password(password: str) -> str:
        """
        Хешировать пароль с использованием bcrypt
        
        Args:
            password: Пароль для хеширования
            
        Returns:
            str: Хешированный пароль
        """
        import bcrypt
        
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed.decode('utf-8')
    
    @staticmethod
    def verify_password(password: str, hashed: str) -> bool:
        """
        Проверить пароль
        
        Args:
            password: Проверяемый пароль
            hashed: Хешированный пароль
            
        Returns:
            bool: Совпадает ли пароль
        """
        import bcrypt
        
        try:
            return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
        except Exception:
            return False


class TokenManager:
    """Менеджер токенов и подписей"""
    
    def __init__(self):
        self.secret_key = settings.JWT_SECRET_KEY.encode()
    
    def generate_secure_token(self, length: int = 32) -> str:
        """
        Генерировать безопасный токен
        
        Args:
            length: Длина токена
            
        Returns:
            str: Сгенерированный токен
        """
        return secrets.token_urlsafe(length)
    
    def create_jwt_token(self, payload: Dict[str, Any], expire_minutes: int = None) -> str:
        """
        Создать JWT токен
        
        Args:
            payload: Данные для токена
            expire_minutes: Время жизни в минутах
            
        Returns:
            str: JWT токен
        """
        try:
            import jwt
            from datetime import datetime, timedelta
            
            if expire_minutes is None:
                expire_minutes = settings.JWT_EXPIRE_MINUTES
            
            # Добавляем время истечения
            payload['exp'] = datetime.utcnow() + timedelta(minutes=expire_minutes)
            payload['iat'] = datetime.utcnow()
            
            token = jwt.encode(payload, self.secret_key, algorithm=settings.JWT_ALGORITHM)
            return token
            
        except Exception as e:
            logger.error(f"Error creating JWT token: {e}")
            raise
    
    def verify_jwt_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Проверить JWT токен
        
        Args:
            token: JWT токен
            
        Returns:
            Optional[Dict[str, Any]]: Данные из токена или None
        """
        try:
            import jwt
            
            payload = jwt.decode(token, self.secret_key, algorithms=[settings.JWT_ALGORITHM])
            return payload
            
        except jwt.ExpiredSignatureError:
            logger.warning("JWT token expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid JWT token: {e}")
            return None
    
    def create_api_signature(self, data: str, timestamp: str) -> str:
        """
        Создать подпись для API запроса
        
        Args:
            data: Данные для подписи
            timestamp: Временная метка
            
        Returns:
            str: Подпись
        """
        import hmac
        
        message = f"{data}{timestamp}".encode('utf-8')
        signature = hmac.new(self.secret_key, message, hashlib.sha256).hexdigest()
        return signature
    
    def verify_api_signature(self, data: str, timestamp: str, signature: str) -> bool:
        """
        Проверить подпись API запроса
        
        Args:
            data: Данные
            timestamp: Временная метка
            signature: Подпись
            
        Returns:
            bool: Валидна ли подпись
        """
        expected_signature = self.create_api_signature(data, timestamp)
        return hmac.compare_digest(signature, expected_signature)


class VPNKeyGenerator:
    """Генератор ключей для VPN протоколов"""
    
    @staticmethod
    def generate_uuid() -> str:
        """
        Генерировать UUID для VLESS/VMESS
        
        Returns:
            str: UUID
        """
        return str(uuid.uuid4())
    
    @staticmethod
    def generate_reality_keys() -> Dict[str, str]:
        """
        Генерировать ключи для Reality
        
        Returns:
            Dict[str, str]: Приватный и публичный ключи
        """
        try:
            # Генерируем X25519 ключи
            from cryptography.hazmat.primitives.asymmetric import x25519
            
            private_key = x25519.X25519PrivateKey.generate()
            public_key = private_key.public_key()
            
            # Конвертируем в формат для Reality
            private_bytes = private_key.private_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PrivateFormat.Raw,
                encryption_algorithm=serialization.NoEncryption()
            )
            
            public_bytes = public_key.public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw
            )
            
            return {
                "private_key": base64.b64encode(private_bytes).decode(),
                "public_key": base64.b64encode(public_bytes).decode()
            }
            
        except Exception as e:
            logger.error(f"Error generating Reality keys: {e}")
            raise
    
    @staticmethod
    def generate_wireguard_keys() -> Dict[str, str]:
        """
        Генерировать ключи для WireGuard
        
        Returns:
            Dict[str, str]: Приватный и публичный ключи
        """
        try:
            from cryptography.hazmat.primitives.asymmetric import x25519
            
            private_key = x25519.X25519PrivateKey.generate()
            public_key = private_key.public_key()
            
            # WireGuard использует base64 encoding
            private_bytes = private_key.private_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PrivateFormat.Raw,
                encryption_algorithm=serialization.NoEncryption()
            )
            
            public_bytes = public_key.public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw
            )
            
            return {
                "private_key": base64.b64encode(private_bytes).decode(),
                "public_key": base64.b64encode(public_bytes).decode()
            }
            
        except Exception as e:
            logger.error(f"Error generating WireGuard keys: {e}")
            raise
    
    @staticmethod
    def generate_openvpn_keys() -> Dict[str, str]:
        """
        Генерировать ключи для OpenVPN
        
        Returns:
            Dict[str, str]: Приватный и публичный ключи
        """
        try:
            # Генерируем RSA ключи для OpenVPN
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048
            )
            
            public_key = private_key.public_key()
            
            # Сериализуем ключи в PEM формат
            private_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            )
            
            public_pem = public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
            
            return {
                "private_key": private_pem.decode(),
                "public_key": public_pem.decode()
            }
            
        except Exception as e:
            logger.error(f"Error generating OpenVPN keys: {e}")
            raise


class HashUtils:
    """Утилиты для хеширования"""
    
    @staticmethod
    def md5_hash(data: Union[str, bytes]) -> str:
        """MD5 хеш"""
        if isinstance(data, str):
            data = data.encode('utf-8')
        return hashlib.md5(data).hexdigest()
    
    @staticmethod
    def sha256_hash(data: Union[str, bytes]) -> str:
        """SHA256 хеш"""
        if isinstance(data, str):
            data = data.encode('utf-8')
        return hashlib.sha256(data).hexdigest()
    
    @staticmethod
    def sha512_hash(data: Union[str, bytes]) -> str:
        """SHA512 хеш"""
        if isinstance(data, str):
            data = data.encode('utf-8')
        return hashlib.sha512(data).hexdigest()
    
    @staticmethod
    def generate_checksum(data: Union[str, bytes], algorithm: str = "sha256") -> str:
        """
        Генерировать контрольную сумму
        
        Args:
            data: Данные
            algorithm: Алгоритм хеширования
            
        Returns:
            str: Контрольная сумма
        """
        if isinstance(data, str):
            data = data.encode('utf-8')
        
        if algorithm == "md5":
            return hashlib.md5(data).hexdigest()
        elif algorithm == "sha1":
            return hashlib.sha1(data).hexdigest()
        elif algorithm == "sha256":
            return hashlib.sha256(data).hexdigest()
        elif algorithm == "sha512":
            return hashlib.sha512(data).hexdigest()
        else:
            raise ValueError(f"Unsupported algorithm: {algorithm}")


class Base64Utils:
    """Утилиты для работы с Base64"""
    
    @staticmethod
    def encode(data: Union[str, bytes]) -> str:
        """
        Кодировать в Base64
        
        Args:
            data: Данные для кодирования
            
        Returns:
            str: Закодированные данные
        """
        if isinstance(data, str):
            data = data.encode('utf-8')
        return base64.b64encode(data).decode('utf-8')
    
    @staticmethod
    def decode(encoded_data: str) -> bytes:
        """
        Декодировать из Base64
        
        Args:
            encoded_data: Закодированные данные
            
        Returns:
            bytes: Декодированные данные
        """
        return base64.b64decode(encoded_data)
    
    @staticmethod
    def url_safe_encode(data: Union[str, bytes]) -> str:
        """
        URL-безопасное кодирование Base64
        
        Args:
            data: Данные для кодирования
            
        Returns:
            str: Закодированные данные
        """
        if isinstance(data, str):
            data = data.encode('utf-8')
        return base64.urlsafe_b64encode(data).decode('utf-8')
    
    @staticmethod
    def url_safe_decode(encoded_data: str) -> bytes:
        """
        URL-безопасное декодирование Base64
        
        Args:
            encoded_data: Закодированные данные
            
        Returns:
            bytes: Декодированные данные
        """
        return base64.urlsafe_b64decode(encoded_data)


class SecureRandom:
    """Генератор криптографически стойких случайных значений"""
    
    @staticmethod
    def random_bytes(length: int) -> bytes:
        """
        Генерировать случайные байты
        
        Args:
            length: Длина в байтах
            
        Returns:
            bytes: Случайные байты
        """
        return secrets.token_bytes(length)
    
    @staticmethod
    def random_hex(length: int) -> str:
        """
        Генерировать случайную hex строку
        
        Args:
            length: Длина в байтах
            
        Returns:
            str: Hex строка
        """
        return secrets.token_hex(length)
    
    @staticmethod
    def random_urlsafe(length: int) -> str:
        """
        Генерировать URL-безопасную случайную строку
        
        Args:
            length: Длина в байтах
            
        Returns:
            str: URL-безопасная строка
        """
        return secrets.token_urlsafe(length)
    
    @staticmethod
    def random_int(min_val: int, max_val: int) -> int:
        """
        Генерировать случайное целое число
        
        Args:
            min_val: Минимальное значение
            max_val: Максимальное значение
            
        Returns:
            int: Случайное число
        """
        return secrets.randbelow(max_val - min_val + 1) + min_val


# Глобальные экземпляры
crypto_manager = CryptoManager()
password_manager = PasswordManager()
token_manager = TokenManager()
vpn_key_generator = VPNKeyGenerator()


def encrypt_sensitive_data(data: str) -> str:
    """
    Быстрая функция для шифрования чувствительных данных
    
    Args:
        data: Данные для шифрования
        
    Returns:
        str: Зашифрованные данные
    """
    return crypto_manager.encrypt_data(data)


def decrypt_sensitive_data(encrypted_data: str) -> str:
    """
    Быстрая функция для расшифровки чувствительных данных
    
    Args:
        encrypted_data: Зашифрованные данные
        
    Returns:
        str: Расшифрованные данные
    """
    return crypto_manager.decrypt_data(encrypted_data)


def generate_secure_password(length: int = 16) -> str:
    """
    Быстрая функция для генерации безопасного пароля
    
    Args:
        length: Длина пароля
        
    Returns:
        str: Сгенерированный пароль
    """
    return password_manager.generate_password(length)


def generate_vpn_uuid() -> str:
    """
    Быстрая функция для генерации UUID для VPN
    
    Returns:
        str: UUID
    """
    return vpn_key_generator.generate_uuid()


def create_auth_token(user_id: int, expire_minutes: int = None) -> str:
    """
    Создать токен аутентификации для пользователя
    
    Args:
        user_id: ID пользователя
        expire_minutes: Время жизни токена
        
    Returns:
        str: Токен аутентификации
    """
    payload = {
        "user_id": user_id,
        "token_type": "auth"
    }
    return token_manager.create_jwt_token(payload, expire_minutes)


def verify_auth_token(token: str) -> Optional[int]:
    """
    Проверить токен аутентификации
    
    Args:
        token: Токен для проверки
        
    Returns:
        Optional[int]: ID пользователя или None
    """
    payload = token_manager.verify_jwt_token(token)
    if payload and payload.get("token_type") == "auth":
        return payload.get("user_id")
    return None


def hash_config_data(config_data: Dict[str, Any]) -> str:
    """
    Создать хеш конфигурационных данных
    
    Args:
        config_data: Данные конфигурации
        
    Returns:
        str: Хеш конфигурации
    """
    import json
    config_json = json.dumps(config_data, sort_keys=True, ensure_ascii=False)
    return HashUtils.sha256_hash(config_json)


class ConfigEncryption:
    """Класс для шифрования конфигураций VPN"""
    
    @staticmethod
    def encrypt_vpn_config(config: Dict[str, Any]) -> str:
        """
        Зашифровать VPN конфигурацию
        
        Args:
            config: Конфигурация VPN
            
        Returns:
            str: Зашифрованная конфигурация
        """
        return crypto_manager.encrypt_sensitive_config(config)
    
    @staticmethod
    def decrypt_vpn_config(encrypted_config: str) -> Dict[str, Any]:
        """
        Расшифровать VPN конфигурацию
        
        Args:
            encrypted_config: Зашифрованная конфигурация
            
        Returns:
            Dict[str, Any]: Расшифрованная конфигурация
        """
        return crypto_manager.decrypt_sensitive_config(encrypted_config)
    
    @staticmethod
    def mask_sensitive_fields(config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Замаскировать чувствительные поля в конфигурации
        
        Args:
            config: Конфигурация
            
        Returns:
            Dict[str, Any]: Конфигурация с замаскированными полями
        """
        masked_config = config.copy()
        sensitive_fields = [
            'password', 'private_key', 'secret', 'token', 
            'api_key', 'uuid', 'id'
        ]
        
        for field in sensitive_fields:
            if field in masked_config:
                value = str(masked_config[field])
                if len(value) > 8:
                    masked_config[field] = f"{value[:4]}***{value[-4:]}"
                else:
                    masked_config[field] = "***"
        
        return masked_config


class WebhookSecurity:
    """Безопасность для webhook'ов"""
    
    @staticmethod
    def verify_webhook_signature(
        payload: str, 
        signature: str, 
        secret: str
    ) -> bool:
        """
        Проверить подпись webhook'а
        
        Args:
            payload: Тело запроса
            signature: Подпись
            secret: Секретный ключ
            
        Returns:
            bool: Валидна ли подпись
        """
        import hmac
        
        expected_signature = hmac.new(
            secret.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(signature, expected_signature)
    
    @staticmethod
    def create_webhook_signature(payload: str, secret: str) -> str:
        """
        Создать подпись для webhook'а
        
        Args:
            payload: Тело запроса
            secret: Секретный ключ
            
        Returns:
            str: Подпись
        """
        import hmac
        
        return hmac.new(
            secret.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()


def validate_encryption_setup() -> bool:
    """
    Проверить настройки шифрования
    
    Returns:
        bool: Корректны ли настройки
    """
    try:
        # Тестируем шифрование/расшифровку
        test_data = "test_encryption_data"
        encrypted = crypto_manager.encrypt_data(test_data)
        decrypted = crypto_manager.decrypt_data(encrypted)
        
        if test_data != decrypted:
            logger.error("Encryption test failed")
            return False
        
        # Тестируем JWT токены
        test_payload = {"test": True}
        token = token_manager.create_jwt_token(test_payload, 1)
        verified_payload = token_manager.verify_jwt_token(token)
        
        if not verified_payload or verified_payload.get("test") != True:
            logger.error("JWT test failed")
            return False
        
        logger.info("Encryption setup validation passed")
        return True
        
    except Exception as e:
        logger.error(f"Encryption setup validation failed: {e}")
        return False