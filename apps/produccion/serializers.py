from rest_framework import serializers
from datetime import date
from django.utils import timezone
from apps.produccion.models import RegistroDiario, Vacunacion, Alerta
from apps.granjas.models import Lote, EstandarSemanal
from apps.produccion.services import (
    calcular_cubetas,
    calcular_aves_vivas_a_fecha,
    calcular_semana_vida,
    calcular_kpis_registro,
    evaluar_alertas_registro
)


class AlertaSerializer(serializers.ModelSerializer):
    lote_nombre = serializers.CharField(source='lote.nombre', read_only=True)

    class Meta:
        model = Alerta
        fields = [
            'id', 'lote', 'lote_nombre', 'fecha', 'tipo', 'severidad',
            'mensaje', 'valor_observado', 'valor_esperado', 'leida', 'creada_en'
        ]
        read_only_fields = [
            'id', 'lote', 'lote_nombre', 'fecha', 'tipo', 'severidad',
            'mensaje', 'valor_observado', 'valor_esperado', 'creada_en'
        ]


class VacunacionSerializer(serializers.ModelSerializer):
    estado = serializers.CharField(read_only=True)

    class Meta:
        model = Vacunacion
        fields = ['id', 'lote', 'vacuna', 'fecha_programada', 'fecha_aplicada', 'estado', 'notas']
        read_only_fields = ['id', 'estado']

    def validate_lote(self, value):
        request = self.context.get('request')
        if request and request.user.granja:
            if value.granja_id != request.user.granja_id:
                raise serializers.ValidationError("El lote no pertenece a su granja.")
        return value


class AplicarVacunacionSerializer(serializers.Serializer):
    fecha_aplicada = serializers.DateField(required=True)
    notas = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_fecha_aplicada(self, value):
        if value > date.today():
            raise serializers.ValidationError("La fecha de aplicación no puede ser futura.")
        return value


class RegistroDiarioSerializer(serializers.ModelSerializer):
    total_huevos = serializers.IntegerField(read_only=True)
    cubetas = serializers.DictField(read_only=True)
    total_cubetas = serializers.IntegerField(read_only=True)
    total_sueltos = serializers.IntegerField(read_only=True)
    aves_vivas = serializers.IntegerField(read_only=True)
    postura_pct = serializers.FloatField(read_only=True)
    consumo_g_ave = serializers.FloatField(read_only=True)
    conversion_alimenticia = serializers.FloatField(read_only=True)
    conversion_kg_kg = serializers.FloatField(read_only=True, required=False)
    semana_vida = serializers.IntegerField(read_only=True)
    sin_estandar = serializers.BooleanField(read_only=True)
    alertas = AlertaSerializer(many=True, read_only=True)

    class Meta:
        model = RegistroDiario
        validators = []  # Validación personalizada en validate() para mensaje explícito en campo 'fecha'
        fields = [
            'id', 'lote', 'fecha', 'aaa', 'aa', 'a', 'b', 'c',
            'alimento_kg', 'mortalidad', 'causa_mortalidad',
            'descarte', 'motivo_descarte', 'observaciones', 'client_uuid',
            'total_huevos', 'cubetas', 'total_cubetas', 'total_sueltos',
            'aves_vivas', 'postura_pct', 'consumo_g_ave',
            'conversion_alimenticia', 'conversion_kg_kg',
            'semana_vida', 'sin_estandar', 'alertas'
        ]
        read_only_fields = [
            'id', 'total_huevos', 'cubetas', 'total_cubetas', 'total_sueltos',
            'aves_vivas', 'postura_pct', 'consumo_g_ave', 'conversion_alimenticia',
            'conversion_kg_kg', 'semana_vida', 'sin_estandar', 'alertas'
        ]

    def validate_lote(self, value):
        request = self.context.get('request')
        if request and request.user.granja:
            if value.granja_id != request.user.granja_id:
                raise serializers.ValidationError("El lote no pertenece a su granja.")
        if value.estado == 'CERRADO':
            raise serializers.ValidationError("No se pueden registrar datos en un lote cerrado.")
        return value

    def validate(self, attrs):
        lote = attrs.get('lote', getattr(self.instance, 'lote', None))
        fecha = attrs.get('fecha', getattr(self.instance, 'fecha', None))
        mortalidad = attrs.get('mortalidad', getattr(self.instance, 'mortalidad', 0))
        descarte = attrs.get('descarte', getattr(self.instance, 'descarte', 0))
        alimento_kg = attrs.get('alimento_kg', getattr(self.instance, 'alimento_kg', 0))

        # No permitir valores negativos
        for f in ['aaa', 'aa', 'a', 'b', 'c', 'mortalidad', 'descarte']:
            val = attrs.get(f)
            if val is not None and val < 0:
                raise serializers.ValidationError({f: ["El valor no puede ser negativo."]})
        if alimento_kg is not None and alimento_kg < 0:
            raise serializers.ValidationError({"alimento_kg": ["El alimento consumido no puede ser negativo."]})

        # Validaciones de fecha
        hoy = date.today()
        if fecha > hoy:
            raise serializers.ValidationError({"fecha": ["No se permiten registros con fechas futuras."]})

        if lote and fecha < lote.fecha_ingreso:
            raise serializers.ValidationError({
                "fecha": [f"La fecha no puede ser anterior a la fecha de ingreso del lote ({lote.fecha_ingreso})."]
            })

        # Aves vivas antes del día
        instancia_id = self.instance.id if self.instance else None
        aves_inicio, _ = calcular_aves_vivas_a_fecha(lote, fecha, excluir_registro_id=instancia_id)
        if (mortalidad + descarte) > aves_inicio:
            raise serializers.ValidationError({
                "mortalidad": [
                    f"La suma de mortalidad ({mortalidad}) y descarte ({descarte}) supera las aves vivas al inicio del día ({aves_inicio})."
                ]
            })

        # Validar unicidad (lote, fecha)
        qs_dup = RegistroDiario.objects.filter(lote=lote, fecha=fecha)
        if instancia_id:
            qs_dup = qs_dup.exclude(id=instancia_id)
        if qs_dup.exists():
            raise serializers.ValidationError({
                "fecha": ["Ya existe un registro para este lote en la fecha indicada."]
            })

        return attrs

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        lote = instance.lote
        fecha = instance.fecha

        # Cálculos puros
        cubetas_calc = calcular_cubetas(instance.aaa, instance.aa, instance.a, instance.b, instance.c)
        ret['total_huevos'] = cubetas_calc['total_huevos']
        ret['cubetas'] = cubetas_calc['cubetas']
        ret['total_cubetas'] = cubetas_calc['total_cubetas']
        ret['total_sueltos'] = cubetas_calc['total_sueltos']

        # Aves vivas
        aves_inicio, aves_final = calcular_aves_vivas_a_fecha(lote, fecha, excluir_registro_id=instance.id)
        # Al final del día del registro actual
        aves_final_con_este = max(0, aves_inicio - instance.mortalidad - instance.descarte)
        ret['aves_vivas'] = aves_final_con_este

        # KPIs
        kpis = calcular_kpis_registro(
            lote, fecha, instance.alimento_kg, cubetas_calc['total_huevos'], aves_inicio
        )
        ret['postura_pct'] = kpis['postura_pct']
        ret['consumo_g_ave'] = kpis['consumo_g_ave']
        ret['conversion_alimenticia'] = kpis['conversion_alimenticia']
        if kpis['conversion_kg_kg'] is not None:
            ret['conversion_kg_kg'] = kpis['conversion_kg_kg']

        # Semana de vida y estándar
        semana_vida = calcular_semana_vida(lote, fecha)
        ret['semana_vida'] = semana_vida
        tiene_estandar = EstandarSemanal.objects.filter(lote=lote, semana=semana_vida).exists()
        ret['sin_estandar'] = not tiene_estandar

        # Alertas de ese lote y fecha
        alertas_qs = Alerta.objects.filter(lote=lote, fecha=fecha)
        ret['alertas'] = AlertaSerializer(alertas_qs, many=True).data

        return ret
