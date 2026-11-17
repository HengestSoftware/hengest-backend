from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.cuentas.views import (
    HealthCheckView,
    LoginView,
    CustomTokenRefreshView,
    MeView,
    CambiarPasswordView,
    AceptarTerminosView,
    UsuarioViewSet
)
from apps.granjas.views import (
    GranjaView,
    GalponViewSet,
    LoteViewSet
)
from apps.produccion.views import (
    RegistroDiarioViewSet,
    VacunacionViewSet,
    AlertaViewSet
)
from apps.suscripciones.views import (
    SuscripcionView,
    PagosListView,
    CheckoutView,
    WompiWebhookView
)
from apps.reportes.views import (
    DashboardView,
    ReporteProduccionView
)

router = DefaultRouter()
router.register(r'galpones', GalponViewSet, basename='galpon')
router.register(r'lotes', LoteViewSet, basename='lote')
router.register(r'registros-diarios', RegistroDiarioViewSet, basename='registro-diario')
router.register(r'vacunaciones', VacunacionViewSet, basename='vacunacion')
router.register(r'alertas', AlertaViewSet, basename='alerta')
router.register(r'usuarios', UsuarioViewSet, basename='usuario')

api_v1_patterns = [
    # Health check
    path('health/', HealthCheckView.as_view(), name='health-check'),

    # Autenticación y Perfil
    path('auth/login/', LoginView.as_view(), name='auth-login'),
    path('auth/refresh/', CustomTokenRefreshView.as_view(), name='auth-refresh'),
    path('auth/me/', MeView.as_view(), name='auth-me'),
    path('auth/cambiar-password/', CambiarPasswordView.as_view(), name='auth-cambiar-password'),
    path('auth/aceptar-terminos/', AceptarTerminosView.as_view(), name='auth-aceptar-terminos'),

    # Configuración de Granja
    path('granja/', GranjaView.as_view(), name='granja-detail'),

    # Dashboard y Reportes
    path('dashboard/', DashboardView.as_view(), name='dashboard'),
    path('reportes/produccion/', ReporteProduccionView.as_view(), name='reportes-produccion'),

    # Suscripciones y Pagos Wompi
    path('suscripcion/', SuscripcionView.as_view(), name='suscripcion-detail'),
    path('suscripcion/pagos/', PagosListView.as_view(), name='suscripcion-pagos'),
    path('suscripcion/checkout/', CheckoutView.as_view(), name='suscripcion-checkout'),
    path('pagos/wompi/webhook/', WompiWebhookView.as_view(), name='wompi-webhook'),

    # Viewsets de DRF
    path('', include(router.urls)),
]

urlpatterns = [
    # Health check en raíz y en /health/ para compatibilidad con monitores Render
    path('health/', HealthCheckView.as_view(), name='root-health'),

    # Panel de administración de Django
    path('admin/', admin.site.urls),

    # Esquema OpenAPI y Swagger UI
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),

    # API v1
    path('api/v1/', include(api_v1_patterns)),
]
