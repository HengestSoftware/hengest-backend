from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from apps.suscripciones.models import Suscripcion, Pago


class SuscripcionSerializer(serializers.ModelSerializer):
    estado = serializers.SerializerMethodField()

    class Meta:
        model = Suscripcion
        fields = ['plan', 'estado', 'precio_cop', 'fecha_inicio', 'fecha_proximo_cobro', 'dias_gracia']

    @extend_schema_field(serializers.CharField())
    def get_estado(self, obj):
        # Evaluación dinámica en el momento de la consulta si ya vencieron los días de gracia
        if obj.estado == 'ACTIVA' and not obj.esta_activa():
            return 'VENCIDA'
        return obj.estado


class PagoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pago
        fields = ['id', 'referencia', 'plan', 'monto_cop', 'estado', 'wompi_transaction_id', 'creado_en']
        read_only_fields = fields


class CheckoutRequestSerializer(serializers.Serializer):
    plan = serializers.ChoiceField(choices=['MENSUAL', 'TRIMESTRAL', 'ANUAL'])
    codigo_referido = serializers.CharField(required=False, allow_blank=True, default='')


class CheckoutResponseSerializer(serializers.Serializer):
    public_key = serializers.CharField()
    reference = serializers.CharField()
    amount_in_cents = serializers.IntegerField()
    currency = serializers.CharField()
    signature_integrity = serializers.CharField()
    redirect_url = serializers.CharField()


class WompiWebhookResponseSerializer(serializers.Serializer):
    status = serializers.CharField()
    detail = serializers.CharField(required=False)
