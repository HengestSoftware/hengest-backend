from django.test import TestCase
from rest_framework.test import APITestCase
from rest_framework import status
from datetime import date, timedelta

from apps.granjas.models import Granja, Galpon, Lote
from apps.cuentas.models import Usuario
from apps.suscripciones.models import Suscripcion
from apps.produccion.models import RegistroDiario


class TestAutenticacion(APITestCase):
    def setUp(self):
        self.granja = Granja.objects.create(nombre="Granja Auth", municipio="Andes")
        self.user = Usuario.objects.create_user(
            email="testuser@hengest.co",
            password="Password123*",
            nombre="Usuario Test",
            rol="ADMIN",
            granja=self.granja
        )

    def test_login_exitoso(self):
        resp = self.client.post("/api/v1/auth/login/", {
            "email": "testuser@hengest.co",
            "password": "Password123*"
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("access", resp.data)
        self.assertIn("refresh", resp.data)
        self.assertIn("user", resp.data)
        self.assertEqual(resp.data["user"]["email"], "testuser@hengest.co")
        self.assertEqual(resp.data["user"]["granja"]["nombre"], "Granja Auth")

    def test_login_fallido(self):
        resp = self.client.post("/api/v1/auth/login/", {
            "email": "testuser@hengest.co",
            "password": "WrongPassword"
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_auth_me(self):
        self.client.force_authenticate(user=self.user)
        resp = self.client.get("/api/v1/auth/me/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["email"], "testuser@hengest.co")

    def test_aceptar_terminos(self):
        self.client.force_authenticate(user=self.user)
        self.assertIsNone(self.user.acepto_terminos_en)
        resp = self.client.post("/api/v1/auth/aceptar-terminos/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(resp.data["acepto_terminos_en"])


class TestAislamientoMultiTenant(APITestCase):
    def setUp(self):
        # Granja A
        self.granja_a = Granja.objects.create(nombre="Granja A", municipio="Andes")
        self.suscripcion_a = Suscripcion.objects.create(
            granja=self.granja_a, plan="MENSUAL", estado="ACTIVA",
            fecha_inicio=date.today(), fecha_proximo_cobro=date.today() + timedelta(days=30)
        )
        self.user_a = Usuario.objects.create_user(
            email="admin_a@test.co", password="Password123*", nombre="Admin A", rol="ADMIN", granja=self.granja_a
        )
        self.galpon_a = Galpon.objects.create(granja=self.granja_a, nombre="Galpon A", capacidad=1000)
        self.lote_a = Lote.objects.create(
            granja=self.granja_a, galpon=self.galpon_a, nombre="Lote A", linea_genetica="Hy-Line",
            fecha_ingreso=date.today() - timedelta(days=30), edad_inicial_semanas=18, aves_iniciales=1000
        )

        # Granja B
        self.granja_b = Granja.objects.create(nombre="Granja B", municipio="Jardín")
        self.suscripcion_b = Suscripcion.objects.create(
            granja=self.granja_b, plan="MENSUAL", estado="ACTIVA",
            fecha_inicio=date.today(), fecha_proximo_cobro=date.today() + timedelta(days=30)
        )
        self.user_b = Usuario.objects.create_user(
            email="admin_b@test.co", password="Password123*", nombre="Admin B", rol="ADMIN", granja=self.granja_b
        )
        self.galpon_b = Galpon.objects.create(granja=self.granja_b, nombre="Galpon B", capacidad=1500)
        self.lote_b = Lote.objects.create(
            granja=self.granja_b, galpon=self.galpon_b, nombre="Lote B", linea_genetica="Lohmann",
            fecha_ingreso=date.today() - timedelta(days=30), edad_inicial_semanas=18, aves_iniciales=1500
        )

    def test_usuario_a_no_ve_recursos_de_b(self):
        self.client.force_authenticate(user=self.user_a)

        # Galpones: no debe listar galpon_b
        resp_galpones = self.client.get("/api/v1/galpones/")
        self.assertEqual(resp_galpones.status_code, status.HTTP_200_OK)
        nombres_galpones = [g['nombre'] for g in resp_galpones.data['results']]
        self.assertIn("Galpon A", nombres_galpones)
        self.assertNotIn("Galpon B", nombres_galpones)

        # Acceso directo por ID a galpon_b -> 404
        resp_directo = self.client.get(f"/api/v1/galpones/{self.galpon_b.id}/")
        self.assertEqual(resp_directo.status_code, status.HTTP_404_NOT_FOUND)

        # Lotes: no debe listar lote_b
        resp_lotes = self.client.get("/api/v1/lotes/")
        self.assertEqual(resp_lotes.status_code, status.HTTP_200_OK)
        nombres_lotes = [l['nombre'] for l in resp_lotes.data['results']]
        self.assertIn("Lote A", nombres_lotes)
        self.assertNotIn("Lote B", nombres_lotes)

        # Modificación indebida: usuario A no puede editar lote B
        resp_patch = self.client.patch(f"/api/v1/lotes/{self.lote_b.id}/", {"nombre": "Hack"})
        self.assertEqual(resp_patch.status_code, status.HTTP_404_NOT_FOUND)


class TestPermisosOperario(APITestCase):
    def setUp(self):
        self.granja = Granja.objects.create(
            nombre="Granja Permisos",
            municipio="Andes",
            dias_edicion_operario=3
        )
        self.suscripcion = Suscripcion.objects.create(
            granja=self.granja, plan="MENSUAL", estado="ACTIVA",
            fecha_inicio=date.today(), fecha_proximo_cobro=date.today() + timedelta(days=30)
        )
        self.admin = Usuario.objects.create_user(
            email="admin@permisos.co", password="Password123*", nombre="Admin", rol="ADMIN", granja=self.granja
        )
        self.operario = Usuario.objects.create_user(
            email="operario@permisos.co", password="Password123*", nombre="Operario", rol="OPERARIO", granja=self.granja
        )
        self.galpon = Galpon.objects.create(granja=self.granja, nombre="G1", capacidad=1000)
        self.lote = Lote.objects.create(
            granja=self.granja, galpon=self.galpon, nombre="Lote 1", linea_genetica="Hy-Line",
            fecha_ingreso=date.today() - timedelta(days=60), edad_inicial_semanas=18, aves_iniciales=1000
        )

    def test_operario_ventana_3_dias_creacion(self):
        self.client.force_authenticate(user=self.operario)
        hoy = date.today()

        # Registro de ayer (dentro de ventana de 3 días) -> 201 Created
        resp_permitido = self.client.post("/api/v1/registros-diarios/", {
            "lote": self.lote.id,
            "fecha": (hoy - timedelta(days=1)).strftime('%Y-%m-%d'),
            "aaa": 10, "aa": 50, "a": 100, "b": 20, "c": 0,
            "alimento_kg": 95.0, "mortalidad": 0
        })
        self.assertEqual(resp_permitido.status_code, status.HTTP_201_CREATED)

        # Registro de hace 5 días (fuera de ventana de 3 días) -> 403 Forbidden
        resp_denegado = self.client.post("/api/v1/registros-diarios/", {
            "lote": self.lote.id,
            "fecha": (hoy - timedelta(days=5)).strftime('%Y-%m-%d'),
            "aaa": 10, "aa": 50, "a": 100, "b": 20, "c": 0,
            "alimento_kg": 95.0, "mortalidad": 0
        })
        self.assertEqual(resp_denegado.status_code, status.HTTP_403_FORBIDDEN)

    def test_operario_no_puede_borrar_registro(self):
        reg = RegistroDiario.objects.create(
            lote=self.lote,
            fecha=date.today() - timedelta(days=1),
            aaa=10, aa=50, a=100, b=20, c=0,
            alimento_kg=95.0, mortalidad=0
        )
        self.client.force_authenticate(user=self.operario)
        resp = self.client.delete(f"/api/v1/registros-diarios/{reg.id}/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_operario_no_accede_a_secciones_admin(self):
        self.client.force_authenticate(user=self.operario)

        # Usuarios
        resp_usr = self.client.get("/api/v1/usuarios/")
        self.assertEqual(resp_usr.status_code, status.HTTP_403_FORBIDDEN)

        # Suscripción
        resp_susc = self.client.get("/api/v1/suscripcion/")
        self.assertEqual(resp_susc.status_code, status.HTTP_403_FORBIDDEN)

        # Reportes
        resp_rep = self.client.get("/api/v1/reportes/produccion/")
        self.assertEqual(resp_rep.status_code, status.HTTP_403_FORBIDDEN)

        # Patch Granja
        resp_patch_granja = self.client.patch("/api/v1/granja/", {"umbral_postura_pts": 8})
        self.assertEqual(resp_patch_granja.status_code, status.HTTP_403_FORBIDDEN)


class TestSuscripcionBloqueo402(APITestCase):
    def setUp(self):
        self.granja = Granja.objects.create(nombre="Granja Morosa", municipio="Andes")
        # Suscripción vencida (fecha cobro hace 15 días con 5 días de gracia)
        self.suscripcion = Suscripcion.objects.create(
            granja=self.granja,
            plan="MENSUAL",
            estado="VENCIDA",
            precio_cop=60000,
            fecha_inicio=date.today() - timedelta(days=45),
            fecha_proximo_cobro=date.today() - timedelta(days=15),
            dias_gracia=5
        )
        self.admin = Usuario.objects.create_user(
            email="admin@morosa.co", password="Password123*", nombre="Admin Moroso", rol="ADMIN", granja=self.granja
        )
        self.galpon = Galpon.objects.create(granja=self.granja, nombre="G1", capacidad=1000)

    def test_bloqueo_402_en_escritura(self):
        self.client.force_authenticate(user=self.admin)

        # Intento de crear un nuevo lote con suscripción vencida -> 402 Payment Required
        resp = self.client.post("/api/v1/lotes/", {
            "galpon": self.galpon.id,
            "nombre": "Lote Nuevo",
            "linea_genetica": "Hy-Line",
            "fecha_ingreso": date.today().strftime('%Y-%m-%d'),
            "edad_inicial_semanas": 18,
            "aves_iniciales": 1000
        })
        self.assertEqual(resp.status_code, status.HTTP_402_PAYMENT_REQUIRED)
        self.assertEqual(resp.data.get("code"), "suscripcion_inactiva")

    def test_lectura_permitida_con_suscripcion_vencida(self):
        self.client.force_authenticate(user=self.admin)
        # Lectura de galpones debe seguir funcionando
        resp = self.client.get("/api/v1/galpones/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
