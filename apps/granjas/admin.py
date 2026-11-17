from django.contrib import admin
from apps.granjas.models import Granja, Galpon, Lote, EstandarSemanal


@admin.register(Granja)
class GranjaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'municipio', 'dias_edicion_operario', 'creada_en')
    search_fields = ('nombre', 'municipio')


@admin.register(Galpon)
class GalponAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'granja', 'capacidad', 'activo')
    list_filter = ('granja', 'activo')
    search_fields = ('nombre', 'granja__nombre')


class EstandarSemanalInline(admin.TabularInline):
    model = EstandarSemanal
    extra = 1


@admin.register(Lote)
class LoteAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'granja', 'galpon', 'linea_genetica', 'fecha_ingreso', 'aves_iniciales', 'estado')
    list_filter = ('granja', 'estado', 'linea_genetica')
    search_fields = ('nombre', 'granja__nombre', 'galpon__nombre')
    inlines = [EstandarSemanalInline]


@admin.register(EstandarSemanal)
class EstandarSemanalAdmin(admin.ModelAdmin):
    list_display = ('lote', 'semana', 'postura_esperada_pct', 'mortalidad_max_semanal_pct', 'consumo_g_ave_dia')
    list_filter = ('lote__granja', 'semana')
    search_fields = ('lote__nombre',)
