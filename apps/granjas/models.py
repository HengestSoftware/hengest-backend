from django.db import models
from datetime import date
import math


class Granja(models.Model):
    nombre = models.CharField(max_length=150, verbose_name="Nombre de la granja")
    municipio = models.CharField(max_length=100, verbose_name="Municipio")
    dias_edicion_operario = models.PositiveIntegerField(
        default=3,
        verbose_name="Días de edición permitidos para operario"
    )
    umbral_postura_pts = models.FloatField(
        default=5.0,
        verbose_name="Umbral de caída de postura (puntos porcentuales)"
    )
    umbral_postura_critico_pts = models.FloatField(
        default=10.0,
        verbose_name="Umbral crítico de postura (puntos porcentuales)"
    )
    umbral_consumo_pct = models.FloatField(
        default=15.0,
        verbose_name="Umbral de desviación de consumo (%)"
    )
    umbral_consumo_critico_pct = models.FloatField(
        default=25.0,
        verbose_name="Umbral crítico de desviación de consumo (%)"
    )
    umbral_mortalidad_diaria_pct = models.FloatField(
        default=0.15,
        verbose_name="Umbral de mortalidad diaria (%)"
    )
    creada_en = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de creación")

    class Meta:
        verbose_name = "Granja"
        verbose_name_plural = "Granjas"
        ordering = ['nombre']

    def __str__(self):
        return f"{self.nombre} ({self.municipio})"


class Galpon(models.Model):
    granja = models.ForeignKey(
        Granja,
        on_delete=models.CASCADE,
        related_name="galpones",
        verbose_name="Granja"
    )
    nombre = models.CharField(max_length=100, verbose_name="Nombre del galpón")
    capacidad = models.PositiveIntegerField(verbose_name="Capacidad de aves")
    activo = models.BooleanField(default=True, verbose_name="Activo")

    class Meta:
        verbose_name = "Galpón"
        verbose_name_plural = "Galpones"
        constraints = [
            models.UniqueConstraint(fields=['granja', 'nombre'], name='unique_galpon_por_granja')
        ]
        ordering = ['granja', 'nombre']

    def __str__(self):
        return f"{self.nombre} - {self.granja.nombre}"


class Lote(models.Model):
    ESTADO_CHOICES = [
        ('ACTIVO', 'Activo'),
        ('CERRADO', 'Cerrado'),
    ]

    granja = models.ForeignKey(
        Granja,
        on_delete=models.CASCADE,
        related_name="lotes",
        verbose_name="Granja"
    )
    galpon = models.ForeignKey(
        Galpon,
        on_delete=models.CASCADE,
        related_name="lotes",
        verbose_name="Galpón"
    )
    nombre = models.CharField(max_length=100, verbose_name="Nombre del lote")
    linea_genetica = models.CharField(max_length=100, verbose_name="Línea genética")
    fecha_ingreso = models.DateField(verbose_name="Fecha de ingreso")
    edad_inicial_semanas = models.PositiveIntegerField(verbose_name="Edad inicial (semanas)")
    aves_iniciales = models.PositiveIntegerField(verbose_name="Aves iniciales")
    peso_promedio_huevo_g = models.FloatField(
        null=True,
        blank=True,
        verbose_name="Peso promedio de huevo (g)"
    )
    estado = models.CharField(
        max_length=10,
        choices=ESTADO_CHOICES,
        default='ACTIVO',
        verbose_name="Estado"
    )
    fecha_cierre = models.DateField(null=True, blank=True, verbose_name="Fecha de cierre")

    class Meta:
        verbose_name = "Lote"
        verbose_name_plural = "Lotes"
        constraints = [
            models.UniqueConstraint(fields=['granja', 'nombre'], name='unique_lote_por_granja')
        ]
        ordering = ['-fecha_ingreso', 'nombre']

    def __str__(self):
        return f"{self.nombre} ({self.linea_genetica}) - {self.granja.nombre}"

    @property
    def semana_vida(self):
        hoy = date.today()
        dias = (hoy - self.fecha_ingreso).days
        return self.edad_inicial_semanas + math.floor(dias / 7)

    @property
    def aves_vivas(self):
        # Aves iniciales - mortalidad acumulada - descarte acumulado hasta hoy
        from apps.produccion.models import RegistroDiario
        totales = RegistroDiario.objects.filter(lote=self).aggregate(
            tot_mortalidad=models.Sum('mortalidad'),
            tot_descarte=models.Sum('descarte')
        )
        mortalidad = totales['tot_mortalidad'] or 0
        descarte = totales['tot_descarte'] or 0
        return max(0, self.aves_iniciales - mortalidad - descarte)


class EstandarSemanal(models.Model):
    lote = models.ForeignKey(
        Lote,
        on_delete=models.CASCADE,
        related_name="estandares",
        verbose_name="Lote"
    )
    semana = models.PositiveIntegerField(verbose_name="Semana de vida")
    postura_esperada_pct = models.FloatField(verbose_name="Postura esperada (%)")
    mortalidad_max_semanal_pct = models.FloatField(verbose_name="Mortalidad máx. semanal (%)")
    consumo_g_ave_dia = models.FloatField(verbose_name="Consumo alimento esperado (g/ave/día)")

    class Meta:
        verbose_name = "Estándar Semanal"
        verbose_name_plural = "Estándares Semanales"
        constraints = [
            models.UniqueConstraint(fields=['lote', 'semana'], name='unique_estandar_por_lote_semana')
        ]
        ordering = ['lote', 'semana']

    def __str__(self):
        return f"Lote {self.lote.nombre} - Sem {self.semana}: {self.postura_esperada_pct}%"
