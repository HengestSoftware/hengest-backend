# HENGEST Backend — Plataforma Avícola SaaS

Backend para **HENGEST**, plataforma web SaaS multi-tenant diseñada para la gestión técnica y operativa de la producción en pequeñas y medianas granjas avícolas de huevo comercial (gallinas ponedoras) en Andes, Antioquia, Colombia.

El sistema digitaliza el registro diario de recolección de huevos, alimento y mortalidad, convierte automáticamente las unidades en **cubetas de 30 unidades por categoría comercial (AAA, AA, A, B, C)**, calcula indicadores zootécnicos clave (tasa de postura, consumo por ave, conversión alimenticia) y emite **alertas automáticas** ante desviaciones frente a los estándares de la semana de vida del lote.

---

## 1. Requisitos del Sistema

- **Python:** 3.12 o superior (probado en Python 3.12.10)
- **Base de Datos:**
  - Desarrollo local: SQLite (`db.sqlite3`) o PostgreSQL
  - Producción: PostgreSQL en **Neon**
- **Gestor de paquetes:** `pip`

---

## 2. Instalación y Configuración Local

Sigue estos pasos dentro de la carpeta raíz del backend:

```bash
# 1. Crear el entorno virtual
python -m venv .venv

# 2. Activar el entorno virtual
# En Windows (PowerShell):
.\.venv\Scripts\Activate.ps1
# En Linux / macOS:
# source .venv/bin/activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar variables de entorno
# Copia el archivo de ejemplo a .env
cp .env.example .env

# 5. Ejecutar migraciones de la base de datos
python manage.py migrate

# 6. (Opcional) Cargar datos de demostración
python manage.py seed_demo

# 7. Iniciar el servidor de desarrollo
python manage.py runserver
```

El servidor estará disponible en `http://127.0.0.1:8000/`.

---

## 3. Variables de Entorno

El archivo `.env` permite configurar el comportamiento del backend:

| Variable | Descripción | Valor por defecto local |
|---|---|---|
| `DATABASE_URL` | Cadena de conexión para SQLite o Neon PostgreSQL | `sqlite:///db.sqlite3` |
| `SECRET_KEY` | Clave secreta criptográfica de Django | Generada para pruebas locales |
| `DEBUG` | Activa modo depuración | `True` en local, `False` en producción |
| `ALLOWED_HOSTS` | Hosts permitidos separados por comas | `localhost,127.0.0.1` |
| `CORS_ALLOWED_ORIGINS` | Orígenes permitidos para peticiones CORS | `http://localhost:5173` |
| `CSRF_TRUSTED_ORIGINS` | Orígenes confiables para protección CSRF | `http://localhost:5173` |
| `FRONTEND_URL` | URL base del cliente web para redirecciones Wompi | `http://localhost:5173` |
| `WOMPI_ENV` | Entorno de Wompi (`sandbox` o `production`) | `sandbox` |
| `WOMPI_PUBLIC_KEY` | Llave pública de Wompi | Opcional en desarrollo |
| `WOMPI_INTEGRITY_SECRET` | Secreto de firma de integridad de Wompi | Opcional en desarrollo |
| `WOMPI_EVENTS_SECRET` | Secreto para verificar webhooks de Wompi | Opcional en desarrollo |
| `PYTHON_VERSION` | Versión de Python para entornos de despliegue | `3.12.10` |

---

## 4. Datos de Demostración (`seed_demo`)

El comando `seed_demo` crea una granja de prueba completa con galpones, lotes, estándares semanales, 30 días de registros con anomalías de prueba, alertas y vacunaciones:

```bash
python manage.py seed_demo
```

### Credenciales de acceso de prueba (solo para entorno local):
- **Administrador:** `admin@demo.hengest.co` / Contraseña: `Demo2026*`
- **Operario:** `operario@demo.hengest.co` / Contraseña: `Demo2026*`

---

## 5. Pruebas Automáticas

Ejecuta el conjunto completo de pruebas unitarias y de integración:

```bash
python manage.py test
```

La suite cubre:
- Conversión matemática a cubetas (bordes 0, 29, 30, 31, 59, 60).
- Cálculo de aves vivas, postura %, consumo y conversión alimenticia.
- Reglas de alertas automáticas (advertencia, crítica, caída súbita, sin estándar).
- Aislamiento multi-tenant entre granjas.
- Permisos del operario (ventana de edición de 3 días, prohibición de borrado y restricción de módulos admin).
- Idempotencia del registro diario vía `client_uuid`.
- Bloqueo `402 Payment Required` (`suscripcion_inactiva`) ante suscripciones vencidas.
- Integración con Wompi: cálculo de firmas SHA256, verificación de webhooks e idempotencia.
- Formato del reporte en CSV (encabezados en español y codificación UTF-8 con BOM).

---

## 6. Documentación de la API (OpenAPI / Swagger)

Con el servidor en ejecución, accede a la documentación interactiva en:
- **Swagger UI:** [http://127.0.0.1:8000/api/docs/](http://127.0.0.1:8000/api/docs/)
- **OpenAPI Schema (JSON/YAML):** [http://127.0.0.1:8000/api/schema/](http://127.0.0.1:8000/api/schema/)

---

## 7. Endpoints de la API (`/api/v1`)

| Método | Ruta | Acceso | Descripción |
|---|---|---|---|
| `GET` | `/health/` | Público | Verificación de estado del servicio (`{"status":"ok"}`) |
| `POST` | `/api/v1/auth/login/` | Público | Autenticación con `{email, password}` -> `{access, refresh, user}` |
| `POST` | `/api/v1/auth/refresh/` | Público | Refrescar token `{refresh}` -> `{access}` |
| `GET` | `/api/v1/auth/me/` | Autenticado | Datos del usuario actual |
| `POST` | `/api/v1/auth/cambiar-password/` | Autenticado | Cambio de contraseña `{password_actual, password_nueva}` |
| `POST` | `/api/v1/auth/aceptar-terminos/` | Autenticado | Registro de aceptación de términos y datos (Ley 1581) |
| `GET` | `/api/v1/granja/` | Autenticado | Consulta de umbrales y configuración de la granja |
| `PATCH` | `/api/v1/granja/` | ADMIN | Modificación de umbrales y configuración |
| `GET`, `POST` | `/api/v1/galpones/` | Lectura ambos, Escritura ADMIN | CRUD de galpones |
| `GET`, `POST` | `/api/v1/lotes/` | Lectura ambos, Escritura ADMIN | CRUD de lotes de aves |
| `GET` | `/api/v1/lotes/{id}/resumen/` | Autenticado | Indicadores históricos acumulados del lote |
| `GET`, `PUT`| `/api/v1/lotes/{id}/estandares/` | GET ambos, PUT ADMIN | Estándares de producción por semana de vida |
| `GET`, `POST` | `/api/v1/registros-diarios/` | ADMIN / OPERARIO (ventana 3 días) | Registros de recolección y consumo |
| `GET`, `POST` | `/api/v1/vacunaciones/` | Lectura ambos, Escritura ADMIN | Plan de vacunación del lote |
| `POST` | `/api/v1/vacunaciones/{id}/aplicar/` | Autenticado | Marcar vacuna como aplicada |
| `GET`, `PATCH`| `/api/v1/alertas/` | Autenticado | Listado y marcado de lectura de alertas |
| `POST` | `/api/v1/alertas/marcar-todas-leidas/` | Autenticado | Marca todas las alertas de la granja como leídas |
| `GET` | `/api/v1/dashboard/` | Autenticado | Métricas del día, semáforos y series históricas |
| `GET` | `/api/v1/reportes/produccion/` | ADMIN | Reporte filtrado en JSON o CSV descargable |
| `GET`, `POST` | `/api/v1/usuarios/` | ADMIN | Gestión de usuarios de la granja |
| `GET` | `/api/v1/suscripcion/` | ADMIN | Estado y vencimiento de la suscripción |
| `GET` | `/api/v1/suscripcion/pagos/` | ADMIN | Historial de transacciones de pago |
| `POST` | `/api/v1/suscripcion/checkout/` | ADMIN | Generación de orden y firma Wompi |
| `POST` | `/api/v1/pagos/wompi/webhook/` | Público (Firma verificada) | Recepción de eventos de pago de Wompi |

---

## 8. Despliegue en Render

Consulta la guía detallada en [docs/DEPLOY_RENDER.md](docs/DEPLOY_RENDER.md) para conocer la configuración exacta del Web Service, variables en Render y conexión a Neon.
