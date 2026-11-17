from django.contrib import admin
from apps.cuentas.models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(admin.ModelAdmin):
    list_display = ('email', 'nombre', 'rol', 'granja', 'activo', 'is_staff', 'creado_en')
    list_filter = ('rol', 'activo', 'is_staff', 'granja')
    search_fields = ('email', 'nombre', 'granja__nombre')
    ordering = ('email',)
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Información Personal', {'fields': ('nombre', 'rol', 'granja')}),
        ('Permisos y Estado', {'fields': ('activo', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Términos y Fechas', {'fields': ('acepto_terminos_en', 'last_login', 'creado_en')}),
    )
    readonly_fields = ('last_login', 'creado_en')
