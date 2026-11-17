from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied
from datetime import date, timedelta
from apps.cuentas.exceptions import SuscripcionInactivaException


class GranjaScopedMixin:
    """
    Mixin reutilizable que aísla todas las consultas por la granja del usuario autenticado.
    Evita fugas de datos multi-tenant.
    """
    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not user or not user.is_authenticated:
            return qs.none()
        # Si es superusuario sin granja asociada (soporte Hengest), puede ver todo en el admin/API
        if user.is_superuser and not user.granja_id:
            return qs
        if not user.granja:
            return qs.none()

        # Determinar el campo de relación con granja
        model = qs.model
        if hasattr(model, 'granja'):
            return qs.filter(granja=user.granja)
        elif hasattr(model, 'lote') and hasattr(model.lote.field.related_model, 'granja'):
            return qs.filter(lote__granja=user.granja)
        return qs

    def perform_create(self, serializer):
        user = self.request.user
        if hasattr(serializer.Meta.model, 'granja'):
            serializer.save(granja=user.granja)
        else:
            serializer.save()


class PermisoSuscripcionActiva(permissions.BasePermission):
    """
    Permiso que valida si la suscripción de la granja está activa.
    Las lecturas (GET, HEAD, OPTIONS) están siempre permitidas.
    Las escrituras responden 402 si está vencida o inactiva.
    """
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        user = request.user
        if not user or not user.is_authenticated:
            return False
        # Si es superusuario de Hengest sin granja, permitir
        if user.is_superuser and not user.granja_id:
            return True

        granja = user.granja
        if not granja:
            raise SuscripcionInactivaException()

        suscripcion = getattr(granja, 'suscripcion', None)
        if not suscripcion or not suscripcion.esta_activa():
            raise SuscripcionInactivaException()

        return True


class EsAdmin(permissions.BasePermission):
    """Permite el acceso exclusivamente a usuarios con rol ADMIN."""
    def has_permission(self, request, view):
        user = request.user
        return bool(
            user and user.is_authenticated and (user.rol == 'ADMIN' or user.is_superuser)
        )


class EsAdminOReadOnly(permissions.BasePermission):
    """Permite lectura a usuarios autenticados y escritura solo a ADMIN."""
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.rol == 'ADMIN' or request.user.is_superuser


class PermisoRegistroDiario(permissions.BasePermission):
    """
    Control de acceso específico para registros diarios:
    - Lectura: ADMIN y OPERARIO.
    - Eliminación: Solo ADMIN (OPERARIO nunca puede borrar).
    - Creación y edición: ADMIN siempre. OPERARIO solo dentro de los últimos N días (dias_edicion_operario).
    """
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        if request.method == 'DELETE' and user.rol != 'ADMIN' and not user.is_superuser:
            return False
        return True

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        if user.is_superuser or user.rol == 'ADMIN':
            return True
        if request.method == 'DELETE':
            return False

        # Si es OPERARIO modificando un objeto existente
        granja = user.granja
        dias_permitidos = granja.dias_edicion_operario if granja else 3
        hoy = date.today()
        limite_inferior = hoy - timedelta(days=dias_permitidos)

        if obj.fecha < limite_inferior or obj.fecha > hoy:
            raise PermissionDenied(
                f"El operario solo puede registrar o editar registros de los últimos {dias_permitidos} días."
            )
        return True
