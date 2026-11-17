from django.contrib import admin
from apps.produccion.models import RegistroDiario, Vacunacion, Alerta


@admin.register(RegistroDiario)
class RegistroDiarioAdmin(admin.ModelAdmin):
    list_display = ('lote', 'fecha', 'aaa', 'aa', 'a', 'b', 'c', 'alimento_kg', 'mortalidad', 'descarte', 'creado_por')
    list_filter = ('lote__granja', 'fecha', 'lote')
    search_fields = ('lote__nombre', 'observaciones')
    date_hierarchy = 'fecha'


@admin.register(Vacunacion)
class VacunacionAdmin(admin.ModelAdmin):
    list_display = ('vacuna', 'lote', 'fecha_programada', 'fecha_aplicada', 'estado')
    list_filter = ('lote__granja', 'fecha_programada', 'fecha_aplicada')
    search_fields = ('vacuna', 'lote__nombre', 'notas')


@admin.register(Alerta)
class AlertaAdmin(admin.ModelAdmin):
    list_display = ('lote', 'fecha', 'tipo', 'severidad', 'mensaje', 'valor_observado', 'valor_esperado', 'leida', 'creada_en')
    list_filter = ('granja', 'tipo', 'severidad', 'leida', 'fecha')
    search_fields = ('lote__nombre', 'mensaje')
    readonly_fields = [f.name for f in Alerta._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
