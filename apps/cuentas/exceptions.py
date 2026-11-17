from rest_framework.views import exception_handler as drf_exception_handler
from rest_framework.exceptions import APIException
from rest_framework import status


class SuscripcionInactivaException(APIException):
    status_code = status.HTTP_402_PAYMENT_REQUIRED
    default_detail = "La suscripción de la granja se encuentra inactiva o vencida."
    default_code = "suscripcion_inactiva"


def custom_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)

    if response is not None:
        if isinstance(response.data, dict):
            # Si tiene 'detail' pero no 'code', nos aseguramos de que cumpla {"detail": "...", "code": "..."}
            if 'detail' in response.data and 'code' not in response.data:
                code = getattr(exc, 'default_code', 'error')
                if hasattr(exc, 'detail') and hasattr(exc.detail, 'code'):
                    code = exc.detail.code
                response.data['code'] = str(code)
        elif isinstance(response.data, list):
            # Si DRF devolvió una lista, la convertimos a formato de error consistente
            code = getattr(exc, 'default_code', 'error')
            response.data = {
                'detail': str(response.data[0]) if response.data else 'Error de solicitud.',
                'code': str(code)
            }

    return response
