# Itzaka — Backend

> Del plano a la obra, todo conectado.

API del cotizador para arquitectos **Itzaka** (una solución de Grupo Torres Muciño). Permite registrar tarifas
(precio por m², metro lineal, piso/muro, etc.), clientes, cotizaciones,
avances de proyecto con evidencia fotográfica, y pagos (totales o parciales)
con su comprobante, hasta el cierre del proyecto con documento resumen.

## Módulos

- **Cuenta y acceso:** registro con correo y contraseña confirmado con un código,
  acceso, recuperación de contraseña, cambio de correo, suscripción y
  eliminación de la cuenta.
- **Catálogo, clientes y cotizaciones:** servicios con su unidad y precio,
  clientes y cotizaciones con total automático, con su documento PDF que se
  descarga o se envía por correo; la que sale de un plano guarda cuánto de cada
  partida cae en cada habitación, para desglosarla por habitación.
- **Proyectos, avances y cierre:** una cotización se vuelve proyecto; los avances
  se registran por cantidad con evidencia fotográfica y el cierre entrega su
  documento resumen.
- **Cobros y personal:** pagos totales o parciales con comprobante y saldo, y el
  personal que ejecuta la obra con lo que se le paga.
- **Planos 2D y 3D:** los planos de cada empresa con su biblioteca de modelos y
  texturas, la foto de un plano en papel convertida en plano editable y la
  cotización que sale del plano.
- **Inicio:** el resumen de la cuenta: obras en curso, lo cotizado y lo cobrado.
- **Colaboradores:** el administrador invita por correo; cada persona trabaja en
  las empresas que la invitan y sólo el administrador decide la organización.
- **Folios de documentos:** cada cotización, estado de proyecto y comprobante
  nace con su folio, que asigna el servidor y guarda en el documento. Por tipo
  de documento, la empresa elige «Autogenerado» (aleatorio, `COT-1A2B3C4D`) o
  «Con clave» (hasta 5 letras o números y un consecutivo que nunca se reinicia,
  `VEN-101`); el folio es único dentro de la empresa y cambiar la modalidad no
  toca lo ya creado (`apps.folios`, `GET/PUT /api/folio-settings/`).

## Estado

<!-- readme:auto:version -->

**Versión:** 4.0.0 — `pyproject.toml` · historial en [CHANGELOG.md](CHANGELOG.md)

<!-- /readme:auto:version -->

<!-- readme:auto:entornos -->

Pendiente: `python3 scripts/readme_sync.py --write --kind backend --docs <memoria>` llena esta tabla desde `estado/proyecto.json` de la memoria del proyecto.

<!-- /readme:auto:entornos -->

## Stack

<!-- readme:auto:stack -->

| Paquete | Versión declarada |
|---|---|
| `anthropic` | `>=1,<2` |
| `boto3` | `>=1.35,<2` |
| `django` | `>=5.2,<6.2` |
| `django-cors-headers` | `>=4.4,<5` |
| `django-csp` | `>=4,<5` |
| `django-environ` | `>=0.11,<0.15` |
| `django-filter` | `>=24.3,<27` |
| `django-phonenumber-field[phonenumbers]` | `>=8,<9` |
| `django-storages[s3]` | `>=1.14,<2` |
| `django-unfold` | `>=0.110,<0.111` |
| `djangorestframework` | `>=3.17.2,<3.19` |
| `djangorestframework-simplejwt` | `>=5.3,<6` |
| `filetype` | `>=1.2.0` |
| `numpy` | `>=2,<3` |
| `opencv-python-headless` | `>=4.10,<6` |
| `pillow` | `>=13,<14` |
| `psycopg[binary]` | `>=3.2,<4` |
| `whitenoise` | `>=6.7,<7` |

Desarrollo y pruebas (`dev`): `factory-boy`, `pytest`, `pytest-cov`, `pytest-django`, `pytest-mock`, `ruff`.

Fuente: `pyproject.toml`; versiones exactas en `uv.lock`.

<!-- /readme:auto:stack -->

- **Django 5.2 + Django REST Framework**
- **PostgreSQL** (Neon en la nube, por entorno)
- Gestión de dependencias con **uv** (`pyproject.toml`)
- Lint/format con **ruff**
- Testing con **pytest** (TDD estricto: RED → GREEN por user story)

## Requisitos

<!-- readme:auto:requisitos -->

- Python `>=3.12` (`requires-python`)
- [uv](https://docs.astral.sh/uv/): entorno y dependencias (no hay `requirements.txt`)
- PostgreSQL accesible por `DATABASE_URL`
- Git

<!-- /readme:auto:requisitos -->

## Puesta en marcha

<!-- readme:auto:puesta-en-marcha -->

1. Clona el repositorio y entra en su carpeta.
2. Instala las dependencias (runtime, desarrollo y pruebas) desde `uv.lock`: `uv sync --locked --all-groups`
3. Copia las variables y complétalas con los valores del equipo (`src/core/.env` nunca se commitea): `cp src/core/.env.example src/core/.env` — `DATABASE_URL` apunta a tu PostgreSQL local
4. Aplica las migraciones: `uv run python src/manage.py migrate`
5. Crea la tabla de caché (throttling): `uv run python src/manage.py createcachetable`
6. Crea un superusuario para el admin: `uv run python src/manage.py createsuperuser`
7. Levanta el servidor: `uv run python src/manage.py runserver` → http://localhost:8000 (admin en `/admin/`)

<!-- /readme:auto:puesta-en-marcha -->

## Variables de entorno

<!-- readme:auto:variables -->

Archivo: `src/core/.env.example` → cópialo a `src/core/.env`. Aquí solo van los nombres: los valores nunca se escriben en el README ni se commitean.

| Variable | Descripción |
|---|---|
| `DEBUG` | — |
| `SECRET_KEY` | — |
| `ALLOWED_HOSTS` | — |
| `CORS_ALLOWED_ORIGINS` | Exact origins, comma separated, never wildcards (also trusted for CSRF). |
| `CSRF_TRUSTED_ORIGINS` | Extra exact origins trusted for CSRF, besides the CORS ones. |
| `CSRF_COOKIE_DOMAIN` | Empty: host-only cookie (the SPA calls /api on its own domain). |
| `CSRF_COOKIE_NAME` | Per environment when two share a domain; the SPA repeats it (VITE_CSRF_COOKIE_NAME). |
| `DATABASE_URL` | — |
| `CONN_MAX_AGE` | Neon: DATABASE_URL is the pooled host (-pooler, transaction mode); keep 0 there. |
| `DATABASE_URL_UNPOOLED` | Direct (unpooled) host, for migrate and createcachetable (never the pooler). |
| `DATABASE_URL_MIGRATIONS` | Direct host with the owner role (multi-company); preferred for migrations. |
| `LOG_DIR` | — |
| `OTP_UNIVERSAL_CODE` | — |
| `OTP_UNIVERSAL_CODE_ENABLED` | Only opens accounts while mail is not configured, and only where enabled: on by default with DEBUG, off in production unless set on purpose. |
| `OTP_TTL_MINUTES` | — |
| `OTP_MAX_ATTEMPTS` | Failed tries a code survives before it is voided. |
| `RECAPTCHA_SECRET_KEY` | Verification turns on with the secret key (RECAPTCHA_ENABLED follows it). The site key goes to the frontend as VITE_RECAPTCHA_SITE_KEY: set both. |
| `RECAPTCHA_MIN_SCORE` | — |
| `RECAPTCHA_HOSTNAMES` | — |
| `RESEND_API_KEY` | Without the key no email goes out. Production refuses to deploy without it. |
| `RESEND_FROM` | A sender of a domain verified in Resend: its test sender (onboarding@resend.dev) only delivers to the Resend account owner, and production refuses it too. |
| `APP_BASE_URL` | Where the links in the emails lead: the application, not the API. |
| `REQUIRE_EMAIL_DELIVERY` | On by default where VERCEL_ENV=production: `migrate` stops the deploy when mail cannot go out, and a mail that cannot be sent is logged as an error. |
| `THROTTLE_ANON` | Run `uv run python src/manage.py createcachetable` once after migrating. |
| `THROTTLE_USER` | — |
| `NUM_PROXIES` | Proxies in front of Django (Vercel = 1), so limits key on the client IP. |
| `R2_ACCOUNT_ID` | — |
| `R2_ACCESS_KEY_ID` | — |
| `R2_SECRET_ACCESS_KEY` | — |
| `R2_BUCKET_NAME` | — |
| `R2_ENDPOINT_URL` | Optional: defaults to https://<account_id>.r2.cloudflarestorage.com |
| `R2_PUBLIC_URL` | Public host that serves the objects (r2.dev subdomain or your custom domain) |
| `R2_SIGNED_URLS` | Private bucket: signed URLs that expire, from the S3 endpoint (not the public host). Turn on after making the bucket private and allowing the app's origin in the bucket's CORS policy (the 3D editor fetches textures and meshes). |
| `R2_SIGNED_URL_SECONDS` | — |

<!-- /readme:auto:variables -->

## Comandos

<!-- readme:auto:comandos -->

| Comando | Para qué |
|---|---|
| `uv run python src/manage.py runserver` | Servidor de desarrollo |
| `uv run python src/manage.py makemigrations` | Crea migraciones tras cambiar modelos |
| `uv run python src/manage.py migrate` | Aplica las migraciones |
| `uv run pytest` | Pruebas (con cobertura: ver Pruebas y quality gate) |
| `uv run ruff format .` | Formato |
| `uv run ruff check .` | Lint (`--fix` corrige) |
| `uv add <paquete>` | Agrega una dependencia de runtime (`--group dev` para desarrollo) |

<!-- /readme:auto:comandos -->

## Pruebas y quality gate

<!-- readme:auto:pruebas -->

Pasos de `quality-gate` (`.github/workflows/quality-gate.yml`), en orden; los mismos comandos sirven en local (con el valor de `MIN_COVERAGE` ya puesto):

1. `uv sync --locked --all-groups`
2. `uv run ruff check .`
3. `rm -rf reports coverage && mkdir -p reports`
4. Pruebas con cobertura (el resultado lo decide el gate): `uv run pytest --junitxml=reports/junit.xml --cov --cov-report=xml:reports/coverage.xml --cov-report=term`
5. Quality gate: `python3 scripts/test_gate.py --junit reports/junit.xml --cobertura reports/coverage.xml --min 0.90 --allow-skip-reason 'got empty parameter set'`
6. README sincronizado (git-deploy-ops readme-format.md): `python3 scripts/readme_sync.py --check --kind backend`

Cobertura mínima: **90 %** (`MIN_COVERAGE` del workflow). Una prueba en rojo, una omitida sin motivo permitido o una cobertura menor bloquean el merge.

| Workflow | Check | Obligatorio en `main` y `develop` |
|---|---|---|
| `.github/workflows/quality-gate.yml` | `quality-gate` | sí |
| `.github/workflows/security.yml` | `security` | sí |

<!-- /readme:auto:pruebas -->

## Estructura de ramas

<!-- readme:auto:estructura -->

| Ruta | Contenido |
|---|---|
| `src/api/` | URLs raíz de la API (incluye las de cada app) |
| `src/apps/` | Apps de dominio (tabla abajo) |
| `src/common/` | Código compartido: modelos abstractos, permisos, paginación, filtros, acciones masivas, errores |
| `src/core/` | Settings, URLs, WSGI/ASGI y middleware |
| `src/templates/` | Plantillas |
| `src/tests/` | Pruebas de plataforma (línea base) |
| `scripts/` | Scripts vendorizados (quality gate, README) y de build |
| `.github/workflows/` | CI |

| App | Nombre (`verbose_name`) |
|---|---|
| `apps.accounts` | Cuentas |
| `apps.assets` | Archivos del editor |
| `apps.catalog` | Catálogo |
| `apps.clients` | Clientes |
| `apps.dashboard` | Inicio |
| `apps.documents` | Documentos |
| `apps.folios` | Folios de documentos |
| `apps.leads` | contactos |
| `apps.legal` | documentos legales |
| `apps.payments` | Pagos |
| `apps.planner` | Planos |
| `apps.projects` | Proyectos |
| `apps.quotes` | Cotizaciones |
| `apps.staff` | Personal |
| `apps.team` | Colaboradores |

<!-- /readme:auto:estructura -->

- `main` → producción.
- `develop` → integración (protegida: sólo pull requests con pruebas en verde y
  cobertura ≥ 90 %).
- `iteracion-N` → rama de trabajo de cada iteración, que entra a `develop` por
  pull request.

## API

<!-- readme:auto:api -->

Pendiente: la tabla sale de `uv run python src/manage.py api_routes --format md` (django-backend-conventions) al correr `readme_sync.py --write` con Django instalado.

<!-- /readme:auto:api -->

Todas las listas paginan en el servidor: `?page=&page_size=` (20 por omisión,
máximo 100) y responden `{count, next, previous, results}`. Cada una declara
sus filtros (`filters.py` de su app; `?campo=a,b` para varios valores), su
búsqueda (`?search=`, sin acentos ni mayúsculas) y su orden (`?ordering=`,
con lista blanca y desempate por id). Las acciones sobre varios registros son
`POST /api/<recurso>/bulk/<acción>/` con `{"ids": [...]}` o
`{"select_all": true, "exclude_ids": [...]}` más la query string de la lista, y
responden `{requested, processed, failed}` (`common/bulk.py`).

## Autenticación y sesión

- Web: sesión con JWT en cookies `HttpOnly` que emite la API
  (`POST /api/auth/login/`; `POST /api/auth/refresh/` rota el refresh y el
  anterior queda en la lista negra; `POST /api/auth/logout/`). La SPA pide
  `GET /api/auth/csrf/` al arrancar: deja la cookie CSRF (`CSRF_COOKIE_NAME`,
  `csrftoken` por omisión) y cada escritura lleva la cabecera `X-CSRFToken`. El
  navegador nunca lee ni envía tokens: no hay `Authorization: Bearer` para la
  web, y la aplicación llama a la API por su propio dominio (`/api/*`).
- Registro con correo y contraseña; la cuenta se confirma con un código de 6
  dígitos que llega por correo (`/api/auth/verify-otp/`, `/api/auth/resend-otp/`).
  La contraseña se recupera también con un código.
- Colaboradores: entran por el enlace de su invitación
  (`/api/invitations/<token>/accept/`), que crea la cuenta ya confirmada o pide la
  contraseña de quien ya tiene una.
- Empresa activa: la cabecera `X-Empresa` (el id de la cuenta de su
  administrador); sin ella, la propia o la primera donde se colabora. Sin acceso
  a la pedida, 403 con `code: company_access`.
- Formularios públicos (registro, acceso, recuperación, contacto e invitación):
  reCAPTCHA v3 verificado en el servidor y campo trampa.
- Sin app móvil: no hay rutas `/api/auth/mobile/`.

## Integraciones

### Correo — Resend

Los códigos de verificación, las invitaciones y los documentos salen por la API
HTTP de Resend (`common/mail.py`); las invitaciones de una tanda, en una sola
petición. En producción el despliegue se detiene si falta la llave o el
remitente es el de prueba (`common/checks.py`, corre con `migrate`).

| Variable | Uso |
|---|---|
| `RESEND_API_KEY` | Llave de la API; sin ella no sale ningún correo |
| `RESEND_FROM` | Remitente de un dominio verificado en Resend; el de prueba (`onboarding@resend.dev`) sólo entrega al dueño de la cuenta |
| `APP_BASE_URL` | Dominio de la aplicación en los enlaces de los correos |
| `REQUIRE_EMAIL_DELIVERY` | Correo obligatorio; encendido por omisión con `VERCEL_ENV=production` |
| `DOCUMENT_EMAIL_MAX_BYTES` | Tope del PDF que viaja adjunto |

### Archivos — Cloudflare R2

Logotipos, evidencia de los avances y las texturas y modelos del editor, por
`django-storages` (`core/settings_storages.py`).

| Variable | Uso |
|---|---|
| `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME` | Cuenta, credenciales y bucket; con las cuatro se activa R2 |
| `R2_ENDPOINT_URL`, `R2_PUBLIC_URL` | Endpoint S3 y host público de los objetos |
| `R2_SIGNED_URLS`, `R2_SIGNED_URL_SECONDS` | URLs firmadas que vencen, para un bucket privado |
| `USE_R2` | Fuerza R2 encendido o apagado |

### IA — Anthropic

La foto de un plano en papel se convierte en un plano editable
(`apps/planner/photo_conversion.py`).

| Variable | Uso |
|---|---|
| `ANTHROPIC_API_KEY` | Llave de la API |
| `PHOTO_PLAN_MODEL` | Modelo que lee la foto |
| `PHOTO_PLAN_DAILY_LIMIT` | Conversiones por cuenta al día |
| `PHOTO_PLAN_MAX_BYTES` | Tope de la foto |

### reCAPTCHA v3 — Google

Verificación de los formularios públicos en el servidor (`common/recaptcha.py`).

| Variable | Uso |
|---|---|
| `RECAPTCHA_SECRET_KEY` | Llave secreta; con ella se enciende la verificación |
| `RECAPTCHA_MIN_SCORE` | Puntaje mínimo |
| `RECAPTCHA_HOSTNAMES` | Dominios desde los que se aceptan los tokens |

### Base de datos — Neon

PostgreSQL de Neon por entorno. La API usa `DATABASE_URL`, el host con pooler
(PgBouncer en modo transacción): conexiones de una petición
(`CONN_MAX_AGE`, 0 por omisión), revisadas antes de reusarse y sin cursores del
servidor (`core/settings.py`). Las migraciones y la tabla de caché van por el
host directo: `DATABASE_URL_MIGRATIONS` (rol dueño) o, si no está,
`DATABASE_URL_UNPOOLED`; sin ninguna de las dos, el build se detiene.

## Administración

- Panel en `/admin/` del dominio de la API (Django Unfold); cada modelo de
  `apps/` tiene su registro, y las sesiones emitidas y anuladas (lista negra
  de simplejwt) se consultan ahí, de solo lectura las emitidas.
- Acceso: sólo el equipo de Itzaka, con un superusuario creado con
  `createsuperuser`; las cuentas de los clientes y sus colaboradores no entran
  al admin. Las credenciales nunca viven en el repositorio ni en este README.

## Despliegue

<!-- readme:auto:despliegue -->

Vercel (`vercel.json`):

- Despliegan: `develop`, `main` (el resto de las ramas no despliega) — `git.deploymentEnabled`.
- Build, en orden:
  1. `uv sync --frozen --no-dev`
  2. `DATABASE_URL="${DATABASE_URL_MIGRATIONS:-${DATABASE_URL_UNPOOLED:?falta DATABASE_URL_MIGRATIONS o DATABASE_URL_UNPOOLED}}" uv run --no-sync python src/manage.py migrate --noinput`
  3. `DATABASE_URL="${DATABASE_URL_MIGRATIONS:-$DATABASE_URL_UNPOOLED}" uv run --no-sync python src/manage.py createcachetable`
- Función: `wsgi.py` con `excludeFiles`.

<!-- /readme:auto:despliegue -->

- Producción: https://api-itzaka.grupotorresmucino.com (admin en `/admin/`); la
  aplicación la llama por su propio dominio, https://itzaka.grupotorresmucino.com/api/.
- Las variables por entorno (sólo nombres) viven en `tecnico/infraestructura.md`
  de la memoria del proyecto, que es privada.
- Cada entorno de Vercel (Production y Preview) necesita, además de
  `DATABASE_URL` (pooler), `DATABASE_URL_UNPOOLED` o `DATABASE_URL_MIGRATIONS`:
  el build migra por ahí. Vercel instala desde `uv.lock` (no hay
  `requirements.txt`).
- Verificación después de desplegar: `/api/health/` responde 200 y
  `/admin/login/` carga con sus estilos.

## Documentación

<!-- readme:auto:documentacion -->

- [CHANGELOG.md](CHANGELOG.md) — historial de versiones
- [.claude/CLAUDE.md](.claude/CLAUDE.md) — guía de desarrollo para personas y agentes
- [.claude/rules/contribucion.md](.claude/rules/contribucion.md) — reglas de contribución
- [.claude/rules/backend.md](.claude/rules/backend.md) — reglas del stack
- [CONTRIBUTING.md](CONTRIBUTING.md) — cómo contribuir (personas y GitHub)
- [AGENTS.md](AGENTS.md) — punto de entrada para otros agentes
- Memoria del proyecto `<proyecto>_docs`: producto, backlog, marca y prototipo en su sitio de documentación (enlace en [Estado](#estado) cuando se publica); infraestructura, despliegue y decisiones en `tecnico/` (privado).

<!-- /readme:auto:documentacion -->

## Contribución

<!-- readme:auto:contribucion -->

Este repositorio sigue el flujo de entrega del equipo. Reglas completas en [.claude/rules/contribucion.md](.claude/rules/contribucion.md) (para personas: [CONTRIBUTING.md](CONTRIBUTING.md)).

- `main` (producción) y `develop` (integración) están protegidas: nadie sube directo; todo entra por pull request.
- Se trabaja en `epica/EP-XX-<slug>` (primer flujo) o en `iteracion-N` (iteraciones), ramas creadas desde `develop`.
- Un commit por historia o item (`US-XX <nombre>` o `TEC <título>`) con el código, sus pruebas, la entrada del CHANGELOG y este README al día.
- El pull request a `develop` se integra solo con `quality-gate` (pruebas en verde y cobertura ≥ 90 %) y `security` en verde; los archivos del gate cambian solo como item `TEC` propio.
- ¿Un cambio fuera del flujo? Abre un issue o pide un item: nunca un push directo, un force-push ni secretos en el repositorio.

<!-- /readme:auto:contribucion -->

## Desarrollo

El código se construye por *user story* siguiendo el flujo de entrega del
equipo (Producto → Desarrollo TDD → Testing → Deploy). El backlog formal, la
fuente única de alcance, vive en la memoria del proyecto, el repositorio
[`itzaka_docs`](https://github.com/gabrieltorgar/itzaka_docs)
(`producto/4.0_Backlog_Producto.json`; sitio en https://cuotreka-docs.vercel.app), junto con la guía de despliegue que antes
era `DEPLOY.md` (`legado/backend/DEPLOY.md`). Variables de entorno: ver
`src/core/.env.example`.

> El scaffold del proyecto Django se genera al iniciar el desarrollo, tras la
> aprobación del backlog (GATE 1).

## Licencia

<!-- COMPLETA: la licencia que acordó el cliente (p. ej. "Software privado y confidencial de <cliente>; todos los derechos reservados."). -->
