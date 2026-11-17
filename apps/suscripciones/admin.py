from django.contrib import admin
from apps.suscripciones.models import Suscripcion, Pago


@admin.register(Suscripcion)
class SuscripcionAdmin(admin.ModelAdmin):
    list_display = ('granja', 'plan', 'estado', 'precio_cop', 'fecha_inicio', 'fecha_proximo_cobro', 'dias_gracia')
    list_filter = ('plan', 'estado')
    search_fields = ('granja__nombre',)


@admin.register(Pago)
class PagoAdmin(admin.ModelAdmin):
    list_display = ('referencia', 'granja', 'plan', 'monto_cop', 'estado', 'wompi_transaction_id', 'creado_en')
    list_filter = ('estado', 'plan')
    search_fields = ('referencia', 'granja__nombre', 'wompi_transaction_id')
    readonly_fields = [f.name for f in Pago._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
