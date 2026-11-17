from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from datetime import date, timedelta
from drf_spectacular.utils import extend_schema

from apps.produccion.models import RegistroDiario, Vacunacion, Alerta
from apps.produccion.serializers import (
    RegistroDiarioSerializer,
    VacunacionSerializer,
    AplicarVacunacionSerializer,
    AlertaSerializer
)
from apps.cuentas.permissions import (
    GranjaScopedMixin,
    EsAdminOReadOnly,
    PermisoRegistroDiario,
    PermisoSuscripcionActiva
)
from apps.produccion.services import evaluar_alertas_registro


class RegistroDiarioFilter(django_filters.FilterSet):
    fecha_desde = django_filters.DateFilter(field_name='fecha', lookup_expr='gte')
    fecha_hasta = django_filters.DateFilter(field_name='fecha', lookup_expr='lte')
    galpon = django_filters.NumberFilter(field_name='lote__galpon')

    class Meta:
        model = RegistroDiario
        fields = ['lote', 'galpon', 'fecha_desde', 'fecha_hasta']


class RegistroDiarioViewSet(GranjaScopedMixin, viewsets.ModelViewSet):
    queryset = RegistroDiario.objects.select_related('lote', 'lote__granja', 'lote__galpon').prefetch_related('lote__alertas').all()
    serializer_class = RegistroDiarioSerializer
    permission_classes = [IsAuthenticated, PermisoRegistroDiario, PermisoSuscripcionActiva]
    filter_backends = [DjangoFilterBackend]
    filterset_class = RegistroDiarioFilter

    def create(self, request, *args, **kwargs):
        client_uuid = request.data.get('client_uuid')
        # Idempotencia por client_uuid
        if client_uuid:
            existente = RegistroDiario.objects.filter(client_uuid=client_uuid).first()
            if existente:
                # Comprobar pertenencia a la granja
                if request.user.granja and existente.lote.granja_id == request.user.granja_id:
                    serializer = self.get_serializer(existente)
                    return Response(serializer.data, status=status.HTTP_200_OK)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Validación de rango de días para OPERARIO
        if request.user.rol == 'OPERARIO' and not request.user.is_superuser:
            fecha = serializer.validated_data['fecha']
            granja = request.user.granja
            dias_permitidos = granja.dias_edicion_operario if granja else 3
            hoy = date.today()
            if fecha < (hoy - timedelta(days=dias_permitidos)):
                raise PermissionDenied(
                    f"El operario solo puede registrar datos de los últimos {dias_permitidos} días."
                )

        instance = serializer.save(creado_por=request.user)
        # Recalcular alertas en el guardado
        evaluar_alertas_registro(instance)

        # Devolver con representación completa calculada
        serializer = self.get_serializer(instance)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_update(self, serializer):
        instance = serializer.save()
        evaluar_alertas_registro(instance)


class VacunacionFilter(django_filters.FilterSet):
    estado = django_filters.CharFilter(method='filter_estado')

    class Meta:
        model = Vacunacion
        fields = ['lote', 'estado']

    def filter_estado(self, queryset, name, value):
        hoy = date.today()
        val = value.upper()
        if val == 'APLICADA':
            return queryset.filter(fecha_aplicada__isnull=False)
        elif val == 'VENCIDA':
            return queryset.filter(fecha_aplicada__isnull=True, fecha_programada__lt=hoy)
        elif val == 'PENDIENTE':
            return queryset.filter(fecha_aplicada__isnull=True, fecha_programada__gte=hoy)
        return queryset


class VacunacionViewSet(GranjaScopedMixin, viewsets.ModelViewSet):
    queryset = Vacunacion.objects.select_related('lote').all()
    serializer_class = VacunacionSerializer
    permission_classes = [IsAuthenticated, EsAdminOReadOnly, PermisoSuscripcionActiva]
    filter_backends = [DjangoFilterBackend]
    filterset_class = VacunacionFilter

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, PermisoSuscripcionActiva])
    def aplicar(self, request, pk=None):
        vacunacion = self.get_object()
        serializer = AplicarVacunacionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        vacunacion.fecha_aplicada = serializer.validated_data['fecha_aplicada']
        if 'notas' in serializer.validated_data and serializer.validated_data['notas']:
            vacunacion.notas = serializer.validated_data['notas']
        vacunacion.save()

        return Response(VacunacionSerializer(vacunacion).data, status=status.HTTP_200_OK)


class AlertaFilter(django_filters.FilterSet):
    fecha_desde = django_filters.DateFilter(field_name='fecha', lookup_expr='gte')
    fecha_hasta = django_filters.DateFilter(field_name='fecha', lookup_expr='lte')

    class Meta:
        model = Alerta
        fields = ['lote', 'tipo', 'severidad', 'leida', 'fecha_desde', 'fecha_hasta']


class AlertaViewSet(GranjaScopedMixin, viewsets.GenericViewSet,
                    viewsets.mixins.ListModelMixin,
                    viewsets.mixins.RetrieveModelMixin,
                    viewsets.mixins.UpdateModelMixin):
    queryset = Alerta.objects.select_related('lote').all()
    serializer_class = AlertaSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = AlertaFilter

    def partial_update(self, request, *args, **kwargs):
        # Permite marcar como leída
        instance = self.get_object()
        leida = request.data.get('leida', True)
        instance.leida = bool(leida)
        instance.save(update_fields=['leida'])
        return Response(AlertaSerializer(instance).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='marcar-todas-leidas')
    def marcar_todas_leidas(self, request):
        granja = request.user.granja
        if not granja:
            return Response({"status": "ok", "marcadas": 0}, status=status.HTTP_200_OK)
        marcadas = Alerta.objects.filter(granja=granja, leida=False).update(leida=True)
        return Response({"status": "ok", "marcadas": marcadas}, status=status.HTTP_200_OK)
