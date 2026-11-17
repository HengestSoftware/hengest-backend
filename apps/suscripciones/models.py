from django.db import models
from datetime import date, timedelta


class Suscripcion(models.Model):
    PLAN_CHOICES = [
        ('MENSUAL', 'Mensual'),
        ('TRIMESTRAL', 'Trimestral'),
        ('ANUAL', 'Anual'),
    ]
    ESTADO_CHOICES = [
        ('PENDIENTE', 'Pendiente'),
        ('ACTIVA', 'Activa'),
        ('VENCIDA', 'Vencida'),
        ('CANCELADA', 'Cancelada'),
    ]

    granja = models.OneToOneField(
        'granjas.Granja',
        on_delete=models.CASCADE,
        related_name="suscripcion",
        verbose_name="Granja"
    )
    plan = models.CharField(
        max_length=20,
        choices=PLAN_CHOICES,
        default='MENSUAL',
        verbose_name="Plan"
    )
    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default='PENDIENTE',
        verbose_name="Estado de suscripción"
    )
    precio_cop = models.PositiveIntegerField(
        default=60000,
        verbose_name="Precio en COP"
    )
    fecha_inicio = models.DateField(
        null=True,
        blank=True,
        verbose_name="Fecha de inicio"
    )
    fecha_proximo_cobro = models.DateField(
        null=True,
        blank=True,
        verbose_name="Fecha de próximo cobro"
    )
    dias_gracia = models.PositiveIntegerField(
        default=5,
        verbose_name="Días de gracia tras vencimiento"
    )

    class Meta:
        verbose_name = "Suscripción"
        verbose_name_plural = "Suscripciones"

    def __str__(self):
        return f"Suscripción {self.granja.nombre} - {self.plan} ({self.estado})"

    def esta_activa(self, fecha_referencia=None):
        if self.estado != 'ACTIVA':
            return False
        if self.fecha_proximo_cobro:
            hoy = fecha_referencia or date.today()
            limite = self.fecha_proximo_cobro + timedelta(days=self.dias_gracia)
            if hoy > limite:
                return False
        return True


class Pago(models.Model):
    ESTADO_CHOICES = [
        ('PENDIENTE', 'Pendiente'),
        ('APROBADO', 'Aprobado'),
        ('RECHAZADO', 'Rechazado'),
        ('ERROR', 'Error'),
    ]

    granja = models.ForeignKey(
        'granjas.Granja',
        on_delete=models.CASCADE,
        related_name="pagos",
        verbose_name="Granja"
    )
    suscripcion = models.ForeignKey(
        Suscripcion,
        on_delete=models.CASCADE,
        related_name="pagos",
        verbose_name="Suscripción"
    )
    referencia = models.CharField(
        max_length=100,
        unique=True,
        verbose_name="Referencia de pago Wompi"
    )
    plan = models.CharField(
        max_length=20,
        choices=Suscripcion.PLAN_CHOICES,
        verbose_name="Plan contratado"
    )
    monto_cop = models.PositiveIntegerField(verbose_name="Monto total (COP)")
    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default='PENDIENTE',
        verbose_name="Estado de la transacción"
    )
    wompi_transaction_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="ID Transacción Wompi"
    )
    payload = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Respuesta cruda del webhook"
    )
    creado_en = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de creación")

    class Meta:
        verbose_name = "Pago"
        verbose_name_plural = "Pagos"
        ordering = ['-creado_en']

    def __str__(self):
        return f"Pago {self.referencia} - ${self.monto_cop:,} COP ({self.estado})"
