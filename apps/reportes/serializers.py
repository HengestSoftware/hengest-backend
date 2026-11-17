from rest_framework import serializers
from apps.produccion.serializers import AlertaSerializer, VacunacionSerializer, RegistroDiarioSerializer


class Serie7dSerializer(serializers.Serializer):
    fecha = serializers.CharField()
    postura_pct = serializers.FloatField()
    total_huevos = serializers.IntegerField()
    mortalidad = serializers.IntegerField()
    consumo_kg = serializers.FloatField()


class LoteDashboardSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    nombre = serializers.CharField()
    semana_vida = serializers.IntegerField()
    postura_pct = serializers.FloatField()
    semaforo = serializers.CharField()


class LotePendienteSerializer(serializers.Serializer):
    lote = serializers.IntegerField()
    lote_nombre = serializers.CharField()


class DashboardResponseSerializer(serializers.Serializer):
    fecha = serializers.CharField()
    lotes_activos = serializers.IntegerField()
    aves_vivas_total = serializers.IntegerField()
    postura_hoy_pct = serializers.FloatField()
    cubetas_hoy = serializers.IntegerField()
    huevos_hoy = serializers.IntegerField()
    registros_pendientes_hoy = LotePendienteSerializer(many=True)
    alertas_sin_leer = serializers.IntegerField()
    alertas_recientes = AlertaSerializer(many=True)
    series_7d = Serie7dSerializer(many=True)
    lotes = LoteDashboardSerializer(many=True)
    vacunaciones_proximas = VacunacionSerializer(many=True)
    vacunaciones_vencidas = VacunacionSerializer(many=True)


class TotalesReporteSerializer(serializers.Serializer):
    huevos = serializers.IntegerField()
    cubetas = serializers.IntegerField()
    alimento_kg = serializers.FloatField()
    mortalidad = serializers.IntegerField()
    postura_promedio_pct = serializers.FloatField()
    conversion_alimenticia = serializers.FloatField()


class FiltrosReporteSerializer(serializers.Serializer):
    lote = serializers.IntegerField(allow_null=True)
    galpon = serializers.IntegerField(allow_null=True)
    fecha_desde = serializers.CharField(allow_null=True)
    fecha_hasta = serializers.CharField(allow_null=True)


class ReporteProduccionResponseSerializer(serializers.Serializer):
    filtros = FiltrosReporteSerializer()
    filas = RegistroDiarioSerializer(many=True)
    totales = TotalesReporteSerializer()
