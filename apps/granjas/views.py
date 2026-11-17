from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from django.db.models import Sum, Avg, Count
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema

from apps.granjas.models import Granja, Galpon, Lote, EstandarSemanal
from apps.granjas.serializers import (
    GranjaSerializer,
    GalponSerializer,
    LoteSerializer,
    EstandarSemanalSerializer
)
from apps.cuentas.permissions import (
    GranjaScopedMixin,
    EsAdminOReadOnly,
    EsAdmin,
    PermisoSuscripcionActiva
)
from apps.produccion.services import (
    calcular_cubetas,
    calcular_aves_vivas_a_fecha,
    calcular_kpis_registro
)


class GranjaView(APIView):
    permission_classes = [IsAuthenticated, PermisoSuscripcionActiva]

    @extend_schema(responses={200: GranjaSerializer}, summary="Consultar configuración de la granja")
    def get(self, request):
        granja = request.user.granja
        if not granja:
            return Response({"detail": "El usuario no tiene una granja asociada."}, status=status.HTTP_404_NOT_FOUND)
        serializer = GranjaSerializer(granja)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(request=GranjaSerializer, responses={200: GranjaSerializer}, summary="Actualizar umbrales de la granja")
    def patch(self, request):
        if request.user.rol != 'ADMIN' and not request.user.is_superuser:
            return Response(
                {"detail": "Solo el administrador puede modificar la configuración de la granja.", "code": "permiso_denegado"},
                status=status.HTTP_403_FORBIDDEN
            )
        granja = request.user.granja
        if not granja:
            return Response({"detail": "El usuario no tiene una granja asociada."}, status=status.HTTP_404_NOT_FOUND)

        serializer = GranjaSerializer(granja, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)


class GalponViewSet(GranjaScopedMixin, viewsets.ModelViewSet):
    queryset = Galpon.objects.all()
    serializer_class = GalponSerializer
    permission_classes = [IsAuthenticated, EsAdminOReadOnly, PermisoSuscripcionActiva]


class LoteViewSet(GranjaScopedMixin, viewsets.ModelViewSet):
    queryset = Lote.objects.select_related('galpon').all()
    serializer_class = LoteSerializer
    permission_classes = [IsAuthenticated, EsAdminOReadOnly, PermisoSuscripcionActiva]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['estado', 'galpon']

    @action(detail=True, methods=['get'], permission_classes=[IsAuthenticated])
    def resumen(self, request, pk=None):
        lote = self.get_object()
        from apps.produccion.models import RegistroDiario

        registros = RegistroDiario.objects.filter(lote=lote).order_by('fecha')
        dias_registrados = registros.count()

        if dias_registrados == 0:
            return Response({
                "lote": lote.id,
                "dias_registrados": 0,
                "huevos_totales": 0,
                "cubetas_totales": 0,
                "postura_promedio_pct": 0.0,
                "mortalidad_acumulada": 0,
                "mortalidad_acumulada_pct": 0.0,
                "alimento_total_kg": 0.0,
                "conversion_alimenticia": None,
                "ultimos_7_dias": []
            }, status=status.HTTP_200_OK)

        huevos_totales = 0
        cubetas_totales = 0
        alimento_total_kg = 0.0
        mortalidad_acumulada = 0
        posturas_diarias = []

        for reg in registros:
            c = calcular_cubetas(reg.aaa, reg.aa, reg.a, reg.b, reg.c)
            huevos_totales += c['total_huevos']
            cubetas_totales += c['total_cubetas']
            alimento_total_kg += float(reg.alimento_kg)
            mortalidad_acumulada += reg.mortalidad

            av_ini, _ = calcular_aves_vivas_a_fecha(lote, reg.fecha, excluir_registro_id=reg.id)
            if av_ini > 0:
                posturas_diarias.append((c['total_huevos'] / av_ini) * 100)

        postura_promedio_pct = round(sum(posturas_diarias) / len(posturas_diarias), 1) if posturas_diarias else 0.0
        mortalidad_acumulada_pct = round((mortalidad_acumulada / lote.aves_iniciales) * 100, 2) if lote.aves_iniciales > 0 else 0.0
        alimento_total_kg = round(alimento_total_kg, 1)

        conversion_alimenticia = None
        if huevos_totales > 0:
            conversion_alimenticia = round(alimento_total_kg / (huevos_totales / 12.0), 2)

        # Últimos 7 registros
        ultimos_7_regs = registros.order_by('-fecha')[:7]
        ultimos_7_dias = []
        for reg in reversed(list(ultimos_7_regs)):
            c = calcular_cubetas(reg.aaa, reg.aa, reg.a, reg.b, reg.c)
            av_ini, _ = calcular_aves_vivas_a_fecha(lote, reg.fecha, excluir_registro_id=reg.id)
            post_pct = round((c['total_huevos'] / av_ini) * 100, 1) if av_ini > 0 else 0.0
            ultimos_7_dias.append({
                "fecha": reg.fecha.strftime('%Y-%m-%d'),
                "postura_pct": post_pct,
                "total_huevos": c['total_huevos'],
                "mortalidad": reg.mortalidad,
                "consumo_kg": float(reg.alimento_kg)
            })

        return Response({
            "lote": lote.id,
            "dias_registrados": dias_registrados,
            "huevos_totales": huevos_totales,
            "cubetas_totales": cubetas_totales,
            "postura_promedio_pct": postura_promedio_pct,
            "mortalidad_acumulada": mortalidad_acumulada,
            "mortalidad_acumulada_pct": mortalidad_acumulada_pct,
            "alimento_total_kg": alimento_total_kg,
            "conversion_alimenticia": conversion_alimenticia,
            "ultimos_7_dias": ultimos_7_dias
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get', 'put'], permission_classes=[IsAuthenticated, PermisoSuscripcionActiva])
    def estandares(self, request, pk=None):
        lote = self.get_object()

        if request.method == 'GET':
            estandares = lote.estandares.all().order_by('semana')
            serializer = EstandarSemanalSerializer(estandares, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

        # PUT: Reemplaza la lista completa (ADMIN)
        if request.user.rol != 'ADMIN' and not request.user.is_superuser:
            return Response(
                {"detail": "Solo el administrador puede actualizar los estándares del lote.", "code": "permiso_denegado"},
                status=status.HTTP_403_FORBIDDEN
            )

        if not isinstance(request.data, list):
            return Response(
                {"detail": "Se esperaba una lista de estándares.", "code": "formato_invalido"},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = EstandarSemanalSerializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            lote.estandares.all().delete()
            nuevos = [
                EstandarSemanal(
                    lote=lote,
                    semana=item['semana'],
                    postura_esperada_pct=item['postura_esperada_pct'],
                    mortalidad_max_semanal_pct=item['mortalidad_max_semanal_pct'],
                    consumo_g_ave_dia=item['consumo_g_ave_dia']
                )
                for item in serializer.validated_data
            ]
            EstandarSemanal.objects.bulk_create(nuevos)

        estandares = lote.estandares.all().order_by('semana')
        return Response(EstandarSemanalSerializer(estandares, many=True).data, status=status.HTTP_200_OK)
