from django.db import models
from django.conf import settings
from datetime import date


class RegistroDiario(models.Model):
    lote = models.ForeignKey(
        'granjas.Lote',
        on_delete=models.CASCADE,
        related_name="registros_diarios",
        verbose_name="Lote"
    )
    fecha = models.DateField(verbose_name="Fecha del registro")

    # Unidades de huevos por categoría comercial
    aaa = models.PositiveIntegerField(default=0, verbose_name="Huevos AAA (unidades)")
    aa = models.PositiveIntegerField(default=0, verbose_name="Huevos AA (unidades)")
    a = models.PositiveIntegerField(default=0, verbose_name="Huevos A (unidades)")
    b = models.PositiveIntegerField(default=0, verbose_name="Huevos B (unidades)")
    c = models.PositiveIntegerField(default=0, verbose_name="Huevos C (unidades)")

    alimento_kg = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0.0,
        verbose_name="Alimento consumido (kg)"
    )

    mortalidad = models.PositiveIntegerField(default=0, verbose_name="Mortalidad (aves)")
    causa_mortalidad = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Causa de mortalidad"
    )

    descarte = models.PositiveIntegerField(default=0, verbose_name="Descarte (aves)")
    motivo_descarte = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Motivo de descarte"
    )

    observaciones = models.TextField(blank=True, default="", verbose_name="Observaciones")
    client_uuid = models.UUIDField(
        null=True,
        blank=True,
        unique=True,
        verbose_name="UUID del cliente (offline)"
    )

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="registros_creados",
        verbose_name="Registrado por"
    )
    creado_en = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de creación")
    actualizado_en = models.DateTimeField(auto_now=True, verbose_name="Fecha de actualización")

    class Meta:
        verbose_name = "Registro Diario"
        verbose_name_plural = "Registros Diarios"
        constraints = [
            models.UniqueConstraint(fields=['lote', 'fecha'], name='unique_registro_por_lote_fecha')
        ]
        indexes = [
            models.Index(fields=['lote', 'fecha']),
        ]
        ordering = ['-fecha', 'lote']

    def __str__(self):
        return f"{self.lote.nombre} - {self.fecha}"


class Vacunacion(models.Model):
    lote = models.ForeignKey(
        'granjas.Lote',
        on_delete=models.CASCADE,
        related_name="vacunaciones",
        verbose_name="Lote"
    )
    vacuna = models.CharField(max_length=150, verbose_name="Nombre de la vacuna")
    fecha_programada = models.DateField(verbose_name="Fecha programada")
    fecha_aplicada = models.DateField(null=True, blank=True, verbose_name="Fecha aplicada")
    notas = models.TextField(blank=True, default="", verbose_name="Notas")

    class Meta:
        verbose_name = "Vacunación"
        verbose_name_plural = "Vacunaciones"
        ordering = ['fecha_programada', 'vacuna']

    def __str__(self):
        return f"{self.vacuna} - Lote {self.lote.nombre} ({self.estado})"

    @property
    def estado(self):
        if self.fecha_aplicada:
            return 'APLICADA'
        if self.fecha_programada < date.today():
            return 'VENCIDA'
        return 'PENDIENTE'


class Alerta(models.Model):
    TIPO_CHOICES = [
        ('POSTURA', 'Postura'),
        ('MORTALIDAD', 'Mortalidad'),
        ('CONSUMO', 'Consumo'),
    ]
    SEVERIDAD_CHOICES = [
        ('ADVERTENCIA', 'Advertencia'),
        ('CRITICA', 'Crítica'),
    ]

    granja = models.ForeignKey(
        'granjas.Granja',
        on_delete=models.CASCADE,
        related_name="alertas",
        verbose_name="Granja"
    )
    lote = models.ForeignKey(
        'granjas.Lote',
        on_delete=models.CASCADE,
        related_name="alertas",
        verbose_name="Lote"
    )
    fecha = models.DateField(verbose_name="Fecha de ocurrencia")
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, verbose_name="Tipo de alerta")
    severidad = models.CharField(max_length=20, choices=SEVERIDAD_CHOICES, verbose_name="Severidad")
    mensaje = models.TextField(verbose_name="Mensaje explicativo")
    valor_observado = models.FloatField(null=True, blank=True, verbose_name="Valor observado")
    valor_esperado = models.FloatField(null=True, blank=True, verbose_name="Valor esperado")
    leida = models.BooleanField(default=False, verbose_name="Leída")
    creada_en = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de generación")

    class Meta:
        verbose_name = "Alerta"
        verbose_name_plural = "Alertas"
        ordering = ['-fecha', '-creada_en']
        indexes = [
            models.Index(fields=['granja', 'leida', 'fecha']),
        ]

    def __str__(self):
        return f"[{self.severidad}] {self.tipo} en {self.lote.nombre} ({self.fecha})"
