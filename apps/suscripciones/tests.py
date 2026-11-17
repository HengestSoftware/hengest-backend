from django.test import TestCase, override_settings
from rest_framework.test import APITestCase
from rest_framework import status
from datetime import date, timedelta
import hashlib
import time

from apps.granjas.models import Granja
from apps.cuentas.models import Usuario
from apps.suscripciones.models import Suscripcion, Pago


@override_settings(
    WOMPI_PUBLIC_KEY="pub_test_key_123",
    WOMPI_INTEGRITY_SECRET="secret_integrity_123",
    WOMPI_EVENTS_SECRET="secret_events_123",
    FRONTEND_URL="http://localhost:5173"
)
class TestWompiIntegration(APITestCase):
    def setUp(self):
        self.granja = Granja.objects.create(nombre="Granja Wompi", municipio="Andes")
        self.admin = Usuario.objects.create_user(
            email="admin@wompi.co", password="Password123*", nombre="Admin", rol="ADMIN", granja=self.granja
        )
        self.suscripcion = Suscripcion.objects.create(
            granja=self.granja,
            plan="MENSUAL",
            estado="PENDIENTE",
            precio_cop=60000,
            dias_gracia=5
        )

    def test_checkout_creacion_y_firma_integridad(self):
        self.client.force_authenticate(user=self.admin)

        # Plan Mensual sin referido: $60.000 COP -> 6000000 centavos
        resp = self.client.post("/api/v1/suscripcion/checkout/", {"plan": "MENSUAL"})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["amount_in_cents"], 6000000)
        self.assertEqual(resp.data["currency"], "COP")

        ref = resp.data["reference"]
        # Validar cálculo exacto de la firma
        expected_sig = hashlib.sha256(
            f"{ref}6000000COPsecret_integrity_123".encode('utf-8')
        ).hexdigest()
        self.assertEqual(resp.data["signature_integrity"], expected_sig)

        # Validar que se creó el registro de Pago PENDIENTE
        pago = Pago.objects.filter(referencia=ref).first()
        self.assertIsNotNone(pago)
        self.assertEqual(pago.estado, "PENDIENTE")
        self.assertEqual(pago.monto_cop, 60000)

    def test_checkout_con_descuento_referido(self):
        self.client.force_authenticate(user=self.admin)

        # Plan Mensual con referido (15% off): 60.000 - 9.000 = $51.000 -> 5100000 centavos
        resp = self.client.post("/api/v1/suscripcion/checkout/", {
            "plan": "MENSUAL",
            "codigo_referido": "AMIGO15"
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["amount_in_cents"], 5100000)

    def test_webhook_firma_invalida(self):
        payload = {
            "event": "transaction.updated",
            "data": {
                "transaction": {
                    "id": "tx_123",
                    "status": "APPROVED",
                    "amount_in_cents": 6000000,
                    "reference": "HG-1-ref"
                }
            },
            "signature": {
                "properties": ["transaction.id", "transaction.status", "transaction.amount_in_cents"],
                "checksum": "checksum_falso_invalido"
            },
            "timestamp": int(time.time())
        }
        resp = self.client.post("/api/v1/pagos/wompi/webhook/", payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data.get("code"), "firma_invalida")

    def test_webhook_firma_valida_y_renovacion_idempotente(self):
        # Crear pago pendiente
        referencia = f"HG-{self.granja.id}-20261116-test"
        pago = Pago.objects.create(
            granja=self.granja,
            suscripcion=self.suscripcion,
            referencia=referencia,
            plan="MENSUAL",
            monto_cop=60000,
            estado="PENDIENTE"
        )

        ts = int(time.time())
        tx_id = "tx_abc123"
        tx_status = "APPROVED"
        amount_cents = 6000000

        # Construir firma de acuerdo a Wompi
        cadena = f"{tx_id}{tx_status}{amount_cents}{ts}secret_events_123"
        checksum = hashlib.sha256(cadena.encode('utf-8')).hexdigest()

        payload = {
            "event": "transaction.updated",
            "data": {
                "transaction": {
                    "id": tx_id,
                    "status": tx_status,
                    "amount_in_cents": amount_cents,
                    "reference": referencia
                }
            },
            "signature": {
                "properties": ["transaction.id", "transaction.status", "transaction.amount_in_cents"],
                "checksum": checksum
            },
            "timestamp": ts
        }

        # 1. Primer envío: debe aprobar y activar suscripción
        resp1 = self.client.post("/api/v1/pagos/wompi/webhook/", payload, format='json')
        self.assertEqual(resp1.status_code, status.HTTP_200_OK)

        pago.refresh_from_db()
        self.assertEqual(pago.estado, "APROBADO")
        self.assertEqual(pago.wompi_transaction_id, tx_id)

        self.suscripcion.refresh_from_db()
        self.assertEqual(self.suscripcion.estado, "ACTIVA")
        self.assertIsNotNone(self.suscripcion.fecha_proximo_cobro)
        fecha_cobro_primera = self.suscripcion.fecha_proximo_cobro

        # 2. Segundo envío (duplicado/idempotencia): no debe sumar otro mes adicional
        resp2 = self.client.post("/api/v1/pagos/wompi/webhook/", payload, format='json')
        self.assertEqual(resp2.status_code, status.HTTP_200_OK)

        self.suscripcion.refresh_from_db()
        self.assertEqual(self.suscripcion.fecha_proximo_cobro, fecha_cobro_primera)
