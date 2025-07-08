"""
Исключения для VPN системы
"""

from core.exceptions.custom_exceptions import BaseCustomException


class VpnException(BaseCustomException):
    """Базовое исключение VPN системы"""
    pass


class VpnConfigurationError(VpnException):
    """Ошибка конфигурации VPN"""
    pass


class VpnConnectionError(VpnException):
    """Ошибка подключения VPN"""
    pass


class VpnServerNotAvailableError(VpnException):
    """Сервер VPN недоступен"""
    pass


class VpnProtocolNotSupportedError(VpnException):
    """Протокол VPN не поддерживается"""
    pass


class VpnClientNotFoundError(VpnException):
    """Клиент VPN не найден"""
    pass


class VpnQuotaExceededError(VpnException):
    """Превышена квота VPN"""
    pass


class VpnAuthenticationError(VpnException):
    """Ошибка аутентификации VPN"""
    pass


class X3UIError(VpnException):
    """Ошибка 3X-UI панели"""
    pass


class X3UIAuthenticationError(X3UIError):
    """Ошибка аутентификации в 3X-UI"""
    pass


class X3UIClientError(X3UIError):
    """Ошибка клиента в 3X-UI"""
    pass


class X3UIServerError(X3UIError):
    """Ошибка сервера 3X-UI"""
    pass