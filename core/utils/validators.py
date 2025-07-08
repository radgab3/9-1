"""
Валидаторы для VPN Bot System
"""

import re
import ipaddress
import validators as external_validators
from typing import Optional, Dict, Any, List, Union
from datetime import datetime
from loguru import logger

from core.database.models import VpnProtocol
from config.settings import settings


class TelegramValidator:
    """Валидаторы для Telegram данных"""
    
    @staticmethod
    def validate_telegram_id(telegram_id: Union[int, str]) -> bool:
        """
        Валидация Telegram ID
        
        Args:
            telegram_id: ID пользователя
            
        Returns:
            bool: Валидность ID
        """
        try:
            user_id = int(telegram_id)
            # Telegram ID должен быть положительным и не слишком большим
            return 1 <= user_id <= 9999999999
        except (ValueError, TypeError):
            return False
    
    @staticmethod
    def validate_username(username: str) -> bool:
        """
        Валидация Telegram username
        
        Args:
            username: Имя пользователя
            
        Returns:
            bool: Валидность username
        """
        if not username:
            return True  # Username необязателен
        
        # Убираем @ если есть
        username = username.lstrip('@')
        
        # Telegram username: 5-32 символа, только буквы, цифры и подчеркивания
        pattern = r'^[a-zA-Z0-9_]{5,32}$'
        return bool(re.match(pattern, username))
    
    @staticmethod
    def validate_chat_id(chat_id: Union[int, str]) -> bool:
        """
        Валидация Chat ID
        
        Args:
            chat_id: ID чата
            
        Returns:
            bool: Валидность Chat ID
        """
        try:
            chat_id = int(chat_id)
            # Chat ID может быть отрицательным (для групп)
            return -9999999999999 <= chat_id <= 9999999999999
        except (ValueError, TypeError):
            return False


class NetworkValidator:
    """Валидаторы сетевых параметров"""
    
    @staticmethod
    def validate_ip_address(ip: str) -> bool:
        """
        Валидация IP адреса
        
        Args:
            ip: IP адрес
            
        Returns:
            bool: Валидность IP
        """
        try:
            ipaddress.ip_address(ip)
            return True
        except ValueError:
            return False
    
    @staticmethod
    def validate_ipv4(ip: str) -> bool:
        """
        Валидация IPv4 адреса
        
        Args:
            ip: IPv4 адрес
            
        Returns:
            bool: Валидность IPv4
        """
        try:
            addr = ipaddress.ip_address(ip)
            return isinstance(addr, ipaddress.IPv4Address)
        except ValueError:
            return False
    
    @staticmethod
    def validate_ipv6(ip: str) -> bool:
        """
        Валидация IPv6 адреса
        
        Args:
            ip: IPv6 адрес
            
        Returns:
            bool: Валидность IPv6
        """
        try:
            addr = ipaddress.ip_address(ip)
            return isinstance(addr, ipaddress.IPv6Address)
        except ValueError:
            return False
    
    @staticmethod
    def validate_port(port: Union[int, str]) -> bool:
        """
        Валидация номера порта
        
        Args:
            port: Номер порта
            
        Returns:
            bool: Валидность порта
        """
        try:
            port_num = int(port)
            return 1 <= port_num <= 65535
        except (ValueError, TypeError):
            return False
    
    @staticmethod
    def validate_domain(domain: str) -> bool:
        """
        Валидация доменного имени
        
        Args:
            domain: Доменное имя
            
        Returns:
            bool: Валидность домена
        """
        try:
            return external_validators.domain(domain)
        except:
            return False
    
    @staticmethod
    def validate_url(url: str) -> bool:
        """
        Валидация URL
        
        Args:
            url: URL адрес
            
        Returns:
            bool: Валидность URL
        """
        try:
            return external_validators.url(url)
        except:
            return False


class VPNValidator:
    """Валидаторы для VPN конфигураций"""
    
    @staticmethod
    def validate_protocol(protocol: str) -> bool:
        """
        Валидация VPN протокола
        
        Args:
            protocol: Название протокола
            
        Returns:
            bool: Валидность протокола
        """
        try:
            VpnProtocol(protocol.lower())
            return True
        except ValueError:
            return False
    
    @staticmethod
    def validate_uuid(uuid_string: str) -> bool:
        """
        Валидация UUID для VLESS/VMESS
        
        Args:
            uuid_string: UUID строка
            
        Returns:
            bool: Валидность UUID
        """
        import uuid
        try:
            uuid.UUID(uuid_string)
            return True
        except ValueError:
            return False
    
    @staticmethod
    def validate_vless_config(config: Dict[str, Any]) -> List[str]:
        """
        Валидация VLESS конфигурации
        
        Args:
            config: Конфигурация VLESS
            
        Returns:
            List[str]: Список ошибок
        """
        errors = []
        
        # Проверяем обязательные поля
        required_fields = ['uuid', 'address', 'port']
        for field in required_fields:
            if field not in config:
                errors.append(f"Missing required field: {field}")
        
        # Проверяем UUID
        if 'uuid' in config:
            if not VPNValidator.validate_uuid(config['uuid']):
                errors.append("Invalid UUID format")
        
        # Проверяем адрес
        if 'address' in config:
            address = config['address']
            if not (NetworkValidator.validate_ip_address(address) or 
                   NetworkValidator.validate_domain(address)):
                errors.append("Invalid address format")
        
        # Проверяем порт
        if 'port' in config:
            if not NetworkValidator.validate_port(config['port']):
                errors.append("Invalid port number")
        
        # Проверяем дополнительные поля
        if 'encryption' in config:
            valid_encryptions = ['none', 'auto', 'aes-128-gcm', 'chacha20-poly1305']
            if config['encryption'] not in valid_encryptions:
                errors.append(f"Invalid encryption: {config['encryption']}")
        
        if 'network' in config:
            valid_networks = ['tcp', 'udp', 'ws', 'h2', 'grpc']
            if config['network'] not in valid_networks:
                errors.append(f"Invalid network type: {config['network']}")
        
        return errors
    
    @staticmethod
    def validate_wireguard_config(config: Dict[str, Any]) -> List[str]:
        """
        Валидация WireGuard конфигурации
        
        Args:
            config: Конфигурация WireGuard
            
        Returns:
            List[str]: Список ошибок
        """
        errors = []
        
        required_fields = ['private_key', 'public_key', 'endpoint']
        for field in required_fields:
            if field not in config:
                errors.append(f"Missing required field: {field}")
        
        # Проверяем ключи (должны быть base64)
        key_fields = ['private_key', 'public_key', 'preshared_key']
        for field in key_fields:
            if field in config and config[field]:
                try:
                    import base64
                    decoded = base64.b64decode(config[field])
                    if len(decoded) != 32:  # WireGuard ключи 32 байта
                        errors.append(f"Invalid {field} length")
                except Exception:
                    errors.append(f"Invalid {field} format")
        
        # Проверяем endpoint
        if 'endpoint' in config:
            endpoint = config['endpoint']
            if ':' in endpoint:
                host, port = endpoint.rsplit(':', 1)
                if not (NetworkValidator.validate_ip_address(host) or 
                       NetworkValidator.validate_domain(host)):
                    errors.append("Invalid endpoint host")
                if not NetworkValidator.validate_port(port):
                    errors.append("Invalid endpoint port")
            else:
                errors.append("Endpoint must include port")
        
        return errors
    
    @staticmethod
    def validate_openvpn_config(config: Dict[str, Any]) -> List[str]:
        """
        Валидация OpenVPN конфигурации
        
        Args:
            config: Конфигурация OpenVPN
            
        Returns:
            List[str]: Список ошибок
        """
        errors = []
        
        required_fields = ['remote', 'port', 'proto']
        for field in required_fields:
            if field not in config:
                errors.append(f"Missing required field: {field}")
        
        # Проверяем remote
        if 'remote' in config:
            remote = config['remote']
            if not (NetworkValidator.validate_ip_address(remote) or 
                   NetworkValidator.validate_domain(remote)):
                errors.append("Invalid remote address")
        
        # Проверяем порт
        if 'port' in config:
            if not NetworkValidator.validate_port(config['port']):
                errors.append("Invalid port number")
        
        # Проверяем протокол
        if 'proto' in config:
            valid_protos = ['udp', 'tcp', 'tcp-client']
            if config['proto'] not in valid_protos:
                errors.append(f"Invalid protocol: {config['proto']}")
        
        # Проверяем cipher
        if 'cipher' in config:
            valid_ciphers = [
                'AES-256-GCM', 'AES-128-GCM', 'AES-256-CBC', 
                'AES-128-CBC', 'CHACHA20-POLY1305'
            ]
            if config['cipher'] not in valid_ciphers:
                errors.append(f"Invalid cipher: {config['cipher']}")
        
        return errors


class UserDataValidator:
    """Валидаторы пользовательских данных"""
    
    @staticmethod
    def validate_email(email: str) -> bool:
        """
        Валидация email адреса
        
        Args:
            email: Email адрес
            
        Returns:
            bool: Валидность email
        """
        try:
            return external_validators.email(email)
        except:
            return False
    
    @staticmethod
    def validate_phone(phone: str) -> bool:
        """
        Валидация номера телефона
        
        Args:
            phone: Номер телефона
            
        Returns:
            bool: Валидность номера
        """
        # Простая валидация международного формата
        pattern = r'^\+[1-9]\d{1,14}$'
        return bool(re.match(pattern, phone))
    
    @staticmethod
    def validate_name(name: str, min_length: int = 1, max_length: int = 50) -> bool:
        """
        Валидация имени
        
        Args:
            name: Имя
            min_length: Минимальная длина
            max_length: Максимальная длина
            
        Returns:
            bool: Валидность имени
        """
        if not name:
            return False
        
        name = name.strip()
        
        if not (min_length <= len(name) <= max_length):
            return False
        
        # Только буквы, пробелы, дефисы и апострофы
        pattern = r'^[a-zA-Zа-яА-Я\s\-\']+$'
        return bool(re.match(pattern, name))
    
    @staticmethod
    def validate_language_code(lang_code: str) -> bool:
        """
        Валидация кода языка
        
        Args:
            lang_code: Код языка
            
        Returns:
            bool: Валидность кода
        """
        if not lang_code:
            return False
        
        # ISO 639-1 коды (2 символа)
        pattern = r'^[a-z]{2}$'
        return bool(re.match(pattern, lang_code.lower()))
    
    @staticmethod
    def validate_country_code(country_code: str) -> bool:
        """
        Валидация кода страны
        
        Args:
            country_code: Код страны
            
        Returns:
            bool: Валидность кода
        """
        if not country_code:
            return False
        
        # ISO 3166-1 alpha-2 коды (2 символа)
        pattern = r'^[A-Z]{2}$'
        return bool(re.match(pattern, country_code.upper()))


class SubscriptionValidator:
    """Валидаторы для подписок"""
    
    @staticmethod
    def validate_subscription_data(data: Dict[str, Any]) -> List[str]:
        """
        Валидация данных подписки
        
        Args:
            data: Данные подписки
            
        Returns:
            List[str]: Список ошибок
        """
        errors = []
        
        # Проверяем обязательные поля
        required_fields = ['user_id', 'server_id', 'plan_id']
        for field in required_fields:
            if field not in data:
                errors.append(f"Missing required field: {field}")
        
        # Проверяем ID полей
        id_fields = ['user_id', 'server_id', 'plan_id']
        for field in id_fields:
            if field in data:
                try:
                    value = int(data[field])
                    if value <= 0:
                        errors.append(f"Invalid {field}: must be positive")
                except (ValueError, TypeError):
                    errors.append(f"Invalid {field}: must be a number")
        
        # Проверяем даты
        date_fields = ['started_at', 'expires_at']
        for field in date_fields:
            if field in data and data[field]:
                if not isinstance(data[field], datetime):
                    errors.append(f"Invalid {field}: must be datetime")
        
        # Проверяем трафик
        if 'traffic_limit_gb' in data and data['traffic_limit_gb'] is not None:
            try:
                limit = int(data['traffic_limit_gb'])
                if limit <= 0:
                    errors.append("Traffic limit must be positive")
            except (ValueError, TypeError):
                errors.append("Invalid traffic limit format")
        
        return errors
    
    @staticmethod
    def validate_plan_data(data: Dict[str, Any]) -> List[str]:
        """
        Валидация данных тарифного плана
        
        Args:
            data: Данные плана
            
        Returns:
            List[str]: Список ошибок
        """
        errors = []
        
        required_fields = ['name', 'duration_days', 'price']
        for field in required_fields:
            if field not in data:
                errors.append(f"Missing required field: {field}")
        
        # Проверяем название
        if 'name' in data:
            if not isinstance(data['name'], str) or not data['name'].strip():
                errors.append("Plan name cannot be empty")
        
        # Проверяем длительность
        if 'duration_days' in data:
            try:
                days = int(data['duration_days'])
                if days <= 0:
                    errors.append("Duration must be positive")
            except (ValueError, TypeError):
                errors.append("Invalid duration format")
        
        # Проверяем цену
        if 'price' in data:
            try:
                price = float(data['price'])
                if price < 0:
                    errors.append("Price cannot be negative")
            except (ValueError, TypeError):
                errors.append("Invalid price format")
        
        return errors


class PaymentValidator:
    """Валидаторы для платежей"""
    
    @staticmethod
    def validate_payment_data(data: Dict[str, Any]) -> List[str]:
        """
        Валидация данных платежа
        
        Args:
            data: Данные платежа
            
        Returns:
            List[str]: Список ошибок
        """
        errors = []
        
        required_fields = ['user_id', 'amount', 'currency']
        for field in required_fields:
            if field not in data:
                errors.append(f"Missing required field: {field}")
        
        # Проверяем сумму
        if 'amount' in data:
            try:
                amount = float(data['amount'])
                if amount <= 0:
                    errors.append("Amount must be positive")
            except (ValueError, TypeError):
                errors.append("Invalid amount format")
        
        # Проверяем валюту
        if 'currency' in data:
            valid_currencies = ['RUB', 'USD', 'EUR', 'BTC', 'ETH', 'USDT']
            if data['currency'] not in valid_currencies:
                errors.append(f"Unsupported currency: {data['currency']}")
        
        return errors


class ConfigValidator:
    """Общий валидатор конфигураций"""
    
    @staticmethod
    def validate_server_config(config: Dict[str, Any]) -> List[str]:
        """
        Валидация конфигурации сервера
        
        Args:
            config: Конфигурация сервера
            
        Returns:
            List[str]: Список ошибок
        """
        errors = []
        
        required_fields = ['name', 'ip_address', 'country', 'country_code']
        for field in required_fields:
            if field not in config:
                errors.append(f"Missing required field: {field}")
        
        # Проверяем IP адрес
        if 'ip_address' in config:
            if not NetworkValidator.validate_ip_address(config['ip_address']):
                errors.append("Invalid IP address")
        
        # Проверяем домен если указан
        if 'domain' in config and config['domain']:
            if not NetworkValidator.validate_domain(config['domain']):
                errors.append("Invalid domain name")
        
        # Проверяем код страны
        if 'country_code' in config:
            if not UserDataValidator.validate_country_code(config['country_code']):
                errors.append("Invalid country code")
        
        # Проверяем протоколы
        if 'supported_protocols' in config:
            for protocol in config['supported_protocols']:
                if not VPNValidator.validate_protocol(protocol):
                    errors.append(f"Invalid protocol: {protocol}")
        
        # Проверяем лимиты
        if 'max_users' in config:
            try:
                max_users = int(config['max_users'])
                if max_users <= 0:
                    errors.append("Max users must be positive")
            except (ValueError, TypeError):
                errors.append("Invalid max users format")
        
        return errors
    
    @staticmethod
    def validate_bot_config(config: Dict[str, Any]) -> List[str]:
        """
        Валидация конфигурации бота
        
        Args:
            config: Конфигурация бота
            
        Returns:
            List[str]: Список ошибок
        """
        errors = []
        
        # Проверяем токен бота
        if 'bot_token' in config:
            token = config['bot_token']
            if not token or not isinstance(token, str):
                errors.append("Bot token is required")
            elif not re.match(r'^\d+:[a-zA-Z0-9_-]+, token):
                errors.append("Invalid bot token format")
        
        # Проверяем admin IDs
        if 'admin_ids' in config:
            admin_ids = config['admin_ids']
            if not isinstance(admin_ids, list):
                errors.append("Admin IDs must be a list")
            else:
                for admin_id in admin_ids:
                    if not TelegramValidator.validate_telegram_id(admin_id):
                        errors.append(f"Invalid admin ID: {admin_id}")
        
        return errors


class ValidationResult:
    """Результат валидации"""
    
    def __init__(self, is_valid: bool = True, errors: List[str] = None):
        self.is_valid = is_valid
        self.errors = errors or []
    
    def add_error(self, error: str):
        """Добавить ошибку"""
        self.errors.append(error)
        self.is_valid = False
    
    def merge(self, other: 'ValidationResult'):
        """Объединить с другим результатом"""
        self.errors.extend(other.errors)
        self.is_valid = self.is_valid and other.is_valid
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразовать в словарь"""
        return {
            'is_valid': self.is_valid,
            'errors': self.errors
        }


class ComprehensiveValidator:
    """Комплексный валидатор для всех типов данных"""
    
    @staticmethod
    def validate_user_registration(data: Dict[str, Any]) -> ValidationResult:
        """
        Валидация данных регистрации пользователя
        
        Args:
            data: Данные для валидации
            
        Returns:
            ValidationResult: Результат валидации
        """
        result = ValidationResult()
        
        # Валидируем Telegram ID
        if 'telegram_id' not in data:
            result.add_error("Telegram ID is required")
        elif not TelegramValidator.validate_telegram_id(data['telegram_id']):
            result.add_error("Invalid Telegram ID")
        
        # Валидируем username если указан
        if 'username' in data and data['username']:
            if not TelegramValidator.validate_username(data['username']):
                result.add_error("Invalid username format")
        
        # Валидируем имя
        if 'first_name' in data and data['first_name']:
            if not UserDataValidator.validate_name(data['first_name']):
                result.add_error("Invalid first name")
        
        # Валидируем язык
        if 'language_code' in data and data['language_code']:
            if not UserDataValidator.validate_language_code(data['language_code']):
                result.add_error("Invalid language code")
        
        return result
    
    @staticmethod
    def validate_vpn_config_creation(data: Dict[str, Any]) -> ValidationResult:
        """
        Валидация создания VPN конфигурации
        
        Args:
            data: Данные для валидации
            
        Returns:
            ValidationResult: Результат валидации
        """
        result = ValidationResult()
        
        # Проверяем обязательные поля
        required_fields = ['subscription_id', 'server_id', 'protocol']
        for field in required_fields:
            if field not in data:
                result.add_error(f"Missing required field: {field}")
        
        # Валидируем протокол
        if 'protocol' in data:
            if not VPNValidator.validate_protocol(data['protocol']):
                result.add_error("Invalid VPN protocol")
            else:
                # Валидируем специфичные настройки протокола
                protocol = data['protocol'].lower()
                config_data = data.get('config_data', {})
                
                if protocol == 'vless':
                    errors = VPNValidator.validate_vless_config(config_data)
                    result.errors.extend(errors)
                elif protocol == 'wireguard':
                    errors = VPNValidator.validate_wireguard_config(config_data)
                    result.errors.extend(errors)
                elif protocol == 'openvpn':
                    errors = VPNValidator.validate_openvpn_config(config_data)
                    result.errors.extend(errors)
        
        if result.errors:
            result.is_valid = False
        
        return result


def validate_telegram_data(data: Dict[str, Any]) -> bool:
    """
    Быстрая валидация Telegram данных
    
    Args:
        data: Данные от Telegram
        
    Returns:
        bool: Валидность данных
    """
    required_fields = ['telegram_id']
    
    for field in required_fields:
        if field not in data:
            return False
    
    if not TelegramValidator.validate_telegram_id(data['telegram_id']):
        return False
    
    return True


def validate_network_config(config: Dict[str, Any]) -> List[str]:
    """
    Быстрая валидация сетевой конфигурации
    
    Args:
        config: Сетевая конфигурация
        
    Returns:
        List[str]: Список ошибок
    """
    errors = []
    
    if 'ip_address' in config:
        if not NetworkValidator.validate_ip_address(config['ip_address']):
            errors.append("Invalid IP address")
    
    if 'port' in config:
        if not NetworkValidator.validate_port(config['port']):
            errors.append("Invalid port number")
    
    if 'domain' in config and config['domain']:
        if not NetworkValidator.validate_domain(config['domain']):
            errors.append("Invalid domain name")
    
    return errors


def is_valid_vpn_protocol(protocol: str) -> bool:
    """
    Быстрая проверка валидности VPN протокола
    
    Args:
        protocol: Название протокола
        
    Returns:
        bool: Валидность протокола
    """
    return VPNValidator.validate_protocol(protocol)


def sanitize_input(input_str: str, max_length: int = 255) -> str:
    """
    Очистка пользовательского ввода
    
    Args:
        input_str: Входная строка
        max_length: Максимальная длина
        
    Returns:
        str: Очищенная строка
    """
    if not input_str:
        return ""
    
    # Убираем лишние пробелы
    cleaned = input_str.strip()
    
    # Ограничиваем длину
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length]
    
    # Удаляем потенциально опасные символы
    dangerous_chars = ['<', '>', '"', "'", '&', '\x00']
    for char in dangerous_chars:
        cleaned = cleaned.replace(char, '')
    
    return cleaned


def validate_json_structure(data: Any, required_fields: List[str]) -> List[str]:
    """
    Валидация структуры JSON данных
    
    Args:
        data: JSON данные
        required_fields: Обязательные поля
        
    Returns:
        List[str]: Список ошибок
    """
    errors = []
    
    if not isinstance(data, dict):
        errors.append("Data must be a JSON object")
        return errors
    
    for field in required_fields:
        if field not in data:
            errors.append(f"Missing required field: {field}")
    
    return errors


class DataSanitizer:
    """Класс для очистки данных"""
    
    @staticmethod
    def sanitize_user_input(data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Очистка пользовательских данных
        
        Args:
            data: Входные данные
            
        Returns:
            Dict[str, Any]: Очищенные данные
        """
        sanitized = {}
        
        for key, value in data.items():
            if isinstance(value, str):
                sanitized[key] = sanitize_input(value)
            elif isinstance(value, (int, float, bool)):
                sanitized[key] = value
            elif isinstance(value, dict):
                sanitized[key] = DataSanitizer.sanitize_user_input(value)
            elif isinstance(value, list):
                sanitized[key] = [
                    sanitize_input(item) if isinstance(item, str) else item
                    for item in value
                ]
            else:
                sanitized[key] = value
        
        return sanitized
    
    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """
        Очистка имени файла
        
        Args:
            filename: Имя файла
            
        Returns:
            str: Очищенное имя файла
        """
        # Удаляем опасные символы для файловой системы
        dangerous_chars = ['<', '>', ':', '"', '|', '?', '*', '/', '\\']
        
        sanitized = filename
        for char in dangerous_chars:
            sanitized = sanitized.replace(char, '_')
        
        # Убираем точки в начале (скрытые файлы в Unix)
        sanitized = sanitized.lstrip('.')
        
        # Ограничиваем длину
        if len(sanitized) > 255:
            name, ext = sanitized.rsplit('.', 1) if '.' in sanitized else (sanitized, '')
            max_name_length = 255 - len(ext) - 1 if ext else 255
            sanitized = name[:max_name_length] + ('.' + ext if ext else '')
        
        return sanitized or 'unnamed_file'