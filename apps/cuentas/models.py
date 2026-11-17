from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager


class UsuarioManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('El email es obligatorio.')
        email = self.normalize_email(email)
        extra_fields.setdefault('activo', True)
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('rol', 'ADMIN')
        extra_fields.setdefault('activo', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('El superusuario debe tener is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('El superusuario debe tener is_superuser=True.')

        return self.create_user(email, password, **extra_fields)


class Usuario(AbstractBaseUser, PermissionsMixin):
    ROL_CHOICES = [
        ('ADMIN', 'Administrador'),
        ('OPERARIO', 'Operario'),
    ]

    email = models.EmailField(unique=True, verbose_name="Correo electrónico")
    nombre = models.CharField(max_length=150, verbose_name="Nombre completo")
    rol = models.CharField(
        max_length=15,
        choices=ROL_CHOICES,
        default='OPERARIO',
        verbose_name="Rol"
    )
    granja = models.ForeignKey(
        'granjas.Granja',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="usuarios",
        verbose_name="Granja"
    )
    activo = models.BooleanField(default=True, verbose_name="Activo")
    is_staff = models.BooleanField(default=False, verbose_name="Es Staff")
    acepto_terminos_en = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fecha de aceptación de términos y datos"
    )
    creado_en = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de creación")

    objects = UsuarioManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['nombre']

    class Meta:
        verbose_name = "Usuario"
        verbose_name_plural = "Usuarios"
        ordering = ['nombre', 'email']

    def __str__(self):
        granja_str = self.granja.nombre if self.granja else "Hengest Staff"
        return f"{self.nombre} ({self.email}) - {self.rol} @ {granja_str}"

    @property
    def is_active(self):
        return self.activo

    @is_active.setter
    def is_active(self, value):
        self.activo = bool(value)
