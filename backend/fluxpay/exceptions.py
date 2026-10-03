"""Consistent error envelope so the Android client can parse every failure the same way.

Every error response looks like::

    {"error": {"code": "insufficient_funds", "message": "...", "details": {...}}}
"""
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.views import exception_handler


class BusinessError(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "business_error"
    default_detail = "The request could not be completed."

    def __init__(self, message: str, code: str | None = None, status_code: int | None = None):
        super().__init__(detail=message, code=code or self.default_code)
        if status_code is not None:
            self.status_code = status_code
        self.error_code = code or self.default_code


def _first_message(data) -> str:
    if isinstance(data, list) and data:
        return _first_message(data[0])
    if isinstance(data, dict) and data:
        key, value = next(iter(data.items()))
        message = _first_message(value)
        return message if key in ("detail", "non_field_errors") else f"{key}: {message}"
    return str(data)


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None

    if isinstance(exc, BusinessError):
        code = exc.error_code
    elif isinstance(exc, ValidationError):
        code = "validation_error"
    else:
        codes = exc.get_codes() if hasattr(exc, "get_codes") else None
        code = codes if isinstance(codes, str) else "error"

    details = response.data if isinstance(response.data, dict) else {"errors": response.data}
    response.data = {
        "error": {
            "code": code,
            "message": _first_message(response.data),
            "details": details,
        }
    }
    return response
