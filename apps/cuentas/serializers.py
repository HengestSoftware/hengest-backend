from rest_framework import serializers
from django.contrib.auth import authenticate, password_validation
from django.utils import timezone
from apps.cuentas.models import Usuario
from apps.granjas.models import Granja


class GranjaResumenSerializer(serializers.ModelSerializer):
    class Meta:
        model = Granja
        fields = ['id', 'nombre', 'municipio']


class UserMeSerializer(serializers.ModelSerializer):
    granja = GranjaResumenSerializer(read_only=True)

    class Meta:
        model = Usuario
        fields = ['id', 'email', 'nombre', 'rol', 'acepto_terminos_en', 'granja']


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = attrs.get('email', '').strip().lower()
        password = attrs.get('password')

        user = authenticate(username=email, password=password)
        if not user:
            # Fallback manual por si el backend de autenticación espera email
            try:
                usuario_obj = Usuario.objects.get(email__iexact=email)
                if usuario_obj.check_password(password):
                    user = usuario_obj
            except Usuario.DoesNotExist:
                pass

        if not user:
            raise serializers.ValidationError({"detail": "Credenciales inválidas.", "code": "credenciales_invalidas"})

        if not user.activo:
            raise serializers.ValidationError({"detail": "El usuario se encuentra inactivo.", "code": "usuario_inactivo"})

        attrs['user'] = user
        return attrs


class CambiarPasswordSerializer(serializers.Serializer):
    password_actual = serializers.CharField(required=True)
    password_nueva = serializers.CharField(required=True)

    def validate_password_actual(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("La contraseña actual no es correcta.")
        return value

    def validate_password_nueva(self, value):
        user = self.context['request'].user
        password_validation.validate_password(value, user)
        return value


class UsuarioAdminSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = Usuario
        fields = ['id', 'email', 'nombre', 'rol', 'activo', 'password']

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        request = self.context.get('request')
        granja = request.user.granja if request else None

        user = Usuario.objects.create(granja=granja, **validated_data)
        if password:
            password_validation.validate_password(password, user)
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            password_validation.validate_password(password, instance)
            instance.set_password(password)
        instance.save()
        return instance
