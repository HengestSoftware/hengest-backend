from django.test import TestCase
from rest_framework.test import APITestCase
from rest_framework import status
from datetime import date, timedelta
import uuid

from apps.granjas.models import Granja, Galpon, Lote, EstandarSemanal
from apps.cuentas.models import Usuario
from apps.suscripciones.models import Suscripcion
from apps.produccion.models import RegistroDiario, Alerta, Vacunacion
from apps.produccion.services import (
    calcular_cubetas,
    calcular_aves_vivas_a_fecha,
    calcular_kpis_registro,
    evaluar_alertas_registro,
    calcular_semana_vida
)


class TestCubetas(TestCase):
    def test_bordes_cubetas(self):
        # Casos bordes: 0, 29, 30, 31, 59, 60
        # Caso 0
        c0 = calcular_cubetas(0, 0, 0, 0, 0)
        self.assertEqual(c0['total_huevos'], 0)
        self.assertEqual(c0['total_cubetas'], 0)
        self.assertEqual(c0['total_sueltos'], 0)
        self.assertEqual(c0['cubetas']['aaa']['cubetas'], 0)
        self.assertEqual(c0['cubetas']['aaa']['sueltos'], 0)

        # Caso 29
        c29 = calcular_cubetas(29, 0, 0, 0, 0)
        self.assertEqual(c29['total_huevos'], 29)
        self.assertEqual(c29['total_cubetas'], 0)
        self.assertEqual(c29['total_sueltos'], 29)
        self.assertEqual(c29['cubetas']['aaa']['cubetas'], 0)
        self.assertEqual(c29['cubetas']['aaa']['sueltos'], 29)

        # Caso 30
        c30 = calcular_cubetas(30, 0, 0, 0, 0)
        self.assertEqual(c30['total_huevos'], 30)
        self.assertEqual(c30['total_cubetas'], 1)
        self.assertEqual(c30['total_sueltos'], 0)
        self.assertEqual(c30['cubetas']['aaa']['cubetas'], 1)
        self.assertEqual(c30['cubetas']['aaa']['sueltos'], 0)

        # Caso 31
        c31 = calcular_cubetas(31, 0, 0, 0, 0)
        self.assertEqual(c31['total_huevos'], 31)
        self.assertEqual(c31['total_cubetas'], 1)
        self.assertEqual(c31['total_sueltos'], 1)
        self.assertEqual(c31['cubetas']['aaa']['cubetas'], 1)
        self.assertEqual(c31['cubetas']['aaa']['sueltos'], 1)

        # Caso 59
        c59 = calcular_cubetas(0, 59, 0, 0, 0)
        self.assertEqual(c59['total_huevos'], 59)
        self.assertEqual(c59['total_cubetas'], 1)
        self.assertEqual(c59['total_sueltos'], 29)
        self.assertEqual(c59['cubetas']['aa']['cubetas'], 1)
        self.assertEqual(c59['cubetas']['aa']['sueltos'], 29)

        # Caso 60
        c60 = calcular_cubetas(0, 0, 60, 0, 0)
        self.assertEqual(c60['total_huevos'], 60)
        self.assertEqual(c60['total_cubetas'], 2)
        self.assertEqual(c60['total_sueltos'], 0)
        self.assertEqual(c60['cubetas']['a']['cubetas'], 2)
        self.assertEqual(c60['cubetas']['a']['sueltos'], 0)

        # Caso combinado
        comb = calcular_cubetas(35, 65, 30, 20, 10)
        # aaa: 35 -> 1 c, 5 s
        # aa: 65 -> 2 c, 5 s
        # a: 30 -> 1 c, 0 s
        # b: 20 -> 0 c, 20 s
        # c: 10 -> 0 c, 10 s
        # total_cubetas = 1 + 2 + 1 + 0 + 0 = 4
        # total_sueltos = 5 + 5 + 0 + 20 + 10 = 40
        self.assertEqual(comb['total_cubetas'], 4)
        self.assertEqual(comb['total_sueltos'], 40)
        self.assertEqual(comb['total_huevos'], 160)


class TestKPIsYAlertas(TestCase):
    def setUp(self):
        self.granja = Granja.objects.create(
            nombre="Granja Test",
            municipio="Andes",
            dias_edicion_operario=3,
            umbral_postura_pts=5.0,
            umbral_postura_critico_pts=10.0,
            umbral_consumo_pct=15.0,
            umbral_consumo_critico_pct=25.0,
            umbral_mortalidad_diaria_pct=0.15
        )
        self.suscripcion = Suscripcion.objects.create(
            granja=self.granja,
            plan="MENSUAL",
            estado="ACTIVA",
            precio_cop=60000,
            fecha_inicio=date.today() - timedelta(days=30),
            fecha_proximo_cobro=date.today() + timedelta(days=30),
            dias_gracia=5
        )
        self.galpon = Galpon.objects.create(
            granja=self.granja,
            nombre="Galpon 1",
            capacidad=2000
        )
        self.lote = Lote.objects.create(
            granja=self.granja,
            galpon=self.galpon,
            nombre="Lote 1",
            linea_genetica="Hy-Line",
            fecha_ingreso=date.today() - timedelta(days=70),
            edad_inicial_semanas=18,
            aves_iniciales=1000,
            peso_promedio_huevo_g=60.0
        )
        # Semana de vida = 18 + floor(70/7) = 28
        self.semana_actual = calcular_semana_vida(self.lote, date.today())
        self.estandar = EstandarSemanal.objects.create(
            lote=self.lote,
            semana=self.semana_actual,
            postura_esperada_pct=90.0,
            mortalidad_max_semanal_pct=0.3,
            consumo_g_ave_dia=110.0
        )

    def test_aves_vivas_y_kpis(self):
        # Aves vivas iniciales
        av_ini, av_fin = calcular_aves_vivas_a_fecha(self.lote, date.today())
        self.assertEqual(av_ini, 1000)
        self.assertEqual(av_fin, 1000)

        # Registro con alimento y huevos
        kpis = calcular_kpis_registro(
            self.lote,
            date.today(),
            alimento_kg=110.0,
            total_huevos=900,
            aves_vivas_inicio=1000
        )
        self.assertEqual(kpis['postura_pct'], 90.0)
        self.assertEqual(kpis['consumo_g_ave'], 110.0)
        # Conversión alimenticia = 110.0 / (900 / 12) = 110 / 75 = 1.47
        self.assertEqual(kpis['conversion_alimenticia'], 1.47)
        # Conversión kg/kg = 110 / (900 * 0.060) = 110 / 54 = 2.04
        self.assertEqual(kpis['conversion_kg_kg'], 2.04)

    def test_alertas_postura_advertencia_y_critica(self):
        hoy = date.today()

        # Caso normal: 900 huevos en 1000 aves = 90.0% (igual a esperada)
        r_normal = RegistroDiario.objects.create(
            lote=self.lote,
            fecha=hoy,
            a=900,
            alimento_kg=110.0,
            mortalidad=1
        )
        alertas = evaluar_alertas_registro(r_normal)
        self.assertEqual(len(alertas), 0)

        # Caso Advertencia de postura: esperada 90.0%, umbral 5.0 -> < 85.0 genera advertencia
        # Ponemos 840 huevos = 84.0%
        r_normal.a = 840
        r_normal.save()
        alertas = evaluar_alertas_registro(r_normal)
        self.assertTrue(any(a.tipo == 'POSTURA' and a.severidad == 'ADVERTENCIA' for a in alertas))

        # Caso Crítica de postura: esperada 90.0%, umbral critico 10.0 -> < 80.0 genera crítica
        # Ponemos 780 huevos = 78.0%
        r_normal.a = 780
        r_normal.save()
        alertas = evaluar_alertas_registro(r_normal)
        self.assertTrue(any(a.tipo == 'POSTURA' and a.severidad == 'CRITICA' for a in alertas))

    def test_alertas_mortalidad_diaria(self):
        hoy = date.today()
        # Umbral diario = 0.15% de 1000 = 1.5 aves.
        # Si mueren 2 aves: 2/1000 = 0.2% > 0.15% -> ADVERTENCIA
        # Si mueren 4 aves: 4/1000 = 0.4% >= 0.30% (doble) -> CRITICA
        r = RegistroDiario.objects.create(
            lote=self.lote,
            fecha=hoy,
            a=900,
            alimento_kg=110.0,
            mortalidad=2
        )
        alertas = evaluar_alertas_registro(r)
        self.assertTrue(any(a.tipo == 'MORTALIDAD' and a.severidad == 'ADVERTENCIA' for a in alertas))

        r.mortalidad = 4
        r.save()
        alertas = evaluar_alertas_registro(r)
        self.assertTrue(any(a.tipo == 'MORTALIDAD' and a.severidad == 'CRITICA' for a in alertas))

    def test_alertas_consumo(self):
        hoy = date.today()
        # Estándar = 110 g/ave.
        # Umbral advertencia: 15% -> desv > 16.5 g (ej. 130 g/ave o 90 g/ave)
        # Umbral crítico: 25% -> desv > 27.5 g (ej. 145 g/ave o 75 g/ave)
        r = RegistroDiario.objects.create(
            lote=self.lote,
            fecha=hoy,
            a=900,
            alimento_kg=130.0, # 130 g/ave -> 18.18% desv
            mortalidad=0
        )
        alertas = evaluar_alertas_registro(r)
        self.assertTrue(any(a.tipo == 'CONSUMO' and a.severidad == 'ADVERTENCIA' for a in alertas))

        r.alimento_kg = 145.0 # 145 g/ave -> 31.8% desv
        r.save()
        alertas = evaluar_alertas_registro(r)
        self.assertTrue(any(a.tipo == 'CONSUMO' and a.severidad == 'CRITICA' for a in alertas))

    def test_sin_estandar_no_genera_alertas(self):
        # Si eliminamos el estándar de la semana, NO genera alertas
        self.estandar.delete()
        hoy = date.today()
        r = RegistroDiario.objects.create(
            lote=self.lote,
            fecha=hoy,
            a=500, # Caída muy fuerte
            alimento_kg=50.0,
            mortalidad=20
        )
        alertas = evaluar_alertas_registro(r)
        self.assertEqual(len(alertas), 0)


class TestRegistroDiarioAPI(APITestCase):
    def setUp(self):
        self.granja = Granja.objects.create(nombre="Granja API", municipio="Andes")
        self.suscripcion = Suscripcion.objects.create(
            granja=self.granja,
            plan="MENSUAL",
            estado="ACTIVA",
            precio_cop=60000,
            fecha_inicio=date.today() - timedelta(days=10),
            fecha_proximo_cobro=date.today() + timedelta(days=20),
            dias_gracia=5
        )
        self.user_admin = Usuario.objects.create_user(
            email="admin@api.com",
            password="Password123*",
            nombre="Admin API",
            rol="ADMIN",
            granja=self.granja
        )
        self.galpon = Galpon.objects.create(granja=self.granja, nombre="G1", capacidad=1000)
        self.lote = Lote.objects.create(
            granja=self.granja,
            galpon=self.galpon,
            nombre="Lote Test",
            linea_genetica="Hy-Line",
            fecha_ingreso=date.today() - timedelta(days=30),
            edad_inicial_semanas=18,
            aves_iniciales=1000
        )

    def test_idempotencia_client_uuid(self):
        self.client.force_authenticate(user=self.user_admin)
        client_uuid = str(uuid.uuid4())
        payload = {
            "lote": self.lote.id,
            "fecha": (date.today() - timedelta(days=1)).strftime('%Y-%m-%d'),
            "aaa": 50,
            "aa": 200,
            "a": 500,
            "b": 100,
            "c": 20,
            "alimento_kg": 105.0,
            "mortalidad": 1,
            "client_uuid": client_uuid
        }

        # Primer POST -> 201 Created
        resp1 = self.client.post("/api/v1/registros-diarios/", payload)
        self.assertEqual(resp1.status_code, status.HTTP_201_CREATED)
        reg_id = resp1.data['id']

        # Segundo POST con el mismo client_uuid -> 200 OK con el registro existente
        resp2 = self.client.post("/api/v1/registros-diarios/", payload)
        self.assertEqual(resp2.status_code, status.HTTP_200_OK)
        self.assertEqual(resp2.data['id'], reg_id)

    def test_unicidad_lote_y_fecha(self):
        self.client.force_authenticate(user=self.user_admin)
        fecha_str = (date.today() - timedelta(days=2)).strftime('%Y-%m-%d')
        payload1 = {
            "lote": self.lote.id,
            "fecha": fecha_str,
            "aaa": 100, "aa": 200, "a": 300, "b": 100, "c": 0,
            "alimento_kg": 90.0, "mortalidad": 0
        }
        resp1 = self.client.post("/api/v1/registros-diarios/", payload1)
        self.assertEqual(resp1.status_code, status.HTTP_201_CREATED)

        # Segundo POST misma fecha sin client_uuid -> 400 Bad Request
        resp2 = self.client.post("/api/v1/registros-diarios/", payload1)
        self.assertEqual(resp2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("fecha", resp2.data)

    def test_no_permitir_fechas_futuras(self):
        self.client.force_authenticate(user=self.user_admin)
        fecha_futura = (date.today() + timedelta(days=1)).strftime('%Y-%m-%d')
        payload = {
            "lote": self.lote.id,
            "fecha": fecha_futura,
            "aaa": 50, "aa": 50, "a": 50, "b": 50, "c": 0,
            "alimento_kg": 50.0, "mortalidad": 0
        }
        resp = self.client.post("/api/v1/registros-diarios/", payload)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("fecha", resp.data)
