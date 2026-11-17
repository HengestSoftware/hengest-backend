import hashlib
import hmac
import uuid
import calendar
import logging
from datetime import date
from django.conf import settings
from rest_framework import status, viewsets, serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from drf_spectacular.utils import extend_schema, inline_serializer

from apps.suscripciones.models import Suscripcion, Pago
from apps.suscripciones.serializers import (
    SuscripcionSerializer,
    PagoSerializer,
    CheckoutRequestSerializer,
    CheckoutResponseSerializer,
    WompiWebhookResponseSerializer
)
from apps.cuentas.permissions import EsAdmin, GranjaScopedMixin

logger = logging.getLogger(__name__)


class SuscripcionView(APIView):
    permission_classes = [IsAuthenticated, EsAdmin]

    @extend_schema(responses={200: SuscripcionSerializer}, summary="Consultar estado de suscripción de la granja")
    def get(self, request):
        granja = request.user.granja
        if not granja:
            return Response({"detail": "Usuario sin granja asociada."}, status=status.HTTP_404_NOT_FOUND)

        suscripcion, _ = Suscripcion.objects.get_or_create(
            granja=granja,
            defaults={
                'plan': 'MENSUAL',
                'estado': 'PENDIENTE',
                'precio_cop': 60000,
                'dias_gracia': 5
            }
        )
        serializer = SuscripcionSerializer(suscripcion)
        return Response(serializer.data, status=status.HTTP_200_OK)


class PagosListView(GranjaScopedMixin, APIView):
    permission_classes = [IsAuthenticated, EsAdmin]

    @extend_schema(responses={200: PagoSerializer(many=True)}, summary="Historial de pagos de la granja")
    def get(self, request):
        granja = request.user.granja
        if not granja:
            return Response([], status=status.HTTP_200_OK)
        pagos = Pago.objects.filter(granja=granja).order_by('-creado_en')
        serializer = PagoSerializer(pagos, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class CheckoutView(APIView):
    permission_classes = [IsAuthenticated, EsAdmin]

    @extend_schema(
        request=CheckoutRequestSerializer,
        responses={200: CheckoutResponseSerializer},
        summary="Generar orden de pago para Wompi"
    )
    def post(self, request):
        public_key = getattr(settings, 'WOMPI_PUBLIC_KEY', None)
        integrity_secret = getattr(settings, 'WOMPI_INTEGRITY_SECRET', None)

        if not public_key or not integrity_secret:
            return Response(
                {
                    "detail": "La pasarela de pagos Wompi no está configurada.",
                    "code": "wompi_no_configurado"
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        serializer = CheckoutRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        plan = serializer.validated_data['plan']
        codigo_referido = serializer.validated_data.get('codigo_referido', '').strip()

        # Cálculo de precios con descuentos
        # Base: Mensual $60.000; Trimestral 3x$60.000 (5% off = $171.000); Anual 12x$60.000 (10% off = $648.000)
        # Referido: 15% desc en primer pago (aplica el mayor, no acumulable)
        tiene_referido = bool(codigo_referido)

        if plan == 'MENSUAL':
            monto_cop = 51000 if tiene_referido else 60000
        elif plan == 'TRIMESTRAL':
            # 3 * 60000 = 180000. Descuento max(5%, 15%) = 15% -> 180000 * 0.85 = 153000. Sin referido: 171000.
            monto_cop = 153000 if tiene_referido else 171000
        elif plan == 'ANUAL':
            # 12 * 60000 = 720000. Descuento max(10%, 15%) = 15% -> 720000 * 0.85 = 612000. Sin referido: 648000.
            monto_cop = 612000 if tiene_referido else 648000
        else:
            monto_cop = 60000

        granja = request.user.granja
        suscripcion, _ = Suscripcion.objects.get_or_create(
            granja=granja,
            defaults={'plan': plan, 'estado': 'PENDIENTE', 'precio_cop': monto_cop}
        )

        # Referencia única HG-{granja_id}-{AAAAMMDD}-{aleatorio}
        fecha_str = date.today().strftime('%Y%m%d')
        ref_random = uuid.uuid4().hex[:6]
        referencia = f"HG-{granja.id}-{fecha_str}-{ref_random}"

        amount_in_cents = monto_cop * 100
        currency = "COP"

        # Firma de integridad SHA256(reference + amount_in_cents + currency + WOMPI_INTEGRITY_SECRET)
        cadena_firma = f"{referencia}{amount_in_cents}{currency}{integrity_secret}"
        signature_integrity = hashlib.sha256(cadena_firma.encode('utf-8')).hexdigest()

        # Crear Pago PENDIENTE
        Pago.objects.create(
            granja=granja,
            suscripcion=suscripcion,
            referencia=referencia,
            plan=plan,
            monto_cop=monto_cop,
            estado='PENDIENTE'
        )

        frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173').rstrip('/')
        redirect_url = f"{frontend_url}/suscripcion/resultado"

        return Response({
            "public_key": public_key,
            "reference": referencia,
            "amount_in_cents": amount_in_cents,
            "currency": currency,
            "signature_integrity": signature_integrity,
            "redirect_url": redirect_url
        }, status=status.HTTP_200_OK)


class WompiWebhookView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        request=inline_serializer('WompiWebhookPayload', fields={'event': serializers.CharField(), 'data': serializers.DictField()}),
        responses={200: WompiWebhookResponseSerializer},
        summary="Webhook de eventos de Wompi"
    )
    def post(self, request):
        events_secret = getattr(settings, 'WOMPI_EVENTS_SECRET', '')
        if not events_secret:
            logger.error("WOMPI_EVENTS_SECRET no está configurado.")
            return Response(
                {"detail": "Webhook secret no configurado", "code": "configuracion_faltante"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        payload = request.data
        signature_data = payload.get('signature', {})
        properties = signature_data.get('properties', [])
        checksum_recibido = signature_data.get('checksum', '')
        timestamp = payload.get('timestamp')

        if not properties or not checksum_recibido or timestamp is None:
            return Response(
                {"detail": "Firma o timestamp ausente en el payload.", "code": "firma_invalida"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Concatenar valores de las propiedades indicadas en signature.properties
        data = payload.get('data', {})
        valores_concatenados = []

        for prop_path in properties:
            parts = prop_path.split('.')
            val = data
            for part in parts:
                if isinstance(val, dict):
                    val = val.get(part)
                else:
                    val = None
                    break
            valores_concatenados.append(str(val) if val is not None else "")

        cadena_a_firmar = "".join(valores_concatenados) + str(timestamp) + events_secret
        checksum_calculado = hashlib.sha256(cadena_a_firmar.encode('utf-8')).hexdigest()

        if not hmac.compare_digest(checksum_calculado.lower(), checksum_recibido.lower()):
            logger.warning("Firma de webhook Wompi inválida.")
            return Response(
                {"detail": "Firma de webhook inválida.", "code": "firma_invalida"},
                status=status.HTTP_400_BAD_REQUEST
            )

        event_type = payload.get('event')
        if event_type != 'transaction.updated':
            return Response({"status": "ignorado", "detail": "Evento no procesable."}, status=status.HTTP_200_OK)

        transaction_data = data.get('transaction', {})
        referencia = transaction_data.get('reference')
        tx_status = transaction_data.get('status')
        tx_id = transaction_data.get('id')

        pago = Pago.objects.filter(referencia=referencia).first()
        if not pago:
            logger.warning(f"Pago no encontrado para referencia {referencia}")
            return Response({"status": "no_encontrado"}, status=status.HTTP_200_OK)

        pago.wompi_transaction_id = str(tx_id) if tx_id else pago.wompi_transaction_id
        pago.payload = payload

        if tx_status == 'APPROVED':
            # Idempotencia: si ya estaba aprobado no duplicar la renovación
            if pago.estado == 'APROBADO':
                return Response({"status": "ok", "detail": "Pago ya procesado previamente."}, status=status.HTTP_200_OK)

            pago.estado = 'APROBADO'
            pago.save()

            # Activar o renovar suscripción
            suscripcion = pago.suscripcion
            suscripcion.estado = 'ACTIVA'
            suscripcion.plan = pago.plan
            suscripcion.precio_cop = pago.monto_cop

            hoy = date.today()
            if not suscripcion.fecha_inicio:
                suscripcion.fecha_inicio = hoy

            base_fecha = suscripcion.fecha_proximo_cobro
            if not base_fecha or base_fecha < hoy:
                base_fecha = hoy

            meses_a_sumar = 1
            if pago.plan == 'TRIMESTRAL':
                meses_a_sumar = 3
            elif pago.plan == 'ANUAL':
                meses_a_sumar = 12

            nuevo_mes = base_fecha.month + meses_a_sumar
            nuevo_year = base_fecha.year + (nuevo_mes - 1) // 12
            nuevo_mes = ((nuevo_mes - 1) % 12) + 1
            max_dias = calendar.monthrange(nuevo_year, nuevo_mes)[1]
            nuevo_dia = min(base_fecha.day, max_dias)

            suscripcion.fecha_proximo_cobro = date(nuevo_year, nuevo_mes, nuevo_dia)
            suscripcion.save()

            return Response({"status": "ok", "detail": "Suscripción activada/renovada."}, status=status.HTTP_200_OK)

        elif tx_status in ['DECLINED', 'VOIDED', 'ERROR']:
            pago.estado = 'RECHAZADO' if tx_status == 'DECLINED' else 'ERROR'
            pago.save()

        return Response({"status": "ok"}, status=status.HTTP_200_OK)
