from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from datetime import date, timedelta
from apps.granjas.models import Granja, Galpon, Lote, EstandarSemanal
from apps.cuentas.models import Usuario
from apps.suscripciones.models import Suscripcion
from apps.produccion.models import RegistroDiario, Vacunacion, Alerta
from apps.produccion.services import evaluar_alertas_registro, calcular_semana_vida


class Command(BaseCommand):
    help = "Carga datos de demostración para pruebas y desarrollo local de HENGEST."

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Permite forzar la ejecución del comando incluso cuando DEBUG=False',
        )

    def handle(self, *args, **options):
        if not settings.DEBUG and not options['force']:
            raise CommandError("Este comando solo puede ejecutarse cuando DEBUG=True o con el flag --force.")

        self.stdout.write(self.style.WARNING("Iniciando la carga de datos de demostración de HENGEST..."))

        # 1. Granja de demostración
        granja, creada = Granja.objects.get_or_create(
            nombre="Granja El Roble Demo",
            defaults={
                "municipio": "Andes",
                "dias_edicion_operario": 3,
                "umbral_postura_pts": 5.0,
                "umbral_postura_critico_pts": 10.0,
                "umbral_consumo_pct": 15.0,
                "umbral_consumo_critico_pct": 25.0,
                "umbral_mortalidad_diaria_pct": 0.15,
            }
        )
        self.stdout.write(self.style.SUCCESS(f"Granja asegurada: {granja.nombre}"))

        # 2. Suscripción activa para la granja
        hoy = date.today()
        suscripcion, _ = Suscripcion.objects.get_or_create(
            granja=granja,
            defaults={
                "plan": "ANUAL",
                "estado": "ACTIVA",
                "precio_cop": 648000,
                "fecha_inicio": hoy - timedelta(days=90),
                "fecha_proximo_cobro": hoy + timedelta(days=275),
                "dias_gracia": 5
            }
        )
        suscripcion.estado = "ACTIVA"
        suscripcion.fecha_proximo_cobro = hoy + timedelta(days=275)
        suscripcion.save()

        # 3. Usuarios de demostración (Admin y Operario)
        # Contraseña documentada en README: Demo2026*
        admin_email = "admin@demo.hengest.co"
        operario_email = "operario@demo.hengest.co"
        password_demo = "Demo2026*"

        admin_user, _ = Usuario.objects.get_or_create(
            email=admin_email,
            defaults={"nombre": "Ana Restrepo (Admin)", "rol": "ADMIN", "granja": granja, "activo": True}
        )
        admin_user.set_password(password_demo)
        admin_user.granja = granja
        admin_user.rol = "ADMIN"
        admin_user.save()

        operario_user, _ = Usuario.objects.get_or_create(
            email=operario_email,
            defaults={"nombre": "Carlos Gómez (Galponero)", "rol": "OPERARIO", "granja": granja, "activo": True}
        )
        operario_user.set_password(password_demo)
        operario_user.granja = granja
        operario_user.rol = "OPERARIO"
        operario_user.save()

        self.stdout.write(self.style.SUCCESS(f"Usuarios demo creados: {admin_email} y {operario_email} (Pass: {password_demo})"))

        # 4. Galpones
        g1, _ = Galpon.objects.get_or_create(
            granja=granja,
            nombre="Galpón 1",
            defaults={"capacidad": 3000, "activo": True}
        )
        g2, _ = Galpon.objects.get_or_create(
            granja=granja,
            nombre="Galpón 2",
            defaults={"capacidad": 2500, "activo": True}
        )

        # 5. Lotes
        fecha_ingreso_lote_a = hoy - timedelta(days=140)
        lote_a, _ = Lote.objects.get_or_create(
            granja=granja,
            nombre="Lote 2026-A",
            defaults={
                "galpon": g1,
                "linea_genetica": "Hy-Line Brown",
                "fecha_ingreso": fecha_ingreso_lote_a,
                "edad_inicial_semanas": 18,
                "aves_iniciales": 2800,
                "peso_promedio_huevo_g": 62.5,
                "estado": "ACTIVO"
            }
        )

        fecha_ingreso_lote_b = hoy - timedelta(days=60)
        lote_b, _ = Lote.objects.get_or_create(
            granja=granja,
            nombre="Lote 2026-B",
            defaults={
                "galpon": g2,
                "linea_genetica": "Lohmann Brown",
                "fecha_ingreso": fecha_ingreso_lote_b,
                "edad_inicial_semanas": 18,
                "aves_iniciales": 2400,
                "peso_promedio_huevo_g": 61.0,
                "estado": "ACTIVO"
            }
        )

        # 6. Estándares semanales (VALORES DE EJEMPLO, NO OFICIALES)
        self.stdout.write(self.style.NOTICE("Cargando estándares semanales marcados claramente como valores de ejemplo..."))
        for sem in range(18, 55):
            EstandarSemanal.objects.update_or_create(
                lote=lote_a,
                semana=sem,
                defaults={
                    "postura_esperada_pct": 92.5 if sem >= 24 else (70.0 + (sem - 18) * 3.5),
                    "mortalidad_max_semanal_pct": 0.25,
                    "consumo_g_ave_dia": 114.0 if sem >= 24 else 95.0,
                }
            )
            EstandarSemanal.objects.update_or_create(
                lote=lote_b,
                semana=sem,
                defaults={
                    "postura_esperada_pct": 91.0 if sem >= 24 else (68.0 + (sem - 18) * 3.5),
                    "mortalidad_max_semanal_pct": 0.28,
                    "consumo_g_ave_dia": 112.0 if sem >= 24 else 92.0,
                }
            )

        # 7. Registros diarios (30 días de registros para Lote 2026-A)
        self.stdout.write("Generando 30 días de registros de producción...")
        # Limpiar registros previos de demo para idempotencia
        RegistroDiario.objects.filter(lote=lote_a).delete()

        for d in range(30, 0, -1):
            fecha_reg = hoy - timedelta(days=d)

            # Insertamos una anomalía crítica en el día hace 2 días (caída de postura y alteración de consumo)
            if d == 2:
                # Anomalía crítica: Postura baja (ej. 75%), consumo desviado, pico mortalidad
                aaa = 100
                aa = 600
                a = 700
                b = 300
                c = 80
                alimento_kg = 390.0  # Consumo muy alto
                mortalidad = 12       # Pico de mortalidad
                descarte = 2
                obs = "Alerta de prueba: descenso súbito de postura y alta temperatura en galpón."
            elif d == 1:
                # Advertencia
                aaa = 120
                aa = 750
                a = 850
                b = 350
                c = 50
                alimento_kg = 310.0
                mortalidad = 4
                descarte = 1
                obs = "Producción en recuperación gradual tras revisión de agua y ventilación."
            else:
                # Producción normal estándar
                aaa = 160
                aa = 950
                a = 1050
                b = 360
                c = 40
                alimento_kg = 315.0
                mortalidad = 1
                descarte = 0
                obs = "Condiciones normales en galpón."

            reg = RegistroDiario.objects.create(
                lote=lote_a,
                fecha=fecha_reg,
                aaa=aaa,
                aa=aa,
                a=a,
                b=b,
                c=c,
                alimento_kg=alimento_kg,
                mortalidad=mortalidad,
                descarte=descarte,
                observaciones=obs,
                creado_por=operario_user
            )
            # Evaluar y recrear alertas para ese registro
            evaluar_alertas_registro(reg)

        # Registro para Lote 2026-B hace 1 día
        RegistroDiario.objects.filter(lote=lote_b).delete()
        reg_b = RegistroDiario.objects.create(
            lote=lote_b,
            fecha=hoy - timedelta(days=1),
            aaa=110,
            aa=800,
            a=900,
            b=320,
            c=30,
            alimento_kg=265.0,
            mortalidad=1,
            descarte=0,
            observaciones="Registro normal galpón 2.",
            creado_por=operario_user
        )
        evaluar_alertas_registro(reg_b)

        # 8. Vacunaciones próximas y vencidas
        Vacunacion.objects.filter(lote__in=[lote_a, lote_b]).delete()

        # Próxima (vence en 3 días)
        Vacunacion.objects.create(
            lote=lote_a,
            vacuna="Refuerzo Newcastle + Bronquitis",
            fecha_programada=hoy + timedelta(days=3),
            notas="Aplicar por aspersión en horas de la mañana."
        )

        # Vencida (programada hace 4 días sin aplicar)
        Vacunacion.objects.create(
            lote=lote_b,
            vacuna="Gumboro Intermedia",
            fecha_programada=hoy - timedelta(days=4),
            notas="Pendiente por llegada de biológico."
        )

        # Aplicada (programada y aplicada hace 15 días)
        Vacunacion.objects.create(
            lote=lote_a,
            vacuna="Triple Aviar",
            fecha_programada=hoy - timedelta(days=15),
            fecha_aplicada=hoy - timedelta(days=15),
            notas="Aplicada sin novedades adversas en las aves."
        )

        self.stdout.write(self.style.SUCCESS("=== Carga de datos de demostración completada exitosamente ==="))
