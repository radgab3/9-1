"""
Пользовательские исключения для VPN Bot System
"""

from typing import Optional, Dict, Any


class BaseCustomException(Exception):
    """Базовое пользовательское исключение"""
    
    def __init__(
        self, 
        message: str, 
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.error_code = error_code or self.__class__.__name__
        self.details = details or {}
        super().__init__(self.message)
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразовать исключение в словарь"""
        return {
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details
        }


class UserNotFoundError(BaseCustomException):
    """Пользователь не найден"""
    pass


class UserAlreadyExistsError(BaseCustomException):
    """Пользователь уже существует"""
    pass


class UserBannedError(BaseCustomException):
    """Пользователь заблокирован"""
    pass


class SubscriptionNotFoundError(BaseCustomException):
    """Подписка не найдена"""
    pass


class SubscriptionExpiredError(BaseCustomException):
    """Подписка истекла"""
    pass


class SubscriptionAlreadyActiveError(BaseCustomException):
    """Подписка уже активна"""
    pass


class InsufficientFundsError(BaseCustomException):
    """Недостаточно средств"""
    pass


class PaymentNotFoundError(BaseCustomException):
    """Платеж не найден"""
    pass


class PaymentFailedError(BaseCustomException):
    """Платеж не прошел"""
    pass


class ServerNotAvailableError(BaseCustomException):
    """Сервер недоступен"""
    pass


class ConfigNotFoundError(BaseCustomException):
    """Конфигурация не найдена"""
    pass


class TooManyRequestsError(BaseCustomException):
    """Слишком много запросов"""
    pass


class ValidationError(BaseCustomException):
    """Ошибка валидации"""
    pass


class AuthenticationError(BaseCustomException):
    """Ошибка аутентификации"""
    pass


class AuthorizationError(BaseCustomException):
    """Ошибка авторизации"""
    pass


class RateLimitExceededError(BaseCustomException):
    """Превышен лимит запросов"""
    pass


class MaintenanceModeError(BaseCustomException):
    """Режим технического обслуживания"""
    pass