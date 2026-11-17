import codecs
from django.test import TestCase
from rest_framework.test import APITestCase
from rest_framework import status
from datetime import date, timedelta

from apps.granjas.models import Granja, Galpon, Lote
from apps.cuentas.models import Usuario
from apps.suscripciones.models import Suscripcion
from apps.produccion.models import RegistroDiario, Vacunacion


class TestDashboardYReportes(APITestCase):
    def setUp(self):
        self.granja = Granja.objects.create(nombre="Granja Reportes", municipio="Andes")
        self.suscripcion = Suscripcion.objects.create(
            granja=self.granja,
            plan="MENSUAL",
            estado="ACTIVA",
            fecha_inicio=date.today(),
            fecha_proximo_cobro=date.today() + timedelta(days=30)
        )
        self.admin = Usuario.objects.create_user(
            email="admin@reportes.co",
            password="Password123*",
            nombre="Admin Rep",
            rol="ADMIN",
            granja=self.granja
        )
        self.galpon = Galpon.objects.create(granja=self.granja, nombre="G1", capacidad=2000)
        self.lote = Lote.objects.create(
            granja=self.granja,
            galpon=self.galpon,
            nombre="Lote 1",
            linea_genetica="Hy-Line",
            fecha_ingreso=date.today() - timedelta(days=60),
            edad_inicial_semanas=18,
            aves_iniciales=1000
        )

        hoy = date.today()
        # Crear 2 registros diarios
        RegistroDiario.objects.create(
            lote=self.lote,
            fecha=hoy - timedelta(days=1),
            aaa=30, aa=120, a=600, b=150, c=0,
            alimento_kg=110.0,
            mortalidad=2
        )
        RegistroDiario.objects.create(
            lote=self.lote,
            fecha=hoy,
            aaa=60, aa=150, a=600, b=90, c=0,
            alimento_kg=112.0,
            mortalidad=1
        )

        # Vacunaciones
        Vacunacion.objects.create(
            lote=self.lote,
            vacuna="Vacuna Vencida",
            fecha_programada=hoy - timedelta(days=2)
        )
        Vacunacion.objects.create(
            lote=self.lote,
            vacuna="Vacuna Próxima",
            fecha_programada=hoy + timedelta(days=4)
        )

    def test_dashboard_metricas(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get("/api/v1/dashboard/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        data = resp.data
        self.assertEqual(data["lotes_activos"], 1)
        self.assertIn("postura_hoy_pct", data)
        self.assertIn("series_7d", data)
        self.assertEqual(len(data["series_7d"]), 7)
        self.assertEqual(len(data["lotes"]), 1)
        self.assertIn("semaforo", data["lotes"][0])
        self.assertEqual(len(data["vacunaciones_proximas"]), 1)
        self.assertEqual(len(data["vacunaciones_vencidas"]), 1)

    def test_reporte_produccion_json(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get("/api/v1/reportes/produccion/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        data = resp.data
        self.assertIn("filtros", data)
        self.assertIn("filas", data)
        self.assertIn("totales", data)
        self.assertEqual(len(data["filas"]), 2)
        self.assertGreater(data["totales"]["huevos"], 0)
        self.assertGreater(data["totales"]["cubetas"], 0)

    def test_reporte_produccion_csv_y_bom(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get("/api/v1/reportes/produccion/?formato=csv")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp['Content-Type'], 'text/csv; charset=utf-8')

        content = resp.content
        # Verificar UTF-8 BOM inicial
        self.assertTrue(content.startswith(codecs.BOM_UTF8))

        # Decodificar texto
        texto_csv = content.decode('utf-8-sig')
        lineas = texto_csv.splitlines()
        self.assertGreaterEqual(len(lineas), 3) # Encabezado + 2 filas

        encabezado = lineas[0]
        # Validar encabezados en español
        self.assertIn("Fecha", encabezado)
        self.assertIn("Lote", encabezado)
        self.assertIn("Galpón", encabezado)
        self.assertIn("Total Huevos", encabezado)
        self.assertIn("Cubetas", encabezado)
        self.assertIn("Postura (%)", encabezado)
