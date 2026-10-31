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
| `ALLOWED_HOSTS` | API hosts (Vercel's deployment hosts are added): production api.itzaka.com, develop api-dev.itzaka.com. |
| `CORS_ALLOWED_ORIGINS` | SPA exact origins, comma separated, never wildcards (also trusted for CSRF): production https://itzaka.com, develop https://dev.itzaka.com. |
| `CSRF_TRUSTED_ORIGINS` | Extra exact origins trusted for CSRF, besides the CORS ones (usually empty). |
| `CSRF_COOKIE_DOMAIN` | Parent domain of the CSRF cookie the SPA reads: .itzaka.com in production and develop (the default without DEBUG); empty locally (host-only). JWT cookies never get a Domain. |
| `CSRF_COOKIE_NAME` | Django's default name in production and locally; develop adds the _dev suffix (both share .itzaka.com). The SPA repeats it (VITE_CSRF_COOKIE_NAME). |
| `DATABASE_URL` | — |
| `CONN_MAX_AGE` | Neon: DATABASE_URL is the pooled host (-pooler, transaction mode); keep 0 there. |
| `DATABASE_URL_UNPOOLED` | Direct (unpooled) host, for migrate and createcachetable (never the pooler). |
| `DATABASE_URL_MIGRATIONS` | Direct host with the owner role (multi-company); preferred for migrations. |
| `LOG_DIR` | — |
| `APP_ENV` | Which environment this is: develop, production or a developer machine; missing means production (fail closed), and a Vercel Production deployment is always production. |
| `OTP_UNIVERSAL_CODE` | E2E-only universal code: only with APP_ENV local or develop (settings refuse to load with it anywhere else, never in Vercel Production), only for OTP_UNIVERSAL_EMAILS and only to verify an account. |
| `OTP_UNIVERSAL_EMAILS` | Comma-separated accounts the universal code verifies (the E2E users). |
| `OTP_TTL_MINUTES` | — |
| `OTP_MAX_ATTEMPTS` | Failed tries a code survives before it is voided. |
| `OTP_RESEND_COOLDOWN_SECONDS` | Seconds between two codes for the same email and purpose (also for unknown emails). |
| `OTP_MAX_CODES_PER_HOUR` | Codes per hour for the same email and purpose. |
| `RECAPTCHA_SECRET_KEY` | Server-side secret key, one per environment. Its site key goes to the frontend as VITE_RECAPTCHA_SITE_KEY: set both together. Production (VERCEL_ENV=production) refuses to deploy without it (common.E003). |
| `RECAPTCHA_MIN_SCORE` | — |
| `RECAPTCHA_HOSTNAMES` | Hosts the tokens may come from: itzaka.com by default without DEBUG, the local one (this value) with DEBUG; develop dev.itzaka.com. |
| `RESEND_API_KEY` | Without the key no email goes out. Production refuses to deploy without it. |
| `RESEND_FROM` | A sender of a domain verified in Resend: its test sender (onboarding@resend.dev) only delivers to the Resend account owner, and production refuses it too. |
| `APP_BASE_URL` | Where the links in the emails lead: the application, not the API (production https://itzaka.com, develop https://dev.itzaka.com). |
| `REQUIRE_EMAIL_DELIVERY` | On by default where VERCEL_ENV=production: `migrate` stops the deploy when mail cannot go out, and a mail that cannot be sent is logged as an error. |
| `CRON_SECRET` | Vercel sends it as «Authorization: Bearer …» to the cron routes; without it they answer 401 and never run. |
| `THROTTLE_ANON` | Run `uv run python src/manage.py createcachetable` once after migrating. |
| `THROTTLE_USER` | — |
| `THROTTLE_COSTLY` | Per account per hour for actions that send email or call a paid API (documents, invitations, photo plans). |
| `ADMIN_LOGIN_MAX_FAILURES` | Failed admin logins from one IP or for one username before a 15-minute lock (429). |
| `NUM_PROXIES` | Proxies in front of Django (Vercel = 1), so limits key on the client IP. |
| `UPLOAD_MAX_BYTES` | Max bytes per file through the API (default 4 MiB): a Vercel function rejects bodies over 4.5 MB before Django. On Vercel any upload cap over 4 MiB stops the deploy (core.E002). |
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
2. `rm -rf reports coverage && mkdir -p reports`
3. Pruebas con cobertura (el resultado lo decide el gate): `uv run pytest --junitxml=reports/junit.xml --cov --cov-report=xml:reports/coverage.xml --cov-report=term`
4. Quality gate: `python3 scripts/test_gate.py --junit reports/junit.xml --cobertura reports/coverage.xml --min 0.90 --allow-skip-reason 'got empty parameter set'`
5. README sincronizado (git-deploy-ops readme-format.md): `python3 scripts/readme_sync.py --check --kind backend`

Cobertura mínima: **90 %** (`MIN_COVERAGE` del workflow). Una prueba en rojo, una omitida sin motivo permitido o una cobertura menor bloquean el merge.

| Workflow | Check | Obligatorio en `main` y `develop` |
|---|---|---|
| `.github/workflows/ci.yml` | `test-backend` | no |
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

La API lee sólo JSON: otro tipo de cuerpo responde 415. Las subidas
(logotipo, evidencia de un avance, foto de un plano, texturas y modelos, y el
PDF que se envía por correo) son `multipart/form-data`, declarado en su vista.
Cada archivo cabe en `UPLOAD_MAX_BYTES` (4 MiB por omisión): una función de
Vercel corta en 4.5 MB el cuerpo entero antes de Django, y en Vercel un tope
mayor detiene el despliegue (`core/checks.py`, `core.E002`, que revisa también
`PLAN_ASSET_MAX_BYTES`, `DOCUMENT_EMAIL_MAX_BYTES` y `PHOTO_PLAN_MAX_BYTES`;
el logotipo tiene el suyo, 2 MB). Cada subida se juzga por su contenido
(`common/validators.py`): la firma real (filetype), y toda imagen pasa por
Pillow `verify()` y un tope de píxeles (rota o descomunal es un 400, nunca un
500). El nombre guardado lo pone el servidor: un uuid y la extensión del tipo
detectado. Archivos de más de 4 MiB no tienen todavía una subida firmada al
bucket: hoy no entran.

Cabeceras de seguridad en cada respuesta (`core/settings_csp.py`,
`core/middleware.py`): la API lleva la Content-Security-Policy aplicada
`default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'`
(sirve JSON: nada que cargar ni quién la enmarque), además de
`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` y
`Referrer-Policy: same-origin`, también con `DEBUG`.

Todas las listas paginan en el servidor: `?page=&page_size=` (20 por omisión,
máximo 100) y responden `{count, next, previous, results}`. Cada una declara
sus filtros (`filters.py` de su app; `?campo=a,b` para varios valores), su
búsqueda (`?search=`, sin acentos ni mayúsculas) y su orden (`?ordering=`,
con lista blanca y desempate por id). Las acciones sobre varios registros son
`POST /api/<recurso>/bulk/<acción>/` con `{"ids": [...]}` o
`{"select_all": true, "exclude_ids": [...]}` más la query string de la lista, y
responden `{requested, processed, failed}` (`common/bulk.py`).

Estados, importes y dueño nunca los escribe el cliente: van de solo lectura en
cada serializer (y lo que el cuerpo mande de más se ignora), los importes los
calcula el servidor (el total y los subtotales de una cotización, lo ganado y
el precio de mano de obra de un avance) y el estado cambia sólo por su acción:
la cotización se vuelve proyecto con `POST /api/projects/`, el proyecto se cierra
con `POST /api/projects/{id}/finalize/` y la invitación se acepta o se cancela
con las suyas. Cada modelo con estado registra su tabla de transiciones en su
servicio (`common/state_machine.py`: cotización `draft → in_project`, proyecto
`in_progress → finished`, invitación `pending → accepted | cancelled`); un
estado final no tiene salida y una fila en él ya no se edita. Los servicios
revisan la tabla sobre la fila releída con `select_for_update` en su
transacción: un doble clic, un reintento o dos peticiones a la vez no hacen dos
proyectos de una cotización ni escriben en un proyecto ya finalizado, y dos
avances o repartos simultáneos no superan la partida. Las pruebas de
concurrencia real corren sólo con PostgreSQL (CI).

## Autenticación y sesión

- Web: sesión con JWT en cookies `HttpOnly` que emite la API
  (`POST /api/auth/login/`; `POST /api/auth/refresh/` rota el refresh de su
  cookie —nunca uno del cuerpo— y el anterior queda en la lista negra;
  `POST /api/auth/logout/`). Acceso, registro, código y recuperación no leen la
  sesión: una cookie vieja no los bloquea. Cada token lleva la huella de la
  contraseña (`CHECK_REVOKE_TOKEN`): cambiarla, recuperarla o ponerla en el admin
  deja fuera al instante a toda sesión anterior; quien la cambió sigue dentro con
  una nueva. La SPA pide
  `GET /api/auth/csrf/` al arrancar: deja la cookie CSRF (`CSRF_COOKIE_NAME`,
  `csrftoken` por omisión) y cada escritura lleva la cabecera `X-CSRFToken`. El
  navegador nunca lee ni envía tokens: no hay `Authorization: Bearer` para la
  web. La aplicación (`https://itzaka.com`) llama a la API en su subdominio
  (`https://api.itzaka.com`), el mismo sitio: las cookies JWT quedan sólo en la
  API (sin `Domain`) y la CSRF en `.itzaka.com` (`CSRF_COOKIE_DOMAIN`), para que
  la SPA la lea. Orígenes exactos en `CORS_ALLOWED_ORIGINS` (también de
  confianza para CSRF), con credenciales.
- Registro con correo y contraseña; la cuenta se confirma con un código de 6
  dígitos que llega por correo (`/api/auth/verify-otp/`, `/api/auth/resend-otp/`).
  Registrarse ya abre la sesión (sin verificar) y verificar el código abre una
  nueva, verificada: no se vuelve a pedir la contraseña. Límite del registro:
  5 por hora y dirección (`register`). La contraseña se recupera también con un
  código.
- Códigos de un solo uso (`OtpCode`, en `apps/accounts`): 6 dígitos de
  `secrets.randbelow`, guardados como HMAC con la `SECRET_KEY` (nunca en claro
  ni en el admin) y comparados en tiempo constante; vencen a los
  `OTP_TTL_MINUTES` y mueren a los `OTP_MAX_ATTEMPTS` intentos fallidos, que se
  cuentan en la fila bajo `select_for_update`. Pedir otro anula el anterior. El
  campo `code` acepta sólo `^[0-9]{6}\Z`, y un código equivocado responde 400
  `{"code": ["Código de verificación inválido"]}` sin lanzar excepción: el
  intento cuenta también con `ATOMIC_REQUESTS`.
- Pedir un código (reenvío, recuperación, correo nuevo y el acceso de una
  cuenta sin verificar) pasa antes por una cuota por correo y propósito, sin
  buscar la cuenta: `OTP_RESEND_COOLDOWN_SECONDS` entre envíos y
  `OTP_MAX_CODES_PER_HOUR` por hora; pasarse responde 429 con `Retry-After`,
  igual exista o no el correo (el acceso sin verificar sigue en su 403, sin
  mandar otro). El primer código, el del registro, no cuenta. Reenvío y
  recuperación responden siempre el mismo 200, y verificar o recuperar con un
  correo sin cuenta (o ya verificado) responde el mismo 400 que un código
  equivocado.
- Código universal (sólo para la suite E2E): `OTP_UNIVERSAL_CODE` no tiene
  valor por omisión y sólo puede existir con `APP_ENV` `local` o `develop`.
  Sin `APP_ENV` es `production`, y un despliegue Production de Vercel
  (`VERCEL_ENV=production`) lo es siempre: con el código en otro entorno los
  settings no cargan y el build falla. Sirve sólo para las cuentas de
  `OTP_UNIVERSAL_EMAILS` (correos exactos, separados por comas) y sólo para
  verificar la cuenta (`verify-otp/`); nunca para recuperar la contraseña ni
  para cambiar el correo. Cada uso queda en el log, sin el código. Sin correo
  configurado (en local) el código propio se emite igual, pero no llega: para
  probar el registro en local, `APP_ENV=local` con el código y tu correo en la
  lista.
- Cambio de correo (`me/email/`): el código va sólo al correo nuevo, la cuenta
  sigue con el de siempre hasta confirmarlo y el anterior recibe un aviso sin
  código. Cambiar la contraseña (`me/password/`) o recuperarla pasa por los
  validadores de Django y deja fuera a toda sesión anterior; quien la cambió
  sigue dentro con una nueva, y quien la recuperó entra con la nueva.
- Límites de intentos (DRF, en la caché compartida de la base): por dirección,
  el alcance de cada vista —acceso `login` 10/min, registro `register` 5/h,
  pedir código `otp_request` 3/min, verificar un código (también recuperar con
  él y confirmar el correo nuevo) `otp_verify` 10/min, pedir recuperar
  `password_reset` 5/h, `me/password/` y `me/delete/` `password_change` 5/h,
  contacto `contact` 5/h—, y por cuenta, sobre el correo enviado
  (`common.throttling.IdentifierRateThrottle`): `login_email` 20/h,
  `otp_email` 10/h, `password_reset_email` 3/h; rotar la dirección no los
  reinicia. Enviar un documento, invitar o reenviar una invitación y convertir
  la foto de un plano comparten `costly` (`THROTTLE_COSTLY`, 20/h por cuenta).
  Pasarse responde 429 con `Retry-After` (expuesto por CORS).
- Permiso por omisión `common.permissions.IsVerifiedUser`: sesión y correo
  verificado. Sin sesión, 401; con una cuenta sin verificar, 403 con
  `code: email_not_verified` (la SPA lleva a la pantalla del código). Sin
  verificar sólo responden `GET /api/auth/me/` y las rutas públicas de la sesión
  (código, reenvío, renovar, salir y CSRF).
- Colaboradores: entran por el enlace de su invitación
  (`/api/invitations/<token>/accept/`), que crea la cuenta ya confirmada o pide la
  contraseña de quien ya tiene una.
- Empresa activa: la cabecera `X-Empresa` (el id de la cuenta de su
  administrador); sin ella, la propia o la primera donde se colabora. Sin acceso
  a la pedida, 403 con `code: company_access`.
- Formularios públicos (registro, acceso, recuperación, contacto e invitación):
  reCAPTCHA v3 verificado en el servidor (`common/recaptcha.py`) y campo trampa
  (`website`). Si Google no contesta, las puertas de la cuenta (registro,
  acceso, recuperación e invitación) responden 503 y el contacto se guarda bajo
  su límite (`contact`, 5/h) marcado para revisar (`needs_review`). Con el campo
  trampa lleno responden lo de siempre sin efecto: el registro, la recuperación,
  el contacto y la invitación su 2xx (la invitación, el 404, 409 o 410 de un
  enlace que no sirve, como la vía real); el acceso, el mismo 401 de unas
  credenciales malas (un 2xx sin la sesión dejaría a la SPA creyendo que entró).
  Un cuerpo que no es un objeto JSON es un 400; el cuerpo tiene tope
  (`DATA_UPLOAD_MAX_MEMORY_SIZE`, 5 MB) y cada campo de texto el suyo
  (contraseñas 128, correos 254, el token 8192).
- Sin app móvil: no hay rutas `/api/auth/mobile/`.

## Integraciones

### Correo — Resend

Los códigos de verificación, las invitaciones y los documentos salen por la API
HTTP de Resend (`common/mail.py`); las invitaciones de una tanda, en una sola
petición. En producción el despliegue se detiene si falta la llave o el
remitente es el de prueba (`common/checks.py`, corre con `migrate`). Los
registros nunca llevan contraseñas, códigos, tokens ni la llave, y los correos
van enmascarados (`j***@dominio.com`), también en lo que Resend contesta al
rechazar un envío (`common.mail.mask_addresses`).

| Variable | Uso |
|---|---|
| `RESEND_API_KEY` | Llave de la API; sin ella no sale ningún correo |
| `RESEND_FROM` | Remitente de un dominio verificado en Resend; el de prueba (`onboarding@resend.dev`) sólo entrega al dueño de la cuenta |
| `APP_BASE_URL` | Dominio de la aplicación en los enlaces de los correos |
| `REQUIRE_EMAIL_DELIVERY` | Correo obligatorio; encendido por omisión con `VERCEL_ENV=production` |
| `DOCUMENT_EMAIL_MAX_BYTES` | Tope del PDF que viaja adjunto (por omisión `UPLOAD_MAX_BYTES`) |

### Archivos — Cloudflare R2

Logotipos, evidencia de los avances y las texturas y modelos del editor, por
`django-storages` (`core/settings_storages.py`).

| Variable | Uso |
|---|---|
| `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME` | Cuenta, credenciales y bucket; con las cuatro se activa R2 |
| `R2_ENDPOINT_URL`, `R2_PUBLIC_URL` | Endpoint S3 y host público de los objetos |
| `R2_SIGNED_URLS`, `R2_SIGNED_URL_SECONDS` | URLs firmadas que vencen, para un bucket privado |
| `USE_R2` | Fuerza R2 encendido o apagado |
| `PLAN_ASSET_MAX_BYTES` | Tope por textura o modelo del editor (por omisión `UPLOAD_MAX_BYTES`) |

### IA — Anthropic

La foto de un plano en papel se convierte en un plano editable
(`apps/planner/photo_conversion.py`).

| Variable | Uso |
|---|---|
| `ANTHROPIC_API_KEY` | Llave de la API |
| `PHOTO_PLAN_MODEL` | Modelo que lee la foto |
| `PHOTO_PLAN_DAILY_LIMIT` | Conversiones por cuenta al día |
| `PHOTO_PLAN_MAX_BYTES` | Tope de la foto (por omisión `UPLOAD_MAX_BYTES`) |

### reCAPTCHA v3 — Google

Verificación de los formularios públicos en el servidor (`common/recaptcha.py`).
Sin `DEBUG` está encendida siempre, con llave o sin ella; con `DEBUG` sigue a la
llave. **Production no despliega sin reCAPTCHA**: con `VERCEL_ENV=production`,
sin `RECAPTCHA_SECRET_KEY` (`common.E003`) o con `RECAPTCHA_ENABLED` apagado
(`common.E004`) el chequeo de `common/checks.py` detiene `migrate` en el build y
la versión anterior sigue atendiendo.

| Variable | Uso |
|---|---|
| `RECAPTCHA_SECRET_KEY` | Llave secreta v3 del entorno; va junto con `VITE_RECAPTCHA_SITE_KEY` del frontend |
| `RECAPTCHA_ENABLED` | Sin definir: encendida sin `DEBUG`, sigue a la llave con `DEBUG`; apagarla sólo en develop sin llaves (vacía se lee como apagada) |
| `RECAPTCHA_MIN_SCORE` | Puntaje mínimo |
| `RECAPTCHA_HOSTNAMES` | Dominios desde los que se aceptan los tokens: `itzaka.com` sin `DEBUG`, `localhost` con `DEBUG`; develop, `dev.itzaka.com` |

### Base de datos — Neon

PostgreSQL de Neon por entorno. La API usa `DATABASE_URL`, el host con pooler
(PgBouncer en modo transacción): conexiones de una petición
(`CONN_MAX_AGE`, 0 por omisión), revisadas antes de reusarse y sin cursores del
servidor (`core/settings.py`). Las migraciones y la tabla de caché van por el
host directo: `DATABASE_URL_MIGRATIONS` (rol dueño) o, si no está,
`DATABASE_URL_UNPOOLED`; sin ninguna de las dos, el build se detiene.

Aislamiento por empresa (RLS, desde iteracion-26): cada tabla de datos de
trabajo lleva `FORCE ROW LEVEL SECURITY` y deja ver y escribir sólo las filas de
la empresa del contexto (`app.company_id`); sin contexto, ninguna. Cada petición
corre en su transacción (`ATOMIC_REQUESTS`) y fija ahí el contexto
(`common/tenancy.py`): la API en `common.views.TenantContextMixin`, que toda
vista de `apps/` hereda, y el admin en `core.middleware.AdminTenantContextMiddleware`.
El rol de `DATABASE_URL` es el dueño de las tablas y se crea
`NOSUPERUSER NOBYPASSRLS`: con superusuario o `BYPASSRLS` las políticas no lo
detienen. Las tablas aisladas, sus políticas y las que quedan fuera (con su
motivo) están en `common/rls.py`. La caché de los límites va por el alias
`cache`: la misma base, en otra conexión fuera de la transacción de la petición,
para que un intento fallido cuente. Una migración de datos sobre tablas de
trabajo corre sin contexto y no ve filas: fija el de cada empresa
(`set_tenant_context`) antes de tocar las suyas. Las pruebas de RLS (marca
`rls`, `src/tests/security/test_rls.py`) corren en el quality gate de CI con
PostgreSQL; en SQLite se saltan.

## Administración

- Panel en `/admin/` del dominio de la API (Django Unfold); cada modelo de
  `apps/` tiene su registro, y las sesiones emitidas y anuladas (lista negra
  de simplejwt) se consultan ahí, de solo lectura las emitidas. Los códigos de
  verificación también son de solo lectura (para qué, intentos y vigencia),
  sin su huella.
- CSP propia del admin (`ADMIN_CSP`, puesta por `core.middleware.AdminCSPMiddleware`
  justo después de `csp.middleware.CSPMiddleware`): sólo bajo `/admin/` (y, con
  `DEBUG`, en el HTML de la API navegable) Unfold recibe `'unsafe-eval'` en
  `script-src` (Alpine) y `'unsafe-inline'` en `style-src`; scripts en línea,
  nunca. Las imágenes, del propio admin y del bucket (`R2_PUBLIC_URL`, o el
  endpoint S3 con el bucket delante si las direcciones van firmadas): la vista
  previa de logotipos y fotos.
- Lo protegido no se edita en el admin (`common.admin.ProtectedFieldsAdminMixin`):
  el estado de cotizaciones, proyectos, invitaciones y suscripciones y el precio
  de mano de obra de un avance se ven y cambian sólo por su servicio, como los
  folios; la cuenta dueña y los vínculos de un registro (su proyecto,
  cotización, partida, persona o correo invitado) se eligen al crearlo y
  después son de solo lectura.
- Con la RLS (iteracion-26) el admin trabaja como una empresa más: quien entra
  ve y edita lo de su empresa propia. Leer las de todas pide el permiso
  `accounts.view_all_companies` (operador de plataforma; el superusuario lo
  tiene, ser staff no), y aun así sólo lee: guardar o borrar una fila de otra
  empresa lo rechaza la base (página de error). Borrar una cuenta la purga con
  todo lo suyo y sus archivos (`purge_account`), como en la API; una con
  cotizaciones o proyectos la sigue frenando el admin por sus registros
  protegidos.
- El login del admin (`core/admin_login.py`) se cierra 15 minutos tras
  `ADMIN_LOGIN_MAX_FAILURES` intentos fallidos (5 por omisión) desde una
  dirección o para un usuario: 429 con `Retry-After`.
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

- Producción: https://api.itzaka.com (admin en `/admin/`), que la aplicación,
  https://itzaka.com, llama en su subdominio. develop: https://api-dev.itzaka.com
  para https://dev.itzaka.com, con `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`,
  `APP_BASE_URL` y `CSRF_COOKIE_NAME=csrftoken_dev` propios (los valores por
  omisión, sin `DEBUG`, son los de producción; con `DEBUG`, los locales).
- Las variables por entorno (sólo nombres) viven en `tecnico/infraestructura.md`
  de la memoria del proyecto, que es privada.
- Entorno y código de pruebas E2E: Production (`main`) no lleva `APP_ENV` (o
  lleva `production`) y nunca `OTP_UNIVERSAL_CODE` ni `OTP_UNIVERSAL_EMAILS`:
  si llegaran, el build falla. develop (Preview) lleva `APP_ENV=develop` y, para
  la suite E2E, `OTP_UNIVERSAL_CODE` (seis dígitos) y `OTP_UNIVERSAL_EMAILS` con
  los correos exactos de las cuentas E2E (el código sólo verifica esas cuentas).
  Desde iteracion-26 `OTP_UNIVERSAL_CODE_ENABLED` ya no se lee.
- Cada entorno de Vercel (Production y Preview) necesita, además de
  `DATABASE_URL` (pooler), `DATABASE_URL_UNPOOLED` o `DATABASE_URL_MIGRATIONS`:
  el build migra por ahí. Vercel instala desde `uv.lock` (no hay
  `requirements.txt`).
- Cron diario de Vercel (`crons` de `vercel.json`, sólo en Production):
  `GET /api/cron/flush-expired-tokens/` borra las sesiones vencidas. Vercel lo
  llama con `Authorization: Bearer <CRON_SECRET>`; sin `CRON_SECRET` en el
  entorno responde 401 y no corre.
- reCAPTCHA (desde iteracion-26): Production no despliega sin
  `RECAPTCHA_SECRET_KEY` ni con `RECAPTCHA_ENABLED` apagado. Antes de promover,
  una persona crea las llaves v3 del dominio `itzaka.com` y pone juntas
  `RECAPTCHA_SECRET_KEY` en el backend y `VITE_RECAPTCHA_SITE_KEY` en el
  frontend de Production. develop (sin `DEBUG`) también verifica: sus propias
  llaves con `RECAPTCHA_HOSTNAMES=dev.itzaka.com`, o `RECAPTCHA_ENABLED=False`.
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
