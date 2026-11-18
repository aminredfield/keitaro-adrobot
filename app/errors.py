"""Ошибки приложения. Каждая знает, каким HTTP-кодом её отдать."""


class AppError(Exception):
    status_code = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(AppError):
    status_code = 404


class ConflictError(AppError):
    status_code = 409


class ValidationError(AppError):
    status_code = 422


class KeitaroError(AppError):
    """Keitaro недоступен или ответил ошибкой — для клиента это 502."""

    status_code = 502
