from rest_framework import status, viewsets, serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.throttling import AnonRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView
from django.utils import timezone
from drf_spectacular.utils import extend_schema, inline_serializer

from apps.cuentas.models import Usuario
from apps.cuentas.serializers import (
    LoginSerializer,
    UserMeSerializer,
    CambiarPasswordSerializer,
    UsuarioAdminSerializer
)
from apps.cuentas.permissions import EsAdmin, GranjaScopedMixin, PermisoSuscripcionActiva


class HealthCheckView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        responses={200: inline_serializer('HealthCheckResponse', fields={'status': serializers.CharField()})},
        summary="Health check para Render"
    )
    def get(self, request):
        return Response({"status": "ok"}, status=status.HTTP_200_OK)


class LoginThrottle(AnonRateThrottle):
    rate = '10/minute'


class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [LoginThrottle]

    @extend_schema(request=LoginSerializer, responses={200: UserMeSerializer}, summary="Inicio de sesión por email")
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']

        refresh = RefreshToken.for_user(user)
        user_serializer = UserMeSerializer(user)

        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': user_serializer.data
        }, status=status.HTTP_200_OK)


class CustomTokenRefreshView(TokenRefreshView):
    @extend_schema(summary="Refrescar token de acceso")
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            # Asegurar formato exacto {access: "..."}
            return Response({'access': response.data.get('access')}, status=status.HTTP_200_OK)
        return response


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: UserMeSerializer}, summary="Obtener usuario actual")
    def get(self, request):
        serializer = UserMeSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)


class CambiarPasswordView(APIView):
    permission_classes = [IsAuthenticated, PermisoSuscripcionActiva]

    @extend_schema(
        request=CambiarPasswordSerializer,
        responses={200: inline_serializer('CambiarPasswordResponse', fields={'detail': serializers.CharField()})},
        summary="Cambiar contraseña"
    )
    def post(self, request):
        serializer = CambiarPasswordSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = request.user
        user.set_password(serializer.validated_data['password_nueva'])
        user.save()
        return Response({"detail": "Contraseña actualizada exitosamente."}, status=status.HTTP_200_OK)


class AceptarTerminosView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={200: UserMeSerializer}, summary="Aceptar términos y tratamiento de datos (Ley 1581 de 2012)")
    def post(self, request):
        user = request.user
        user.acepto_terminos_en = timezone.now()
        user.save(update_fields=['acepto_terminos_en'])
        serializer = UserMeSerializer(user)
        return Response(serializer.data, status=status.HTTP_200_OK)


class UsuarioViewSet(GranjaScopedMixin, viewsets.ModelViewSet):
    queryset = Usuario.objects.all()
    serializer_class = UsuarioAdminSerializer
    permission_classes = [IsAuthenticated, EsAdmin, PermisoSuscripcionActiva]

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return Usuario.objects.none()
        if user.is_superuser and not user.granja_id:
            return Usuario.objects.all()
        return Usuario.objects.filter(granja=user.granja)

    def perform_destroy(self, instance):
        # Desactivar usuario en lugar de borrarlo físicamente
        instance.activo = False
        instance.save(update_fields=['activo'])
