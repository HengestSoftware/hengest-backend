from rest_framework import serializers
from apps.granjas.models import Granja, Galpon, Lote, EstandarSemanal


class GranjaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Granja
        fields = [
            'id', 'nombre', 'municipio', 'dias_edicion_operario',
            'umbral_postura_pts', 'umbral_postura_critico_pts',
            'umbral_consumo_pct', 'umbral_consumo_critico_pct',
            'umbral_mortalidad_diaria_pct'
        ]
        read_only_fields = ['id']


class GalponSerializer(serializers.ModelSerializer):
    class Meta:
        model = Galpon
        fields = ['id', 'nombre', 'capacidad', 'activo']
        read_only_fields = ['id']

    def validate(self, attrs):
        request = self.context.get('request')
        granja = request.user.granja if request else None
        nombre = attrs.get('nombre')
        if granja and nombre:
            qs = Galpon.objects.filter(granja=granja, nombre=nombre)
            if self.instance:
                qs = qs.exclude(id=self.instance.id)
            if qs.exists():
                raise serializers.ValidationError({"nombre": ["Ya existe un galpón con este nombre en la granja."]})
        return attrs


class LoteSerializer(serializers.ModelSerializer):
    galpon_nombre = serializers.CharField(source='galpon.nombre', read_only=True)
    aves_vivas = serializers.IntegerField(read_only=True)
    semana_vida = serializers.IntegerField(read_only=True)

    class Meta:
        model = Lote
        fields = [
            'id', 'galpon', 'galpon_nombre', 'nombre',
            'linea_genetica', 'fecha_ingreso', 'edad_inicial_semanas',
            'aves_iniciales', 'peso_promedio_huevo_g', 'estado',
            'fecha_cierre', 'aves_vivas', 'semana_vida'
        ]
        read_only_fields = ['id', 'galpon_nombre', 'aves_vivas', 'semana_vida']

    def validate_galpon(self, value):
        request = self.context.get('request')
        if request and request.user.granja:
            if value.granja_id != request.user.granja_id:
                raise serializers.ValidationError("El galpón seleccionado no pertenece a su granja.")
        return value

    def validate(self, attrs):
        request = self.context.get('request')
        granja = request.user.granja if request else None
        nombre = attrs.get('nombre')
        if granja and nombre:
            qs = Lote.objects.filter(granja=granja, nombre=nombre)
            if self.instance:
                qs = qs.exclude(id=self.instance.id)
            if qs.exists():
                raise serializers.ValidationError({"nombre": ["Ya existe un lote con este nombre en la granja."]})

        estado = attrs.get('estado', getattr(self.instance, 'estado', 'ACTIVO'))
        fecha_cierre = attrs.get('fecha_cierre', getattr(self.instance, 'fecha_cierre', None))
        if estado == 'CERRADO' and not fecha_cierre:
            raise serializers.ValidationError({"fecha_cierre": ["Debe especificar la fecha de cierre para un lote cerrado."]})

        return attrs


class EstandarSemanalSerializer(serializers.ModelSerializer):
    class Meta:
        model = EstandarSemanal
        fields = ['semana', 'postura_esperada_pct', 'mortalidad_max_semanal_pct', 'consumo_g_ave_dia']
