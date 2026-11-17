import csv
import codecs
from io import StringIO
from datetime import date, timedelta
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.http import HttpResponse
from drf_spectacular.utils import extend_schema, OpenApiParameter

from apps.granjas.models import Lote
from apps.produccion.models import RegistroDiario, Alerta, Vacunacion
from apps.produccion.serializers import AlertaSerializer, VacunacionSerializer, RegistroDiarioSerializer
from apps.produccion.services import (
    calcular_cubetas,
    calcular_aves_vivas_a_fecha,
    calcular_kpis_registro
)
from apps.cuentas.permissions import EsAdmin, PermisoSuscripcionActiva


from apps.reportes.serializers import (
    DashboardResponseSerializer,
    ReporteProduccionResponseSerializer
)


class DashboardView(APIView):
    permission_classes = [IsAuthenticated, PermisoSuscripcionActiva]

    @extend_schema(responses={200: DashboardResponseSerializer}, summary="Datos del dashboard de producción")
    def get(self, request):
        granja = request.user.granja
        if not granja:
            return Response({"detail": "Usuario sin granja asociada."}, status=status.HTTP_404_NOT_FOUND)

        hoy = date.today()
        hoy_str = hoy.strftime('%Y-%m-%d')

        lotes_activos_qs = Lote.objects.filter(granja=granja, estado='ACTIVO').select_related('galpon')
        lotes_activos_count = lotes_activos_qs.count()

        # Aves vivas total de todos los lotes activos
        aves_vivas_total = sum(lote.aves_vivas for lote in lotes_activos_qs)

        # Registros de hoy para los lotes de la granja
        registros_hoy = RegistroDiario.objects.filter(
            lote__granja=granja,
            fecha=hoy
        ).select_related('lote')

        lotes_con_registro_hoy_ids = set(registros_hoy.values_list('lote_id', flat=True))

        registros_pendientes_hoy = [
            {"lote": lote.id, "lote_nombre": lote.nombre}
            for lote in lotes_activos_qs
            if lote.id not in lotes_con_registro_hoy_ids
        ]

        huevos_hoy = 0
        cubetas_hoy = 0
        aves_vivas_inicio_hoy = 0

        for r in registros_hoy:
            c = calcular_cubetas(r.aaa, r.aa, r.a, r.b, r.c)
            huevos_hoy += c['total_huevos']
            cubetas_hoy += c['total_cubetas']
            av_ini, _ = calcular_aves_vivas_a_fecha(r.lote, hoy, excluir_registro_id=r.id)
            aves_vivas_inicio_hoy += av_ini

        if aves_vivas_inicio_hoy > 0 and huevos_hoy > 0:
            postura_hoy_pct = round((huevos_hoy / aves_vivas_inicio_hoy) * 100, 1)
        else:
            postura_hoy_pct = 0.0

        # Alertas sin leer y recientes
        alertas_qs = Alerta.objects.filter(granja=granja).select_related('lote')
        alertas_sin_leer = alertas_qs.filter(leida=False).count()
        alertas_recientes = alertas_qs.order_by('-fecha', '-creada_en')[:5]

        # Serie de 7 días (del hoy-6 a hoy)
        fecha_hace_6d = hoy - timedelta(days=6)
        registros_7d_qs = RegistroDiario.objects.filter(
            lote__granja=granja,
            fecha__gte=fecha_hace_6d,
            fecha__lte=hoy
        ).select_related('lote')

        # Agrupar por fecha
        registros_por_dia = {}
        for i in range(7):
            d = fecha_hace_6d + timedelta(days=i)
            registros_por_dia[d] = []

        for reg in registros_7d_qs:
            if reg.fecha in registros_por_dia:
                registros_por_dia[reg.fecha].append(reg)

        series_7d = []
        for d in sorted(registros_por_dia.keys()):
            regs_dia = registros_por_dia[d]
            total_h = 0
            total_m = 0
            total_c_kg = 0.0
            total_av_ini = 0
            for r in regs_dia:
                c = calcular_cubetas(r.aaa, r.aa, r.a, r.b, r.c)
                total_h += c['total_huevos']
                total_m += r.mortalidad
                total_c_kg += float(r.alimento_kg)
                av_ini, _ = calcular_aves_vivas_a_fecha(r.lote, d, excluir_registro_id=r.id)
                total_av_ini += av_ini

            post_pct = round((total_h / total_av_ini) * 100, 1) if total_av_ini > 0 else 0.0
            series_7d.append({
                "fecha": d.strftime('%Y-%m-%d'),
                "postura_pct": post_pct,
                "total_huevos": total_h,
                "mortalidad": total_m,
                "consumo_kg": round(total_c_kg, 1)
            })

        # Semáforo y postura por lote activo
        hace_3d = hoy - timedelta(days=3)
        alertas_ultimos_3d = Alerta.objects.filter(
            granja=granja,
            leida=False,
            fecha__gte=hace_3d
        )

        lotes_dashboard = []
        for lote in lotes_activos_qs:
            # Semáforo según alerta más grave sin leer en últimos 3 días
            alertas_lote = [a for a in alertas_ultimos_3d if a.lote_id == lote.id]
            if any(a.severidad == 'CRITICA' for a in alertas_lote):
                semaforo = 'ROJO'
            elif any(a.severidad == 'ADVERTENCIA' for a in alertas_lote):
                semaforo = 'AMARILLO'
            else:
                semaforo = 'VERDE'

            # Último registro para postura
            ultimo_reg = RegistroDiario.objects.filter(lote=lote).order_by('-fecha').first()
            if ultimo_reg:
                c_ult = calcular_cubetas(ultimo_reg.aaa, ultimo_reg.aa, ultimo_reg.a, ultimo_reg.b, ultimo_reg.c)
                av_ini_ult, _ = calcular_aves_vivas_a_fecha(lote, ultimo_reg.fecha, excluir_registro_id=ultimo_reg.id)
                post_lote = round((c_ult['total_huevos'] / av_ini_ult) * 100, 1) if av_ini_ult > 0 else 0.0
            else:
                post_lote = 0.0

            lotes_dashboard.append({
                "id": lote.id,
                "nombre": lote.nombre,
                "semana_vida": lote.semana_vida,
                "postura_pct": post_lote,
                "semaforo": semaforo
            })

        # Vacunaciones próximas (<= 7 días) y vencidas (< hoy)
        vacunaciones_qs = Vacunacion.objects.filter(
            lote__granja=granja,
            fecha_aplicada__isnull=True
        ).select_related('lote')

        limite_7d = hoy + timedelta(days=7)
        vacunaciones_proximas = [
            v for v in vacunaciones_qs if hoy <= v.fecha_programada <= limite_7d
        ]
        vacunaciones_vencidas = [
            v for v in vacunaciones_qs if v.fecha_programada < hoy
        ]

        return Response({
            "fecha": hoy_str,
            "lotes_activos": lotes_activos_count,
            "aves_vivas_total": aves_vivas_total,
            "postura_hoy_pct": postura_hoy_pct,
            "cubetas_hoy": cubetas_hoy,
            "huevos_hoy": huevos_hoy,
            "registros_pendientes_hoy": registros_pendientes_hoy,
            "alertas_sin_leer": alertas_sin_leer,
            "alertas_recientes": AlertaSerializer(alertas_recientes, many=True).data,
            "series_7d": series_7d,
            "lotes": lotes_dashboard,
            "vacunaciones_proximas": VacunacionSerializer(vacunaciones_proximas, many=True).data,
            "vacunaciones_vencidas": VacunacionSerializer(vacunaciones_vencidas, many=True).data
        }, status=status.HTTP_200_OK)


class ReporteProduccionView(APIView):
    permission_classes = [IsAuthenticated, EsAdmin, PermisoSuscripcionActiva]

    @extend_schema(
        summary="Reporte de producción en formato JSON o CSV",
        responses={200: ReporteProduccionResponseSerializer},
        parameters=[
            OpenApiParameter('lote', int, required=False),
            OpenApiParameter('galpon', int, required=False),
            OpenApiParameter('fecha_desde', str, required=False),
            OpenApiParameter('fecha_hasta', str, required=False),
            OpenApiParameter('formato', str, required=False, description="json o csv (por defecto json)")
        ]
    )
    def get(self, request):
        granja = request.user.granja
        if not granja:
            return Response({"detail": "Usuario sin granja asociada."}, status=status.HTTP_404_NOT_FOUND)

        qs = RegistroDiario.objects.filter(lote__granja=granja).select_related('lote', 'lote__galpon').order_by('fecha', 'lote__nombre')

        lote_id = request.query_params.get('lote')
        galpon_id = request.query_params.get('galpon')
        fecha_desde = request.query_params.get('fecha_desde')
        fecha_hasta = request.query_params.get('fecha_hasta')
        formato = request.query_params.get('formato', 'json').lower()

        if lote_id:
            qs = qs.filter(lote_id=lote_id)
        if galpon_id:
            qs = qs.filter(lote__galpon_id=galpon_id)
        if fecha_desde:
            qs = qs.filter(fecha__gte=fecha_desde)
        if fecha_hasta:
            qs = qs.filter(fecha__lte=fecha_hasta)

        registros = list(qs)

        # Cálculos de totales
        total_huevos = 0
        total_cubetas = 0
        total_alimento = 0.0
        total_mortalidad = 0
        posturas_acumuladas = []

        filas_data = []
        serializer = RegistroDiarioSerializer(registros, many=True)
        filas_data = serializer.data

        for fila in filas_data:
            total_huevos += fila.get('total_huevos', 0)
            total_cubetas += fila.get('total_cubetas', 0)
            total_alimento += float(fila.get('alimento_kg', 0.0))
            total_mortalidad += fila.get('mortalidad', 0)
            if fila.get('postura_pct') is not None:
                posturas_acumuladas.append(fila['postura_pct'])

        postura_promedio_pct = round(sum(posturas_acumuladas) / len(posturas_acumuladas), 1) if posturas_acumuladas else 0.0
        conversion_alimenticia = round(total_alimento / (total_huevos / 12.0), 2) if total_huevos > 0 else 0.0

        if formato == 'csv':
            response = HttpResponse(content_type='text/csv; charset=utf-8')
            response['Content-Disposition'] = f'attachment; filename="reporte_produccion_{date.today().strftime("%Y%m%d")}.csv"'
            # UTF-8 BOM para soporte completo en Excel
            response.write(codecs.BOM_UTF8)

            writer = csv.writer(response, delimiter=',')
            writer.writerow([
                "Fecha", "Lote", "Galpón", "AAA", "AA", "A", "B", "C",
                "Total Huevos", "Cubetas", "Sueltos", "Alimento (kg)",
                "Mortalidad", "Descarte", "Aves Vivas", "Postura (%)",
                "Consumo (g/ave)", "Conversión"
            ])

            for reg, fila in zip(registros, filas_data):
                writer.writerow([
                    reg.fecha.strftime('%Y-%m-%d'),
                    reg.lote.nombre,
                    reg.lote.galpon.nombre,
                    reg.aaa,
                    reg.aa,
                    reg.a,
                    reg.b,
                    reg.c,
                    fila.get('total_huevos', 0),
                    fila.get('total_cubetas', 0),
                    fila.get('total_sueltos', 0),
                    f"{float(reg.alimento_kg):.2f}".replace('.', ','),
                    reg.mortalidad,
                    reg.descarte,
                    fila.get('aves_vivas', 0),
                    f"{fila.get('postura_pct', 0.0):.1f}".replace('.', ','),
                    f"{fila.get('consumo_g_ave', 0.0):.1f}".replace('.', ','),
                    f"{fila.get('conversion_alimenticia', 0.0):.2f}".replace('.', ',') if fila.get('conversion_alimenticia') is not None else ""
                ])

            return response

        # Formato JSON por defecto
        return Response({
            "filtros": {
                "lote": int(lote_id) if lote_id else None,
                "galpon": int(galpon_id) if galpon_id else None,
                "fecha_desde": fecha_desde,
                "fecha_hasta": fecha_hasta,
            },
            "filas": filas_data,
            "totales": {
                "huevos": total_huevos,
                "cubetas": total_cubetas,
                "alimento_kg": round(total_alimento, 2),
                "mortalidad": total_mortalidad,
                "postura_promedio_pct": postura_promedio_pct,
                "conversion_alimenticia": conversion_alimenticia
            }
        }, status=status.HTTP_200_OK)
