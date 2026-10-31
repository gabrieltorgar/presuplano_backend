# Changelog — Itzaka (backend)

Todas las notas de cambios relevantes de la API. El formato sigue
[Keep a Changelog](https://keepachangelog.com/es-ES/) y versionado semántico.

## [Unreleased] — En curso

### Fixed
- **leads/views.py · core/settings.py · README — TEC Detalles de seguridad que quedaron de la iteración 26**: (1) `ContactView` (`POST /api/contact/`) declara `authentication_classes = []`, como acceso y registro: con la cookie de una sesión viva y sin `X-CSRFToken` ya no responde 403 de CSRF, y con una vencida tampoco falla. (2) `DATA_UPLOAD_MAX_MEMORY_SIZE` pasa de 5 MB, más de lo que Vercel deja llegar (~4.5 MB), a `UPLOAD_MAX_BYTES` (4 MiB, y lo sigue si el entorno lo baja). (3) `CSRF_TRUSTED_ORIGINS`: los hosts `*.vercel.app` del despliegue (`VERCEL_URL`, `VERCEL_BRANCH_URL`, `VERCEL_PROJECT_PRODUCTION_URL`) siguen en `ALLOWED_HOSTS`, pero como orígenes de confianza solo en Preview (`VERCEL_ENV=preview`), mientras develop viva en `*.vercel.app`; producción (y un despliegue sin `VERCEL_ENV`) confía solo en los orígenes exactos configurados. (4) El README decía que el rol de `DATABASE_URL` se crea `NOSUPERUSER NOBYPASSRLS`; en Neon es `neondb_owner`, con `BYPASSRLS`, así que en ejecución la RLS no se aplica: ahora lo dice, con el rol de ejecución sin `BYPASSRLS` como pendiente de infraestructura de la persona y el aislamiento que da hoy la aplicación (`TenantContextMixin` y el 404 entre empresas), también en el admin. Sin cambios de código por esto. (SEC-04 · SEC-04.5 · API-02 · iteracion-27 #7)
- **core/admin_login.py · common/throttling.py · accounts/otp_quota.py — TEC Llaves de caché con HMAC SHA-256**: Las tres llaves de caché que se derivaban con `salted_hmac` sin `algorithm` (SHA-1) —el cierre del login del admin por usuario, el límite por cuenta (`IdentifierRateThrottle`) y la cuota de códigos por correo y propósito— pasan `algorithm="sha256"`, como la huella de los códigos: se acaban los avisos `RemovedInDjango2028Warning` (en Django 2028 el valor por omisión cambia a SHA-256). **Al desplegar, los contadores de intentos vigentes se reinician una vez**: las llaves cambian, así que quien estaba en espera por el límite por cuenta, la cuota de códigos o el cierre del login del admin por usuario vuelve a empezar de cero (los límites por dirección y el cierre por IP no cambian). (iteracion-27 #8)
- **accounts/tests/test_otp_codes.py — TEC Pruebas de concurrencia que solo corren en PostgreSQL**: Las dos pruebas de dos verificaciones de un código al mismo tiempo (`TestDosVerificacionesAlMismoTiempoEnPostgreSQL`, iteracion-26 #13) vivían dentro de un `if connection.vendor == "postgresql"` del módulo: en SQLite ni se registraban, y nada decía que no habían corrido. Ahora llevan `POSTGRES_ONLY` (`common/tests/concurrency.py`), el `skipif` con el mismo motivo de las demás pruebas de concurrencia: en SQLite salen como saltadas con «la concurrencia real sólo existe en PostgreSQL: corre en CI con PostgreSQL», y con PostgreSQL corren (comprobado contra PostgreSQL 16: 42 de 42 en el archivo). (iteracion-27 #9)

## [5.0.0] — 2026-10-31 · iteracion-26: el backend vuelve a desplegarse en Vercel con una sola DATABASE_URL, secretos en Infisical, lint en el quality gate y seguridad con itzaka.com y api.itzaka.com: permiso IsVerifiedUser, sesión en cookies del mismo sitio, OTP con HMAC y cuota, throttling por cuenta, reCAPTCHA obligatorio, CSP, subidas validadas y aislamiento por empresa con RLS

### Changed
- **ci — TEC Se retira ci.yml; su lint pasa al quality gate**: `quality-gate.yml` corre `uv run ruff check .` después de `uv sync --locked --all-groups` y antes de las pruebas, sin `|| true`: un error de lint bloquea el merge igual que una prueba en rojo. Era lo único que solo corría `ci.yml`. (SRV-03.2 · iteracion-26 #3)
- **core/settings.py · core/.env.example · README — TEC Secretos del backend en Infisical**: Los valores de las variables viven en Infisical (proyecto itzaka-backend, entornos dev, test, preview y prod): en local se corre con `infisical sm run --env=<entorno> -- <comando>` y Vercel los recibe por la sincronización de Infisical; `src/core/.env.example` sigue siendo la lista de nombres y lo dice en su encabezado, y nombra ahora `ANTHROPIC_API_KEY`. Los settings leían `src/src/core/.env` (BASE_DIR ya es `src/`), así que el `src/core/.env` que pedía el README nunca se cargaba: ahora se lee `src/core/.env` como respaldo local, sin pisar nunca lo que trae el entorno. El README tiene la sección «Secretos (Infisical)»: qué entorno usar para el servidor, `manage.py` y las pruebas, cómo entran agentes y CI y qué hacer si falta un secreto. Pruebas: `common/tests/test_settings_environment.py`. (iteracion-26 #2)

### Removed
- **ci — TEC Se retira ci.yml; su lint pasa al quality gate**: `.github/workflows/ci.yml` (check `test-backend`) se borra: repetía lo que ya corre `quality-gate` (`uv sync`, pytest con cobertura ≥ 90 % sobre PostgreSQL), con acciones sin fijar por SHA, sin `permissions` de nivel superior y sin `persist-credentials: false`. Un pull request a `main` o `develop` queda con sus dos checks, `quality-gate` y `security`, y ya no corre nada en el push a esas ramas, a las que solo se llega por pull request. Lo único que hacía solo `ci.yml`, `uv run ruff check .`, pasa al quality gate (ver Changed). (SRV-03.2 · iteracion-26 #3)

### Fixed
- **vercel.json · core/.env.example · tests/platform · README — TEC El build de Vercel migra con la DATABASE_URL de la app**: Vercel rechazaba todo el vercel.json de la 4.0.0 («buildCommand should NOT be longer than 256 characters»: medía 331) y los despliegues del backend quedaron detenidos. El build vuelve al de antes de la iteracion-25: uv sync --frozen --no-dev, migrate --noinput y createcachetable con la misma DATABASE_URL de la API (142 caracteres). Se retiran DATABASE_URL_UNPOOLED y DATABASE_URL_MIGRATIONS de src/core/.env.example y del README; los ajustes del pooler (CONN_HEALTH_CHECKS, DISABLE_SERVER_SIDE_CURSORS, CONN_MAX_AGE en 0) se quedan. La prueba base test_vercel_json_follows_the_deploy_standard exige un buildCommand de 256 caracteres o menos que no reasigne DATABASE_URL, y test_env_example_names_only_the_app_database_url que .env.example nombre solo DATABASE_URL. (GIT-02, DJ-01 · iteracion-26 #1)

### Security
- **seguridad — TEC Permiso por defecto IsVerifiedUser**: `REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"]` pasa de `IsAuthenticated` a `common.permissions.IsVerifiedUser` (nuevo `src/common/permissions.py`: hereda de `IsAuthenticated` y exige `is_email_verified`; sin sesión sigue siendo 401 y sin verificar es 403 `{"detail": "Verifica tu correo para continuar.", "code": "email_not_verified"}`). Las vistas que declaraban `IsAuthenticated` a secas (31 de 32: catálogo, clientes, cotizaciones, proyectos, avances, evidencias, pagos, personal, planos, modelos, documentos, folios —también el `get_permissions` de `folio-settings/<tipo>/`—, equipo, organización, aceptación legal y `me/email`, `me/password`, `me/delete`) usan `IsVerifiedUser`, antes que `IsCompanyAdmin` donde lo llevan; sólo `GET /api/auth/me/` sigue con `IsAuthenticated` (la SPA lee `is_email_verified` para llevar a la pantalla del código; `PATCH me/` pide verificar). Las rutas públicas (código, reenvío, renovar, salir, CSRF) no cambian. Las cuentas que nacen de una invitación ya nacen verificadas: los colaboradores no quedan fuera. (SEC-02 · iteracion-26 #8)
- **seguridad — TEC Sesión en cookies con la SPA en itzaka.com y la API en api.itzaka.com**: Sin `DEBUG`, los valores por omisión son los de producción: `ALLOWED_HOSTS` = `api.itzaka.com` (más los hosts que Vercel da al despliegue; antes `*`), `CORS_ALLOWED_ORIGINS` y `CSRF_TRUSTED_ORIGINS` = `https://itzaka.com`, `CSRF_COOKIE_DOMAIN` = `.itzaka.com` (la SPA lee la cookie CSRF desde su dominio y la repite en `X-CSRFToken`) y `APP_BASE_URL` = `https://itzaka.com`; con `DEBUG`, los locales (`localhost`, `127.0.0.1`, `[::1]`, `http://localhost:5173`, sin `Domain`). develop los cambia por variables (`dev.itzaka.com`, `api-dev.itzaka.com`, `CSRF_COOKIE_NAME=csrftoken_dev`). Orígenes exactos, `CORS_ALLOW_CREDENTIALS` sigue encendido y las cookies JWT siguen sin `Domain`. El `User-Agent` del correo pasa a `+https://itzaka.com`. `src/core/.env.example` documenta cada variable por entorno. Prueba nueva `test_session_cookie_settings` (producción en un subproceso con `VERCEL=1`: cookies `Secure`, dominio, orígenes y hosts; en proceso: `itzaka_access` e `itzaka_refresh` `Secure`, `HttpOnly`, `Lax` y sin `Domain`, y la CSRF legible con `Domain=.itzaka.com`). (SEC-04, SEC-04.1, SEC-04.4 · iteracion-26 #9)
- **seguridad — TEC Intercambios de credenciales sin autenticar, solo JSON y cuerpos sin tokens**: `REST_FRAMEWORK["DEFAULT_PARSER_CLASSES"]` = `JSONParser`: un cuerpo `application/x-www-form-urlencoded` o multipart en una ruta que no es de subida responde 415 (un `<form>` de otro sitio ya no inicia una sesión ni escribe). Sólo las subidas leen multipart, declarado en la vista y sin `FormParser`: `PATCH /api/auth/organization/` (multipart + JSON), `POST /api/progresses/{id}/evidence/`, `POST /api/plans/photo-conversions/`, `POST /api/plan-assets/` y `POST /api/documents/send/`; corregir un avance (`PATCH /api/progresses/{id}/`) y `POST /api/plan-assets/missing/` leen JSON. Acceso, registro, código, reenvío y recuperación (`login/`, `register/`, `verify-otp/`, `resend-otp/`, `password-reset/`, `password-reset/confirm/`) declaran `authentication_classes = []`: una cookie de acceso de una sesión muerta ya no responde 401, ni una viva sin `X-CSRFToken` 403, y unas credenciales malas siguen siendo 401 con `WWW-Authenticate` (`common.authentication.CredentialExchangeMixin`; sin autenticadores DRF las volvía 403, que la SPA lee como «sin verificar»). `POST /api/auth/refresh/` sólo lee el refresh de su cookie (el del cuerpo se ignora: 401); su cuerpo nunca lleva tokens y un 401 borra las dos cookies. Pruebas nuevas en `apps/accounts/tests/test_credential_exchanges.py`: `test_login_rejects_form_encoded_body`, `test_no_route_reads_urlencoded_and_only_uploads_read_multipart`, `test_login_works_with_a_dead_access_cookie` (y los otros cinco intercambios), `test_refresh_answered_401_clears_both_cookies`, `test_allauth_html_urls_not_mounted` y `test_user_data_does_not_expose_sensitive_fields` (acceso, `me`, organización, equipo, invitaciones, registro, código; ninguna respuesta trae contraseñas, códigos, tokens ni `is_superuser`/`is_staff`). (SEC-04.2, SEC-04.3, SEC-04.5, CRD-02.1, CRD-02.2, MAN-06 · iteracion-26 #10)
- **seguridad — TEC Rotación y lista negra de tokens con limpieza programada**: `SIMPLE_JWT["CHECK_REVOKE_TOKEN"] = True`: cada token lleva la huella de la contraseña con la que nació y deja de servir en cuanto cambia. Cambiar la contraseña (`POST /api/auth/me/password/`) deja fuera al instante a las otras sesiones, también su access (antes vivía hasta vencer, media hora), y a quien la cambió le abre una sesión nueva; recuperarla o ponerla desde el admin también. `POST /api/auth/refresh/` revisa lo mismo (`SessionRefreshSerializer`): un refresh de antes del cambio, o de una cuenta borrada (antes un 500), responde 401 y borra las cookies. Los tokens emitidos antes de este cambio no traen la huella: se rechazan una vez y se vuelve a entrar. Nueva ruta `GET /api/cron/flush-expired-tokens/` (204) que corre `flushexpiredtokens`; la abre sólo `Authorization: Bearer <CRON_SECRET>` comparado en tiempo constante (`common/cron.py`): sin `CRON_SECRET`, sin la cabecera, con otro secreto o con una sesión de usuario responde 401 y no corre. `vercel.json` la programa con `crons` a diario (`0 9 * * *`, UTC); `CRON_SECRET` en `src/core/.env.example`. (CRD-02 · iteracion-26 #11)
- **cuenta — TEC El registro abre una sesión sin verificar**: `POST /api/auth/register/` (201) deja la sesión de la cuenta nueva en las cookies HttpOnly `itzaka_access` e `itzaka_refresh` y la cookie CSRF; el cuerpo sigue siendo sólo la cuenta (`{id, email, is_email_verified}`, sin tokens). Con `IsVerifiedUser` (#8) esa sesión sólo alcanza `GET /api/auth/me/` y las rutas públicas: una ruta de datos responde 403 `code: email_not_verified`. `POST /api/auth/verify-otp/` (200) abre una sesión nueva de la cuenta que verificó: tras registrarse, o tras el 403 `phone_not_verified` del acceso de una cuenta sin verificar, escribir el código es entrar, sin volver a pedir la contraseña. La cuenta nace activa (sin `is_active=False`); el campo trampa sigue respondiendo lo de siempre sin cuenta ni sesión. El límite del registro pasa del alcance `signup` (10 por hora) a `register` (5 por hora y dirección); `signup` se quita. (CRD-01.1 · iteracion-26 #12)
- **cuenta — TEC Códigos OTP con HMAC e intentos bajo bloqueo**: El código de un solo uso se guarda como HMAC-SHA256 con la `SECRET_KEY` (`salted_hmac`, `services.otp_digest`; antes `make_password`), se genera con `secrets.randbelow` y se compara con `constant_time_compare`: una copia de la base sola no revela ningún código vivo. `check_otp` corre en `transaction.atomic` con `select_for_update()` sobre el último código vivo: cada intento fallido suma en la fila (`F("attempts") + 1`) y al llegar a `OTP_MAX_ATTEMPTS` el código muere; dos verificaciones simultáneas del código correcto abren una sola vez. Emitir otro anula los anteriores con `update` (nunca se borran). `verify-otp/`, `password-reset/confirm/` y `me/email/verify/` aceptan en `code` sólo `^[0-9]{6}\Z` (un dígito Unicode u otro largo es un 400 del campo y no cuenta como intento) y responden un código equivocado, vencido, usado o agotado con un `Response` 400 `{"code": ["Código de verificación inválido"]}` en vez de lanzar (antes `["…"]` en los dos primeros y `{"code": "…"}`, que la SPA no mostraba, en el tercero): con `ATOMIC_REQUESTS` (#22) el intento sigue contando. El acceso de una cuenta sin verificar responde su 403 `phone_not_verified` sin lanzarlo, y el código que acaba de salir queda en la base. Los códigos vivos de antes del cambio (guardados con `make_password`) ya no coinciden con ningún HMAC: se pide otro (vencían a los 10 minutos; sin migración de datos). Admin de los códigos de solo lectura: `fields` explícitos sin `code_hash` (tampoco en la lista), sin agregar ni editar, con búsqueda por correo. (CRD-04, CRD-04.1, CRD-04.3 · iteracion-26 #13)
- **cuenta — TEC Espera, tope por hora y respuestas sin enumeración del OTP**: Pedir un código pasa antes por una cuota por destino (el correo normalizado) y propósito, sin buscar la cuenta (`apps/accounts/otp_quota.py` → `check_request_quota`, en la caché compartida): `OTP_RESEND_COOLDOWN_SECONDS` (60) entre envíos y `OTP_MAX_CODES_PER_HOUR` (5) por hora. Pasarse lanza `OTPCooldown`, que `api_exception_handler` responde 429 `{"detail": "Ya te enviamos un código. Intenta de nuevo en N segundos."}` con `Retry-After`, igual para un correo que existe y uno que no. La aplican `POST /api/auth/resend-otp/`, `password-reset/`, `me/email/` (y `PATCH me/`) al correo nuevo, `me/email/resend/` y el acceso de una cuenta sin verificar (que dentro de la espera sigue respondiendo su 403 `phone_not_verified`, sin mandar otro código); el primer código, el del registro, no cuenta (reenviar sirve de inmediato; el siguiente espera). Reenvío y recuperación siguen respondiendo siempre el mismo 200. `POST /api/auth/verify-otp/` con un correo sin cuenta (antes 404 «No existe una cuenta con ese correo.») o ya verificado (antes 400 «El correo ya está verificado») y `POST /api/auth/password-reset/confirm/` con un correo sin cuenta (antes 404) responden el mismo 400 que un código equivocado, `{"code": ["Código de verificación inválido"]}`; la contraseña nueva se valida antes, con o sin cuenta, así que ese 400 tampoco lo distingue. Cambio de correo y de contraseña (CRD-04.5), ya se cumplía y queda protegido: el código va sólo al correo nuevo, la confirmación lo exige, el anterior recibe un aviso sin código, los validadores de Django corren sobre la contraseña nueva al cambiarla y al recuperarla, y las dos cosas dejan fuera a toda sesión anterior (quien la cambió sigue con una nueva; quien la recupera entra con la nueva). Variables nuevas en `src/core/.env.example`. (CRD-04.2, CRD-04.5 · iteracion-26 #14)
- **cuenta — TEC OTP universal solo en local y develop**: `OTP_UNIVERSAL_CODE` ya no tiene valor por omisión (era «123456») y sólo puede existir con `APP_ENV` en `local` o `develop`. `APP_ENV` es nuevo (`local`, `develop` o `production`; sin la variable, `production`), y un despliegue con `VERCEL_ENV=production` es producción diga lo que diga `APP_ENV`: con el código en cualquier otro entorno los settings lanzan `ImproperlyConfigured`, y el build (`migrate`) y cada proceso fallan. El código sirve sólo para las cuentas de `OTP_UNIVERSAL_EMAILS` (nueva: correos exactos separados por comas, sin distinguir mayúsculas) y sólo para verificar la cuenta (`POST /api/auth/verify-otp/`): nunca para recuperar la contraseña ni para cambiar el correo (`accounts.services.universal_code_accepted`); cada uso deja un aviso en el log con la cuenta, sin el código. Antes abría cualquier cuenta y cualquier propósito mientras el correo no estuviera configurado, donde `OTP_UNIVERSAL_CODE_ENABLED` (encendido con `DEBUG`) lo permitía; esa variable se quita. Sin correo configurado ya se emite el código propio (el envío anota que no salió). `src/core/.env.example`: `APP_ENV=local`, `OTP_UNIVERSAL_CODE` y `OTP_UNIVERSAL_EMAILS` vacíos. Antes de desplegar: Production sin `OTP_UNIVERSAL_CODE`, `OTP_UNIVERSAL_EMAILS` ni `OTP_UNIVERSAL_CODE_ENABLED` (con el código, el build falla); develop (Preview) con `APP_ENV=develop` y, para la suite E2E, el código y la lista de sus cuentas. Un `src/core/.env` local que traiga `OTP_UNIVERSAL_CODE` necesita `APP_ENV=local`. (CRD-04.4 · iteracion-26 #15)
- **seguridad — TEC Throttling por cuenta, tasas de auth y login del admin con límite**: `common.throttling.IdentifierRateThrottle` entra en `DEFAULT_THROTTLE_CLASSES`: las vistas que declaran `identifier_throttle_scope` cuentan además por el correo enviado (normalizado y como HMAC; también el campo `identifier`, o el correo de la sesión), así que rotar la dirección no reinicia el límite de una cuenta. `DEFAULT_THROTTLE_RATES` con las tasas de django-backend-conventions: `login` 10/min, `register` 5/h, `otp_request` 3/min, `otp_verify` 10/min, `password_reset` 5/h, `password_change` 5/h, `contact` 5/h, `costly` 20/h (`THROTTLE_COSTLY`), `bulk` 30/min, `upload` 30/h, `dj_rest_auth` 10/min, `login_email` 20/h, `otp_email` 10/h y `password_reset_email` 3/h, más `invitation` 30/min (el enlace público de una invitación); se quitan `otp` (5/min, que compartían pedir y verificar), `documents` e `invitations` (30/h). Alcances: `login/` `login` + `login_email`; `verify-otp/`, `password-reset/confirm/` y `me/email/verify/` `otp_verify` + `otp_email`; `resend-otp/`, `me/email/` (y `PATCH me/`, que también pide el correo nuevo; `GET me/` no) y `me/email/resend/` `otp_request`; `password-reset/` `password_reset` + `password_reset_email`; `me/password/` y `me/delete/` `password_change`; `POST /api/documents/send/`, `POST /api/collaborators/invitations/`, `…/invitations/{id}/resend/` y `POST /api/plans/photo-conversions/` `costly` (un bote por cuenta: antes 30/h para documentos y 30/h para invitaciones, y las fotos sin alcance). El registro se queda en 5 por hora y dirección: los colaboradores entran por su invitación (alcance `login`), no por el registro. `CACHES["default"]["OPTIONS"]` = `{"MAX_ENTRIES": 20000, "CULL_FREQUENCY": 10}`: con las 300 de Django la tabla borraba contadores de throttle vivos. El login del admin (`core/admin_login.py`, montado en `admin/login/` antes de `admin.site.urls`) responde 429 con `Retry-After: 900` durante 15 minutos tras `ADMIN_LOGIN_MAX_FAILURES` (5) intentos fallidos desde una dirección o para un usuario. `THROTTLE_COSTLY` y `ADMIN_LOGIN_MAX_FAILURES` en `src/core/.env.example`. (BOT-03, BOT-03.1, BOT-03.2, BOT-03.4 · iteracion-26 #16)
- **seguridad — TEC reCAPTCHA obligatorio en producción y cargador que se recupera**: Sin `DEBUG`, `RECAPTCHA_ENABLED` está encendido por omisión, con llave o sin ella (antes seguía a `RECAPTCHA_SECRET_KEY`: sin llaves los cinco formularios públicos sólo tenían el campo trampa); con `DEBUG` sigue a la llave. `RECAPTCHA_HOSTNAMES` por omisión es `itzaka.com` sin `DEBUG` y `localhost` con `DEBUG` (antes `itzaka.grupotorresmucino.com,localhost` en todos lados); develop pone `dev.itzaka.com`. Nuevo chequeo `common.checks.recaptcha_in_production` (tag `security`, corre con `migrate` en el build): con `VERCEL_ENV=production`, sin `RECAPTCHA_SECRET_KEY` es `common.E003` y con `RECAPTCHA_ENABLED` apagado `common.E004`, y **Production no despliega**: antes de promover, una persona crea las llaves v3 y pone juntas `RECAPTCHA_SECRET_KEY` (backend) y `VITE_RECAPTCHA_SITE_KEY` (frontend) en Production. Formularios públicos (MAN-04): un cuerpo que no es un objeto JSON (arreglo, texto, número, `null`) responde 400 `non_field_errors` en registro, acceso, recuperación, contacto e invitación (antes 500); un correo que no es texto con el campo trampa ya no es un 500 (`normalize_email` sólo limpia texto); las contraseñas de registro, acceso, `password-reset/confirm/` y aceptar una invitación tienen tope de 128 caracteres y el correo del registro de 254 (400 del campo); un token de más de 8192 caracteres o que no es texto no se le manda a Google (400). El señuelo de la invitación responde lo mismo que la vía real cuando el enlace no sirve: 404 si no existe (antes 201), 409 si ya se usó y 410 si se canceló o venció. Sin Google, aceptar una invitación responde 503 (con prueba nueva); el contacto se sigue guardando bajo `contact` (5/h) con `needs_review`. Decisión registrada en el código y el README: el acceso con el campo trampa responde el mismo 401 de unas credenciales malas (un 2xx sin la sesión dejaría a la SPA creyendo que entró). Pruebas nuevas en `common/tests/test_public_forms.py` y `common/tests/test_recaptcha.py`; `src/core/.env.example` documenta `RECAPTCHA_ENABLED` (comentada: vacía se lee como apagada). (BOT-01, MAN-04 · iteracion-26 #17)
- **seguridad — TEC CSP aplicada en la API y el admin**: La API responde con la Content-Security-Policy aplicada `default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'` (antes `default-src 'self'` con `script-src`, `style-src`, `img-src 'self' data: https:` y demás, pensada para páginas). El admin tiene la suya, `ADMIN_CSP` (`core/settings_csp.py`): `default-src 'self'`, `script-src 'self' 'unsafe-eval'` (Alpine de Unfold), `style-src 'self' 'unsafe-inline'`, `img-src 'self' data:` más el origen del bucket (`R2_PUBLIC_URL`, o el endpoint S3 con el bucket delante si `R2_SIGNED_URLS`; antes cualquier `https:`), `font-src 'self' data:`, `connect-src 'self'`, `object-src 'none'`, `base-uri 'self'`, `frame-ancestors 'none'` y `form-action 'self'`. La pone `core.middleware.AdminCSPMiddleware` bajo `/admin/` y, con `DEBUG`, en el HTML de la API navegable; va justo después de `csp.middleware.CSPMiddleware` (django-csp 4, el ya instalado), que reemplaza a `common.csp.ScopedCSPMiddleware` (se borra `src/common/csp.py`). `SECURE_CONTENT_TYPE_NOSNIFF = True` y `X_FRAME_OPTIONS = "DENY"` se declaran siempre (antes sólo fuera de `DEBUG`) y `SECURE_REFERRER_POLICY` sigue en `same-origin`, más estricta que `strict-origin-when-cross-origin`: ni el origen de la API ni el del admin salen hacia otro sitio. Pruebas nuevas en `src/core/tests/test_csp.py` (la API con `default-src 'none'` también en un 404, el login de Unfold carga con su política y sin scripts en línea, la API navegable con `DEBUG`, el orden del middleware, el bucket en `img-src`). (SRV-01 · iteracion-26 #18)
- **seguridad — TEC Subidas validadas por contenido con tope de 4 MB**: Nuevo `UPLOAD_MAX_BYTES` (4 MiB, del entorno): lo más que pesa un archivo que viaja por la API, porque una función de Vercel corta en 4.5 MB el cuerpo entero antes de Django (respondía 413 sin CORS y la SPA mostraba «Sin conexión»). Los topes de cada subida quedan bajo él: la evidencia de un avance pasa de 5 MB a `UPLOAD_MAX_BYTES`, `PLAN_ASSET_MAX_BYTES` (texturas y modelos del editor) de 10 MB y `DOCUMENT_EMAIL_MAX_BYTES` (el PDF que se envía por correo) de 8 MB a `UPLOAD_MAX_BYTES` por omisión, y `PHOTO_PLAN_MAX_BYTES` también lo toma; el logotipo sigue en 2 MB. Lo que pasaba de 4.5 MB ya no llegaba en Vercel: ahora el 400 dice el tope. Nuevo chequeo `core.checks.uploads_fit_vercel` (tag `security`, registrado desde `AccountsConfig.ready()`, corre con `migrate`): con `VERCEL` y cualquiera de esos cuatro topes por encima de 4 MiB es `core.E002` y el despliegue se detiene. `common.validators.validate_upload` pasa toda imagen por Pillow `verify()` y vuelve a abrirla para contar sus píxeles (antes sólo leía el tamaño y sólo si la subida traía tope de píxeles): una imagen con la firma bien y los datos rotos responde 400 «Imagen corrupta o demasiado grande.» (antes 500 o se guardaba), también en las texturas; el exceso de píxeles se revisa fuera del `try` y dice «La imagen excede las dimensiones máximas.». La foto de un plano (`POST /api/plans/photo-conversions/`) pasa por `validate_upload` (PNG, JPG o WEBP, 50 MP) antes de llegar a Claude. El nombre guardado sigue saliendo del tipo detectado (uuid y extensión), nunca del cliente; la extensión que trae el cliente no se exige (las bibliotecas de Sweet Home 3D traen archivos sin ella). `UPLOAD_MAX_BYTES` en `src/core/.env.example`. Pruebas nuevas en `src/common/tests/test_upload_limits.py`. Archivos de más de 4 MiB por una subida firmada al bucket: pendiente. (API-02 · iteracion-26 #19)
- **seguridad — TEC Campos protegidos de solo lectura, importes del servidor y máquinas de estado**: Nuevo `src/common/state_machine.py` (`Transitions` con `check` y `ensure_editable`, `REGISTRY`, `register`): la cotización (`draft → in_project`, final `in_project`), el proyecto (`in_progress → finished`, final `finished`) y la invitación (`pending → accepted | cancelled`, finales las dos) registran su tabla en su servicio (`QUOTE_TRANSITIONS`, `PROJECT_TRANSITIONS`, `INVITATION_TRANSITIONS`); la suscripción, que nace activa y nada la cambia todavía, queda exenta en la línea base de plataforma (#29). Cada cambio de estado y cada escritura bajo una fila con estado se revisa sobre la fila releída con `select_for_update(of=("self",))` en su transacción: `start_project` es atómica de punta a punta con la cotización bloqueada (un segundo clic, un reintento o la petición que esperó el bloqueo responden 400 «Esta cotización ya tiene un proyecto asociado»; una carrera que se saltara el bloqueo choca con el `OneToOneField` y es 409) y ya no convierte una cotización que está `in_project`; editar, volver a cotizar desde el plano y borrar una cotización (también una `in_project` sin proyecto: 400), finalizar un proyecto (`finalize_project`, ahora atómica), registrar, corregir o borrar avances, subir o quitar fotos (`add_evidence`, ahora atómica), registrar pagos y repartir partidas (`assign_service`, ahora atómica) bloquean su cotización o su proyecto: uno que se cerró mientras tanto ya no cambia, y dos avances o dos repartos a la vez no superan la partida. Cancelar una invitación es atómica y bloqueada como aceptarla (`find_invitation` bloquea sólo la invitación, `of=("self",)`); reenviarla guarda el enlace nuevo en la fila releída y bloqueada (si mientras salía el correo la aceptaron o la cancelaron, 400 y su enlace se queda); desistir del cambio de correo (`DELETE /api/auth/me/email/`) se aplica a la cuenta bloqueada y releída. `PUT`/`PATCH /api/assignments/{id}/` conserva el proyecto, la partida y la persona del reparto aunque el cuerpo mande otros (antes el cuerpo los cambiaba). `status` de solo lectura también en las formas de lectura (`QuoteSerializer`, `ProjectSerializer` y `ProjectListSerializer`, con `quote`; `ProgressSerializer` con `labor_unit_price`; `SubscriptionSerializer` los nombra uno por uno). En el admin, nuevo `common.admin.ProtectedFieldsAdminMixin`: el estado de cotizaciones, proyectos, invitaciones y suscripciones y el precio de mano de obra de un avance se ven y no se editan; la cuenta dueña (`owner`, `account`, `user`) y los vínculos de proyecto, cotización, partida, persona y correo invitado se eligen al crear y después son de solo lectura (cotizaciones, proyectos, avances, pagos, pagos al personal, repartos, personal, servicios, clientes, planos, archivos y modelos del editor, organización, colaboradores e invitaciones). Ninguna ruta cambia ni se agrega: la SPA no escribía ningún estado. Pruebas nuevas: `test_a_total_sent_by_the_client_is_ignored` (POST y PATCH con total y subtotales falsos, control en `notes`) y `test_a_progress_ignores_earned_value_and_labor_price` (VAL-05), `src/common/tests/test_state_machine.py`, `src/common/tests/test_admin_protected_fields.py` y `test_*_states.py` en cotizaciones, proyectos, pagos, personal y equipo; las de concurrencia real (`test_concurrent_conversion_creates_one_project`, dos avances, finalizar y avanzar, dos repartos y dos cancelaciones a la vez) corren sólo con PostgreSQL (`src/common/tests/concurrency.py`). (SEC-03, SEC-03.1, SEC-03.2, SEC-03.3, VAL-05 · iteracion-26 #20)
- **seguridad — TEC Sin secretos en los logs**: El aviso de un envío que Resend rechaza (`common/mail.py`) enmascara cada correo que trae lo que Resend contesta (hasta 500 bytes, que podían repetir las direcciones de los destinatarios: `common.mail.mask_addresses`, `j***@dominio.com`) y lee el estado HTTP de `error.status` (antes `error.code`, que el escáner tomaba por un código de un solo uso); el destinatario ya iba enmascarado (o, en una tanda, sólo cuántos). Revisado el resto: ningún log ni campo `extra` de `src/` lleva contraseñas, códigos, tokens, la llave de Resend ni un correo completo, y ningún `transaction.on_commit` recibe un `functools.partial`. Pruebas nuevas con `caplog` en `src/common/tests/test_logs_without_secrets.py`: un rechazo suelto y uno de una tanda no escriben ninguna dirección, y registrarse, verificar, recuperar la contraseña y entrar no dejan en ningún registro (mensaje ni `extra`) el correo, las contraseñas, los dos códigos ni las cookies de la sesión. (CRD-01 · iteracion-26 #21)
- **seguridad — TEC Aislamiento por empresa con RLS en PostgreSQL**: Las 20 tablas de datos de trabajo (tarifas, clientes, cotizaciones con sus partidas y su desglose por habitación, proyectos con sus avances y evidencias, pagos, personal con sus servicios, repartos y pagos, planos y fotos convertidas, archivos y modelos del editor, folios) llevan `ENABLE` + `FORCE ROW LEVEL SECURITY` —el rol dueño de las tablas, el de `DATABASE_URL`, también queda sujeto— con dos políticas (migraciones `*_aislamiento_por_empresa` de nueve apps, `common.rls.IsolateCompanies`, sólo en PostgreSQL: en SQLite no hacen nada): `tenant_isolation`, leer y escribir sólo filas cuyo `owner_id` —el de su padre en las hijas, comparado de forma explícita— es `app.company_id` (sin contexto, ninguna), y `platform_operator_read`, sólo `SELECT` con `app.platform_operator`. Quedan fuera, con su motivo en `common.rls.SHARED_TABLES`: cuentas, suscripciones, membretes (`companies_of` lee el nombre de cada empresa donde se colabora), códigos, colaboradores e invitaciones (`account_of` y el enlace público las leen sin contexto), constancias legales y contactos públicos. Cada petición corre en su transacción (`ATOMIC_REQUESTS = True`) y fija ahí el contexto con `SET LOCAL` (`common/tenancy.py::set_tenant_context`, que falla fuera de una transacción): en la API, `common.views.TenantContextMixin` tras autenticar, con la empresa de `account_of` (`X-Empresa`; sin acceso a la pedida, contexto vacío y el 403 de siempre) —las 48 vistas de `apps/` heredan de `TenantAPIView` o un `Tenant*ViewSet`; la API nunca lee entre empresas—; en el admin, `core.middleware.AdminTenantContextMiddleware` (después de `AuthenticationMiddleware`): la empresa propia de quien entra y, sólo para leer las de todas, el permiso nuevo `accounts.view_all_companies` (migración `accounts.0014`; ser staff no lo da, el superusuario sí). La caché de los límites escribe por su propio alias, `DATABASES["cache"]` (la misma `DATABASE_URL`, `ATOMIC_REQUESTS` apagado, `core.routers.CacheRouter`): con la transacción por petición, un 401 o un 400 revertía su propio intento y el límite nunca llegaba; `createcachetable` del build, en el alias `default`, sigue creando la tabla. Eliminar la cuenta (`purge_account`) purga con el contexto de la propia cuenta aunque se pida trabajando en otra empresa, y borrar una cuenta en el admin (una o en lote) ahora la purga igual, archivos incluidos. Revisión de `ATOMIC_REQUESTS` en todas las apps: nada más escribía algo que debiera quedar y luego lanzaba (los códigos de #13 y el 403 de #20 ya respondían sin lanzar). Pruebas nuevas: `src/common/tests/test_tenancy.py` (`test_set_tenant_context_outside_atomic_raises`, la empresa de cada petición, `test_every_api_view_of_apps_sets_the_tenant_context`), `test_rls_tables.py` (cada tabla aislada o compartida con su motivo, toda tabla con `owner` aislada, el SQL de cada migración y que en SQLite no hace nada), `test_atomic_requests.py` (con la caché de base de datos: diez contraseñas equivocadas y la siguiente es 429; cinco contraseñas actuales equivocadas, igual), `test_database_settings.py` (`test_db_cache_writes_outside_atomic_requests`), `src/core/tests/test_admin_tenancy.py`, `apps/accounts/tests/test_delete_account.py::TestEliminarConLaRLS`, `src/tests/security/test_rls.py` (marca `rls`, registrada en `src/tests/security/conftest.py`; PostgreSQL de CI con el rol `app_rls` `NOSUPERUSER NOBYPASSRLS` y `SET LOCAL ROLE`: `test_rls_role_cannot_bypass`, `FORCE` y políticas en las 20 tablas, sin contexto 0 filas, A no ve ni escribe lo de B, el operador sólo lee, la API, el admin, la purga y el cron; en SQLite se saltan con su motivo) y `src/tests/security/test_scope_registry.py` con `SCOPED_DETAIL_ROUTES` (41 rutas de detalle, pedidas por un usuario y por un staff de otra empresa: 404 y nada cambia). (SEC-01, SEC-01.1, BOT-03.3, MAN-03 · iteracion-26 #22)
- **.gitleaksignore — TEC Exención registrada de la contraseña de prueba en .gitleaksignore**: La única huella ignorada (`src/common/tests/test_recaptcha.py`, regla `generic-api-key`, del commit `6e7cc23` de iteracion-12) lleva justo arriba su exención `# no es un secreto: …` con el archivo, la iteración y el motivo: es una contraseña inventada para una prueba de reCAPTCHA, no una credencial, así que no hay nada que rotar y no se afirma ninguna rotación. Archivo de gate, aprobado por la persona en el chat (2026-10-31). (CRD-03.1 · iteracion-26 #28)
- **tests/platform/ — TEC Pruebas base de seguridad, auth, rutas y dominio**: Las pruebas base afirman lo que deja esta iteración y lo protegen. `test_security_baseline.py`: `IsVerifiedUser` por omisión, solo `JSONParser`, `IdentifierRateThrottle` y las 15 tasas de security.md §6 en `test_drf_defaults_are_secure` (antes `IsAuthenticated` y la tasa `otp`, que ya no existe); `RECAPTCHA_ENABLED` encendido en producción sin llave; `test_spa_and_api_are_same_site` (con los ajustes de la suite y en un despliegue de Vercel sin variables: `CSRF_COOKIE_DOMAIN` `.itzaka.com`, `CORS_ALLOWED_ORIGINS` `https://itzaka.com`, `ALLOWED_HOSTS` `api.itzaka.com`, y ningún origen con comodín, en `*.vercel.app` u otro sufijo público ni fuera del dominio de la cookie); `test_installed_versions_meet_floors` (las versiones instaladas sobre los pisos de libraries.md; django ≥ 6.1.2 y < 6.2 por decisión de la persona); `test_security_middlewares_installed` y `test_csp_is_scoped_to_admin`; sin `functools.partial` en `transaction.on_commit`; la caché de base de datos fuera de `ATOMIC_REQUESTS` y cada petición en una transacción. `test_auth_baseline.py`: `CHECK_REVOKE_TOKEN`. `test_routes_baseline.py` (y `routes.py` con `identifier_scope`): tasa también para cada alcance por cuenta, el alcance propio de cada ruta de auth y ninguna con `otp` ni `dj_rest_auth` (`test_auth_routes_use_their_scope`), `costly` en lo que manda correo o genera documentos, `test_public_endpoints_declare_a_scope` (antes `test_public_routes_declare_a_scope`), `test_views_require_a_verified_user` (`IsAuthenticated` a secas solo en `VERIFICATION_EXEMPT`, hoy `me`; la ruta del cron con `IsCronJob`), toda vista de `apps/` con `TenantContextMixin` y cada ruta de detalle en `tests/security/scope_registry.py`. `test_domain_baseline.py`: sin excepciones en `WRITABLE_PROTECTED` (eran tres formas de lectura con `status`); el admin no edita campos protegidos al crear ni al editar (salvo `is_staff` e `is_superuser` del usuario y la cuenta dueña al crear, con su motivo); cada tabla de estados con sus finales sin salida y cada modelo con estado con su tabla (`Subscription` exenta, con su motivo). Archivo de gate, aprobado por la persona en el chat (2026-10-31). (SEC-02, SEC-02.2, SEC-03, SEC-03.1, SEC-04.4, BOT-03.1, BOT-03.2, SRV-01, SRV-03.6 · iteracion-26 #29)

---

## [4.0.0] — 2026-10-30 · iteracion-25: PDF de cotización con desglose por habitación, folios de documentos configurables por organización, la API responde 409 o 400 con su motivo en vez de un 500, base de datos lista para el pooler de Neon y quality gate, security y pruebas base al día con git-deploy-ops

### Added
- **cotizaciones — US-12 PDF de cotización con desglose por habitación**: Cada partida que mide el plano guarda cuánto de ella cae en cada habitación: las partidas traen `rooms` = `[{name, quantity}]` (modelo nuevo `QuoteItemRoom`, con su admin; migración `quotes 0008_desglose_por_habitacion`, sólo crea la tabla). Crear y editar (`/api/quotes/`) y `POST /api/quotes/{id}/plan-sync/` lo aceptan opcional en cada partida: hasta 100 habitaciones, nombre de hasta 150 caracteres, cada una una sola vez y sin pasar de la cantidad de la partida (lo que sobra no cae en ninguna habitación). Recotizar el plano reemplaza el reparto de sus partidas. Editar la cotización a mano sin `rooms` conserva el reparto de una partida del plano mientras su cantidad lo alcance; si la cantidad baja, la partida se queda sin habitación. El resumen global no cambia: la partida, su cantidad, su subtotal y el total son los mismos; la lista, el detalle y las escrituras traen las habitaciones con sus partidas sin una consulta por cada una. (US-12, US-95 · iteracion-25 #1)
- **folios — US-142 Folios de documentos configurables por organización**: Nueva app `apps.folios`: el folio de cada documento lo asigna el servidor al crearlo (`assign_folio`, dentro de la transacción del documento) y queda guardado. Por empresa y tipo de documento (cotización, estado del proyecto, comprobante de pago y de pago a personal) hay dos modalidades: «Autogenerado» (`COT-` y 8 caracteres aleatorios, la forma de siempre; se vuelve a sortear si repite) y «Con clave» (de 1 a 5 letras o números en mayúsculas, validada en el servidor, y un consecutivo: `VEN-101`). El contador es por empresa y clave (`FolioCounter`, bloqueado con `select_for_update`), nunca se reinicia y lo comparten los tipos que usan la misma clave; `IssuedFolio` registra cada folio emitido con una restricción única por empresa, también entre tipos. Endpoints `GET /api/folio-settings/` (un objeto por tipo con su modalidad, su clave y el siguiente folio), `GET/PUT /api/folio-settings/<tipo>/` (cambiarlo es del administrador, US-140) y `GET /api/folio-settings/<tipo>/preview/?mode=&prefix=` (el siguiente folio de una clave sin guardarla). Admin de Unfold de solo lectura para contadores y folios emitidos. (iteracion-25 #2)
- **tests/platform/ — TEC Pruebas base de plataforma**: Pruebas base nuevas (TDD-B01): `routes.py` recorre el URLconf; `test_routes_baseline.py` exige sesión en toda ruta salvo la lista blanca pública de 15 rutas con su motivo (una ruta nueva con `AllowAny` queda en rojo), un límite propio en las públicas o su motivo, una tasa para cada `throttle_scope` y 401 sin sesión en cada método de cada ruta privada; `test_auth_baseline.py` (lista negra y rotación de simplejwt, cookies HttpOnly/Lax/Secure, CSRF en las escrituras con la cookie, códigos OTP cifrados, sin rutas móviles); `test_domain_baseline.py` (campos protegidos de solo lectura en los serializers; tres formas de lectura con su motivo); `test_api_contract_baseline.py` (`test_default_pagination_contract`, movida de `test_list_contract.py`; `test_a_list_without_page_is_paginated_too`; `test_every_list_route_paginates`; `test_every_list_route_declares_filters_search_and_ordering`; `test_list_contract_pending_is_dated_and_current` con `LIST_CONTRACT_PENDING` vacío, y el contrato de `api_exception_handler`: 400 con el dict de campos, 409 que dice qué usa el registro, 429 con `Retry-After`). (TDD-B01 · iteracion-25 #10)

### Changed
- **quotes · projects · payments · staff — US-142 Cada documento guarda su folio**: `Quote`, `Project`, `Payment` y `WorkerPayment` tienen `folio` (no editable, único por empresa con `UniqueConstraint(owner, folio)`), que viaja en sus respuestas y no cambia por edición. Las migraciones `quotes 0007_quote_folio`, `projects 0005_project_folio`, `payments 0003_payment_folio` y `staff 0003_workerpayment_folio` guardan en los documentos que ya existían el folio que sus PDFs imprimían (la clave y los primeros 8 caracteres del id, como lo derivaba el navegador) y lo apartan en el registro de la empresa: lo emitido no cambia. Las cotizaciones se buscan también por folio (`?search=`), y un documento creado desde el admin toma su folio como en la API. (iteracion-25 #2)
- **core/settings.py · accounts/admin.py — TEC Base de datos lista para el pooler de Neon, admin completo y pruebas sin exclusiones**: `DATABASES["default"]` lleva `CONN_HEALTH_CHECKS = True`, `DISABLE_SERVER_SIDE_CURSORS = True` y `CONN_MAX_AGE` del entorno (0 por omisión): con el pooler de Neon (PgBouncer en modo transacción) una conexión muerta tras el reposo ya no llega a una petición y un `.iterator()` no se rompe entre transacciones. `src/core/.env.example` nombra `CONN_MAX_AGE`, `DATABASE_URL_UNPOOLED` y `DATABASE_URL_MIGRATIONS`. `OutstandingToken` y `BlacklistedToken` (lista negra de simplejwt) se vuelven a registrar con un `ModelAdmin` de Unfold que conserva el de simplejwt (las sesiones emitidas siguen de solo lectura). Sin `pragma: no cover` en el código: `common/authentication.py` pasa a `CSRFCheck` una lambda y `manage.py` ya estaba en `omit`. El fixture autouse de la caché de pruebas se llama `_isolated_cache`. (DJ-01, PLT-B02, QA-01 · iteracion-25 #7)
- **.github/ · scripts/ · vercel.json — TEC Quality gate, security, Dependabot y despliegue al día con git-deploy-ops**: `quality-gate.yml` instala con `uv sync --locked --all-groups` (un `uv.lock` desfasado ya no pasa), corre con `DEBUG: "True"` y `SECRET_KEY` de CI, limpia `reports/`, llama a `test_gate.py` con `--allow-skip-reason` y agrega el paso «README sincronizado» (`readme_sync.py --check --kind backend`, sin `--require-routes` mientras falte el comando `api_routes`). `security.yml` con gitleaks fijado por digest (subcomando `git`) y la autoprueba del auditor. Ambos con acciones fijadas por SHA, `permissions: contents: read` y `persist-credentials: false`. `dependabot.yml` (uv y github-actions) espera 7 días tras cada publicación. `scripts/test_gate.py` (bloquea skips y xfail sin motivo), `security_audit.py` (falla cerrado), `gate_guard.py` y `readme_sync.py` copiados de git-deploy-ops, fuera de ruff. `vercel.json`: `migrate` y `createcachetable` por `DATABASE_URL_MIGRATIONS` o `DATABASE_URL_UNPOOLED` (el build falla sin ninguna) y `scripts/**` fuera de la función. Pruebas base: `test_production_settings_values` (producción en un subproceso), `test_vercel_json_follows_the_deploy_standard` y `test_dependency_manifest_is_uv_only`. (GIT-01, GIT-02, GIT-04, GIT-05, GIT-08, TDD-B03, ARQ-B01, SRV-03.1, SRV-03.2, SRV-03.3, SRV-03.4 · iteracion-25 #8)
- **tests/platform/test_vercel_bundle.py — TEC Pruebas portables en Windows**: `test_the_legal_documents_ship_with_the_function` compara la ruta de cada documento legal con `as_posix()`, como la lee Vercel: en Windows `str()` daba `src\apps\legal\...` y el patrón `*.md` (que no cruza `/`) la marcaba como excluida. Sigue fallando si `excludeFiles` vuelve a dejar fuera los documentos (`**/*.md`). (iteracion-25 #9)

### Fixed
- **common/exceptions.py — TEC La API responde 409 o 400 con su motivo en vez de un 500**: El manejador de errores pasa a `common.exceptions.api_exception_handler` (registrado en `REST_FRAMEWORK["EXCEPTION_HANDLER"]`). El `ValidationError` de Django es un 400 con el dict de campos (un mensaje suelto va a `non_field_errors`): un id que no es UUID en `GET /api/payments/summary/`, `/api/payments/voucher/` (`?project=`) o `/api/worker-payments/summary/` (`?worker=`) respondía 500. Borrar algo en uso (`ProtectedError`/`RestrictedError`, p. ej. `DELETE /api/workers/{id}/` de alguien con repartos, pagos o avances) es un 409 que dice qué lo usa («No se puede eliminar porque tiene registros relacionados: pagos a personal.»); antes recibía el mensaje de dos peticiones simultáneas, que pedía reintentar. El resto de `IntegrityError` sigue en 409 con su mensaje y `code: conflict`, y el 429 conserva su texto. (ERR-B01 · iteracion-25 #3)

### Removed
- **requirements.txt — TEC Quality gate, security, Dependabot y despliegue al día con git-deploy-ops**: `requirements.txt` se borra: `pyproject.toml` + `uv.lock` son la única fuente de dependencias (Vercel instala de `uv.lock` y `security_audit.py` falla cerrado si hay un `requirements*.txt` junto a `pyproject.toml`). `test_requirements_txt_is_the_lockfile_exported` se reemplaza por `test_dependency_manifest_is_uv_only`. (ARQ-B01 · iteracion-25 #8)

---

## [3.13.0] — 2026-10-30 · iteracion-24: cumplimiento de seguridad: la cookie CSRF para la SPA y cuerpos de auth sin tokens

### Fixed
- **seguridad — TEC La API entrega la cookie CSRF a la SPA, con la cookie y los orígenes desde el entorno**: Nuevo `GET /api/auth/csrf/` (204, público y sin autenticación): deja la cookie CSRF antes del primer POST de un navegador nuevo; antes respondía 404 y el token llegaba solo con el login o con /me/. `CSRF_COOKIE_NAME` (por omisión `csrftoken`) y `CSRF_COOKIE_DOMAIN` (por omisión ninguno: la SPA llama a /api por su propio dominio) se leen del entorno; `CSRF_TRUSTED_ORIGINS` y `CORS_ALLOWED_ORIGINS` también, con orígenes exactos. `Retry-After` queda expuesto por CORS para que la SPA muestre la espera de un 429. `src/core/.env.example` lista las cuatro variables. (SEC-04.3, SEC-04, SEC-04.6 · iteracion-24 #1)
- **seguridad — TEC Prueba base: las respuestas de auth web nunca llevan tokens**: `test_web_auth_responses_carry_no_tokens` revisa todas las respuestas que abren o renuevan la sesión web: entrar, renovar, cambiar la contraseña y aceptar una invitación. Exige que la sesión llegue solo en las cookies HttpOnly y que el cuerpo no traiga `access` ni `refresh` en ningún nivel, ni el valor de alguna de las cookies. El comportamiento ya era ese; la prueba lo deja protegido. (CRD-02.1 · iteracion-24 #2)

---

## [3.11.0] — 2026-10-30 · iteracion-21: dominio propio itzaka.grupotorresmucino.com

### Changed
- **plataforma — TEC Dominio propio: itzaka.grupotorresmucino.com**: La API de producción pasa a `https://api-itzaka.grupotorresmucino.com` y la aplicación a `https://itzaka.grupotorresmucino.com`, que la llama por su propio dominio (`/api`). Cambian los valores por omisión de `APP_BASE_URL` (los enlaces de los correos) y `RECAPTCHA_HOSTNAMES` (`itzaka.grupotorresmucino.com,localhost`), `src/core/.env.example` y el `User-Agent` con el que el backend se presenta a Resend.

---

## [3.10.0] — 2026-10-30 · iteracion-20: marca Itzaka (paleta de piedra y logo de talud-tablero)

### Added
- **plataforma — TEC Versión visible**: La API dice qué versión corre: `APP_VERSION` se lee de `pyproject.toml` (una sola fuente; la sube el commit «Versión X.Y.Z»), el admin la muestra bajo «Itzaka» en la barra lateral y en el acceso (`src/templates/admin/login.html`), y `GET /api/health/` responde exactamente `{"status": "ok", "version": "X.Y.Z"}` (antes decía `"service": "presuplano-backend"`), sin autenticación para que una cookie vencida no la vuelva 401.

### Changed
- **marca — TEC Marca v2.0 — El producto se llama Itzaka**: Cuotreka pasa a llamarse Itzaka, una solución de Grupo Torres Muciño. Asuntos y firma de los correos («Este mensaje se generó desde Itzaka, una solución de Grupo Torres Muciño.»), «optimizado por Itzaka», admin «Itzaka Admin», remitente por omisión «Itzaka». Términos y privacidad en su versión 2026-10-28 con el nombre nuevo y la nota «Itzaka antes se llamaba Cuotreka (y antes, presuplano)»: todas las cuentas los vuelven a aceptar. Las cookies de la sesión pasan a `itzaka_access` / `itzaka_refresh`; las de antes (`cuotreka_*`) se siguen leyendo y se borran al renovar o salir, así nadie pierde su sesión. La tabla de caché pasa a `itzaka_cache` (la crea `createcachetable` en el build; la anterior queda sin uso). Paquete `itzaka-backend` (con `requirements.txt` exportado de nuevo de `uv.lock`). accounts 0012: solo el texto de ayuda del nombre de la organización.
- **marca — TEC Marca v2.0 — Logo y colores de Itzaka en los correos y el admin**: Los correos de la casa (sin membrete) llevan el encabezado en blanco con el símbolo a color en PNG @2x (`/email-logo@2x.png`, publicado por el frontend: el frontend se promueve antes) y, junto a él, «ITZAKA» en obsidiana con la regla del nombre escrito (Inter 800, +0.08 em) y la firma del grupo debajo; con membrete, la banda sigue siendo del color del despacho. Grises de piedra en la plantilla y pie en #5E5A55 (antes #94A3B8, que no llegaba a AA). Admin de Unfold con la obsidiana como primario y los neutrales de piedra y cal del manual v2.0. Una organización nueva nace con el color obsidiana #141517 (accounts 0013); las que ya existen conservan el color que tienen guardado.

---

## [3.8.0] — 2026-10-23 · iteracion-17: contrato de listas y acciones en lote

### Added
- **servicios — US-06 · US-110 El catálogo se pide por páginas y se borra en
  lote:** `GET /api/tariffs/` filtra por tipo de unidad (`?unit_type=a,b`),
  busca en nombre y descripción, ordena por nombre, precio o fecha de alta (por
  omisión, de la A a la Z) y `?id=a,b` rotula un selector sin bajar el
  catálogo. `POST /api/tariffs/bulk/delete/` borra la selección o todos los
  resultados de la búsqueda; el que está en una cotización se queda y dice por
  qué.
- **clientes — US-09 · US-109 Los clientes se piden por páginas y se borran en
  lote:** `GET /api/clients/` busca en nombre, teléfono y correo, filtra por
  contacto (`?has_contact=true` o `false`), ordena por nombre o fecha de alta
  (por omisión, de la A a la Z) y `?id=a,b` rotula un selector sin bajar la
  lista. `POST /api/clients/bulk/delete/` borra la selección o todos los
  resultados de la búsqueda; el que está en una cotización se queda y dice por
  qué.
- **cotizaciones — US-13 Las cotizaciones se piden por páginas:**
  `GET /api/quotes/` filtra por estado (varios a la vez,
  `?status=draft,in_project`) y por plano (`?plan=a,b`: las que salieron de
  esos planos), busca por cliente y ordena por fecha, importe (`total`) o
  cliente (`client_name`); por omisión, la más reciente. El importe y el
  cliente se calculan en la consulta, así que ordenar por ellos abarca todas
  las páginas.
- **proyectos — US-67 La lista de proyectos sin avances ni fotos:**
  `GET /api/projects/` entrega cada fila con su cliente, estado, cotizado,
  avanzado y porcentaje, sin partidas, avances ni fotos; filtra por estado
  (varios a la vez), busca por cliente y ordena por avance
  (`progress_percentage`), cotizado (`quoted_value`) o cliente
  (`client_name`); por omisión, el de menos avance. Lo cotizado y lo avanzado
  se calculan en la consulta, cada uno en su subconsulta, así que ordenar
  abarca todas las páginas. `GET /api/projects/{id}/` sigue trayendo el
  proyecto completo.
- **personal — US-96 · US-97 El personal se pide por páginas:**
  `GET /api/workers/` busca en nombre, teléfono, correo y los servicios que
  cobra; filtra por saldo (`?has_balance=true`), por tipo (`?kind=`) y por
  quienes hacen un servicio (`?service=<id>`, para repartir una partida), y
  ordena por saldo (`balance`) o por nombre; por omisión, primero a quien más
  se le debe. El saldo se calcula en la consulta —lo ganado menos lo pagado,
  nunca negativo—, así que filtrar y ordenar abarca todas las páginas.
  `GET /api/workers/totals/` da lo que se les debe y lo repartido de toda la
  cuenta.
- **planos — US-78 Los planos por páginas y eliminar varios:**
  `GET /api/plans/` busca por nombre y ordena por último cambio o por nombre
  (por omisión, el último que se tocó); el dispositivo recorre los resúmenes
  de cien en cien para ponerse al día. `POST /api/plans/bulk/delete/` elimina
  varios; las cotizaciones que salieron de ellos se quedan, sin el enlace.
- **colaboradores — US-138 Los colaboradores por páginas y en lote:**
  `GET /api/collaborators/` entrega la tabla de colaboradores e invitaciones
  por páginas, filtra por varios estados a la vez (`?status=pending,expired`),
  busca en el correo y ordena por correo (por omisión, de la A a la Z) o por
  desde cuándo. `POST /api/collaborators/bulk/<acción>/` activa, desactiva,
  quita o cancela varios: la acción que no aplica a una fila —desactivar una
  invitación, cancelar a un colaborador— dice por qué y las demás siguen.
- **plataforma — TEC Pruebas base del contrato de listas:**
  `tests/platform/test_list_contract.py` revisa cada vista que lista: que
  pagine con `DefaultPagination`, declare sus filtros, su búsqueda y una lista
  blanca de orden, y ordene por omisión con desempate por id; que las dos
  listas que no son vistas genéricas (colaboradores y mobiliario) también
  paginen, y que cada acción en lote tenga su límite `bulk`. Una vista nueva
  que no cumpla el contrato deja la línea base en rojo. Las pruebas de
  plataforma leen sus archivos en UTF-8: en Windows leían en cp1252.

### Changed
- **API — TEC Contrato de listas en el backend (US-77 · US-79):** todas las
  listas paginan siempre: sin `page` llegan las 20 primeras con `count`,
  `next`, `previous` y `results`, nunca más de 100 por página, y un desempate
  por id evita filas repetidas o perdidas entre páginas. Antes, sin `page` la
  lista llegaba entera como arreglo. Los filtros de django-filter, la búsqueda
  y el orden quedan por omisión en todas las vistas; la búsqueda y el orden de
  texto no distinguen acentos ni mayúsculas, igual en PostgreSQL que en SQLite
  (`common/search.py`). `common/filters.py` da los filtros de varios valores
  (`?status=a,b`) y `common/bulk.py` la base de las acciones en lote
  (`POST /api/<recurso>/bulk/<acción>/`, hasta `BULK_MAX_ITEMS` = 500
  registros, límite `bulk` de 30 por minuto).
- **API — TEC Contrato de listas: las listas que no son una pantalla:** los
  pagos de un proyecto, los avances, el reparto, los pagos al personal y los
  archivos del editor declaran sus filtros —los mismos `?project=` y
  `?worker=` de siempre, ahora validados: un id mal escrito es 400—, su
  búsqueda y un orden estable. `GET /api/plan-models/` llega por páginas como
  las demás listas; antes daba todas las fichas en un arreglo.

---

## [3.7.2] — 2026-10-22 · iteracion-16: bugs agrupados por gravedad

### Added
- **repositorio — TEC Archivos de trabajo del repositorio:** guía de
  desarrollo para personas y agentes (`.claude/CLAUDE.md`), reglas de
  contribución y del stack (`.claude/rules/`), `AGENTS.md` y `CONTRIBUTING.md`.
  El README adopta el formato de la casa —bloques generados de versión, stack,
  variables, comandos, quality gate, estructura, despliegue y contribución— y
  suma las secciones de módulos, autenticación y sesión, integraciones y
  administración, sin borrar el texto que ya tenía.

### Fixed
- **colaboradores — US-139 Reenviar sin dejar a la persona sin enlace
  (gravedad media-alta):** el reenvío cambiaba el enlace antes de mandar el
  correo; si el correo fallaba, el enlace anterior ya no servía y el nuevo no
  llegaba. Ahora el enlace nuevo reemplaza al anterior sólo cuando el correo
  salió: si no sale, `POST /api/collaborators/invitations/<id>/resend/` responde
  503 con `code: email_not_sent` y la invitación queda como estaba. La
  respuesta dice si el correo salió (`email_sent`).
- **correo — US-135 Producción no sale sin correo (gravedad media):** sin
  `RESEND_API_KEY`, o con el remitente de prueba de Resend, los códigos, las
  invitaciones y los documentos no le llegaban a nadie y sólo quedaba un aviso
  en el registro. Ahora `common/checks.py` (corre con `migrate`, parte del
  build) detiene el despliegue de producción y la versión anterior sigue
  atendiendo; un correo que no puede salir queda como error. Encendido por
  omisión con `VERCEL_ENV=production` (`REQUIRE_EMAIL_DELIVERY`), y las
  variables de Resend quedan en `.env.example`.
- **colaboradores — US-135 Una tanda de invitaciones sale de una vez (gravedad
  media):** hasta 20 correos salían uno por uno, con 10 s de espera cada uno,
  y si la función se cortaba a media tanda quedaban invitaciones pendientes
  que nunca recibieron su correo. Ahora la tanda sale en una sola petición
  (`mail.send_batch`, el endpoint de tandas de Resend) y en la misma
  transacción que las invitaciones: un corte no deja ninguna pendiente sin su
  correo.
- **colaboradores — US-136 El campo trampa lleno no deja una sesión a medias
  (gravedad baja):** la aceptación que el campo trampa descarta respondía sin
  `company`, y la aplicación fallaba después de guardar una sesión falsa.
  Ahora responde con la misma forma que una aceptación de verdad —la persona y
  la empresa a la que se entra—, sin cuenta ni sesión detrás.
- **API — US-135 · US-136 Dos peticiones al mismo tiempo no terminan en 500
  (gravedad baja):** una restricción única que choca entre dos peticiones
  responde 409 con qué hacer (`code: conflict`), sin el mensaje de la base.
  Invitar a la vez el mismo correo deja una sola invitación y la otra dice que
  ya está pendiente; aceptar a la vez dos invitaciones al mismo correo nuevo
  crea una cuenta y la otra pide entrar con su contraseña (409
  `account_exists`).
- **planos — US-92 El id de un plano no cambia al editarlo:** el id lo pone el
  editor al crear el plano; una edición (`PATCH`/`PUT /api/plans/<id>/`) con
  otro id responde 400 y no guarda nada.

---

## [3.7.1] — 2026-10-21 · iteracion-15: documentos legales en producción

### Fixed
- **legal — US-121 · US-122 · US-123 Los documentos legales en producción:**
  `excludeFiles` de `vercel.json` dejaba fuera de la función todos los `.md`,
  también los términos y la política de privacidad; el registro no cargaba los
  documentos vigentes y `/api/auth/me/` respondía 500. Ahora sólo se excluyen
  los `.md` de la raíz, y una prueba de plataforma lo vigila.

---

## [3.7.0] — 2026-10-21 · iteracion-14: colaboradores invitados

### Added
- **colaboradores — US-135 Invitar colaboradores por correo:** app `team` con
  `Membership` (quién colabora en la empresa de quién, activo o no) e
  `Invitation` (correo, huella SHA-256 del enlace, vigencia de 7 días).
  `POST /api/collaborators/invitations/` recibe de 1 a 20 correos y manda a
  cada uno, con la marca de la empresa, un enlace a `/invitacion/<token>`; no
  invita dos veces a quien ya colabora o ya tiene una invitación vigente, y
  dice por qué se saltó cada correo (límite de 30 por hora).
- **colaboradores — US-136 Aceptar una invitación y crear mi cuenta:**
  `GET /api/invitations/<token>/` (público) dice a qué empresa invita y si
  sigue vigente; `POST /api/invitations/<token>/accept/` crea la cuenta ya
  confirmada y sin empresa propia (`User.has_own_workspace`), o pide la
  contraseña de quien ya tiene una, abre la sesión y dice a qué empresa se
  entra. El enlace sirve una vez (vencida o cancelada 410, ya aceptada 409);
  reCAPTCHA y campo trampa como el registro.
- **colaboradores — US-137 Trabajar en las empresas que me invitan:** los datos
  se acotan a la empresa en la que se trabaja (`apps/team/tenancy.py`,
  `account_of(request)`): la cabecera `X-Empresa` la elige; sin ella, la propia
  o la primera donde se colabora activo. Una empresa ajena o donde lo
  desactivaron responde 403 con `code: company_access`. `/api/auth/me/` trae
  `companies` (id, nombre y papel). Los documentos salen con la marca de la
  empresa y las respuestas llegan a quien los manda.
- **colaboradores — US-138 Gestionar a mis colaboradores:**
  `GET /api/collaborators/` (con `?search=` y `?status=`) junta colaboradores
  e invitaciones que esperan; `PATCH/DELETE /api/collaborators/members/<id>/`
  activa, desactiva o quita de la empresa —lo registrado se queda y la cuenta
  sigue siendo de la persona—.
- **colaboradores — US-139 Reenviar o cancelar una invitación:**
  `POST /api/collaborators/invitations/<id>/resend/` (enlace nuevo por 7 días;
  el anterior deja de servir) y `…/cancel/`.

### Changed
- **organización — US-140 Lo que sólo el administrador decide:** cambiar la
  organización (nombre, color, logotipo, contacto) e invitar o gestionar
  colaboradores responden 403 a un colaborador (`IsCompanyAdmin`); ver la
  organización sigue abierto. US-71, US-102 y US-118 cambian en lo mismo.
- **cuenta — US-126:** un colaborador que elimina su cuenta no borra nada de
  la empresa.
- **CORS:** deja pasar la cabecera `X-Empresa`.

---

## [3.6.0] — 2026-10-20 · iteracion-13: plataforma y convenciones (admin, teléfonos y capas)

### Changed
- **admin — TEC Django Unfold:** el panel de administración usa Unfold en
  todos los modelos de la aplicación (se suman las partidas de cotización y los
  servicios del personal), con el usuario por correo en formularios de Unfold y
  los grupos registrados de nuevo. La CSP sólo se abre bajo `/admin/` para lo
  que Unfold necesita (`'unsafe-eval'` de Alpine y estilos en línea); la API
  conserva la estricta. Entrar al admin lleva a `/admin/`.
- **clientes — US-07 Teléfonos validados:** el teléfono de clientes,
  organización, personal y contactos se valida (`django-phonenumber-field`,
  región MX) y se guarda en E.164; la API lo devuelve como se escribe en México
  («55 1234 5678») o con su lada si es de fuera. Uno que no es teléfono se
  rechaza con «Escribe un teléfono válido, con su lada.». La migración pasa a
  E.164 los que ya estaban sin perder los que no se pueden leer.
- **arquitectura — TEC Capas e higiene:** las consultas y reglas de personal
  pasan de las vistas a `staff/selectors.py` y `staff/services.py`
  (`get_owned_worker`, `ensure_single_self`, `hand_out`). Pruebas de
  arquitectura: ninguna vista consulta modelos directamente y
  `requirements.txt` es exactamente el `uv export` del `uv.lock`.

### Fixed
- **dependencias vulnerables:** Pillow 13.0 corrige ocho vulnerabilidades altas
  publicadas después de la 3.5.0 que encontró el workflow `security`.

---

## [3.5.0] — 2026-10-20 · iteracion-12: seguridad (sesión, límites, reCAPTCHA, archivos y línea base)

### Added
- **seguridad — TEC Línea base de seguridad en pruebas y CI:**
  `src/tests/platform/test_security_baseline.py` vigila permisos y límites por
  defecto, caché compartida, tope de página, validadores de contraseña, cookies,
  cabeceras y el bloque HTTPS de producción, y revisa el código (campos
  explícitos, SQL con parámetros, ninguna credencial en los registros). Workflow
  `security` (gitleaks y pip-audit, con excepciones que vencen), Dependabot
  semanal contra `develop` y un solo umbral de cobertura (90 %).

### Changed
- **accounts — US-03 Sesión en cookies seguras:** el inicio de sesión deja el
  access (≤ 30 min) y el refresh (≤ 7 días) en cookies HttpOnly SameSite=Lax,
  Secure en producción; el cuerpo sólo trae la cuenta. El refresh rota en cada
  renovación (`POST /api/auth/refresh/`) y el usado queda en la lista negra;
  `POST /api/auth/logout/` lo anula y borra las cookies; cambiar o restablecer la
  contraseña cierra las demás sesiones. Las escrituras con la cookie exigen el
  token CSRF (`X-CSRFToken`). La cabecera `Authorization` sigue sirviendo.
- **API — límites de intentos (US-02):** throttling en toda la API (60/min por
  dirección, 300/min por cuenta) y por puerta: acceso 10/min, registro 10/h,
  códigos 5/min, recuperación 5/h, contacto 5/h, envío de documentos 30/h. Los
  contadores viven en la caché de la base (el build corre `createcachetable`) y
  el 429 dice «Demasiados intentos. Intenta de nuevo en N segundos.».
- **formularios públicos — US-83 reCAPTCHA y campo trampa:** registro, acceso,
  recuperación y contacto verifican un token de reCAPTCHA v3 por acción
  (`recaptcha_token`) antes de validar nada, en cuanto hay
  `RECAPTCHA_SECRET_KEY`; si Google no contesta, las puertas de la cuenta
  responden 503 y el contacto se guarda «por revisar» (`Lead.needs_review`). Un
  campo `website` lleno recibe la respuesta de siempre sin ningún efecto.
- **archivos — US-16 validados por su contenido:** evidencia, logotipo,
  texturas, piezas de mobiliario y documentos se juzgan por sus primeros bytes
  (filetype) y se guardan como `<uuid>.<ext>`; por correo sólo sale un PDF, con
  el nombre que pone el servidor. `R2_SIGNED_URLS` sirve el bucket privado con
  direcciones firmadas que vencen (apagado hasta cerrar el bucket).
- **seguridad — TEC Configuración de Django:** CSP estricta (django-csp),
  Referrer-Policy explícita, sólo JSON en producción, paginación opcional con
  tope de 100 por página (`page`, `page_size`) y tope del cuerpo de 5 MB.

### Fixed
- **accounts — contraseñas débiles:** los cuatro validadores de Django (con el
  de parecido al correo) se aplican al registrarse, recuperar y cambiar la
  contraseña; antes sólo se revisaba el largo.
- **accounts — código de verificación adivinable:** cada código muere al quinto
  intento fallido, y el código universal del MVP sólo abre cuentas sin correo
  configurado y donde se pidió (`OTP_UNIVERSAL_CODE_ENABLED`, encendido con
  `DEBUG`): en producción falla cerrado.
- **US-18 referencias de otra cuenta:** un id ajeno en una escritura se rechaza
  con el mismo mensaje que uno que no existe (`OwnedPrimaryKeyRelatedField`), y
  ya no queda un trabajador creado a medias cuando su servicio era ajeno. Pruebas
  de acceso cruzado para cada recurso.
- **correo — dato personal en los registros:** el destinatario se registra
  enmascarado (`j***@dominio.com`).
- **dependencias vulnerables:** pyjwt 2.15.1, sqlparse 0.6.0, Pillow 12.3,
  Django 5.2.18, djangorestframework 3.17.2 y urllib3 2.8.0 corrigen
  vulnerabilidades altas que encontró el workflow `security`.

## [3.3.1] — 2026-10-14 · iteracion-9: configuración de despliegue en Vercel

### Changed
- **despliegue — TEC Configuración de despliegue en Vercel:** sólo `main` y
  `develop` crean un despliegue; las ramas de trabajo quedan cubiertas por el
  quality gate de CI y ya no dejan un preview de ~300 MB cada una. La función
  `wsgi.py` excluye con `excludeFiles` las pruebas, los fixtures, la
  documentación y las cachés. El build instala sólo lo de ejecución
  (`uv sync --frozen --no-dev`) y migra, sin el `collectstatic` que copiaba a
  `/tmp` (WhiteNoise sirve los estáticos con sus finders). Nuevas pruebas en
  `test_deploy_entrypoint.py` vigilan esa configuración.

### Fixed
- **despliegue — `excludeFiles` dentro del límite de Vercel:** el esquema de
  `vercel.json` admite hasta 256 caracteres y el glob tenía 282, así que el
  despliegue de develop terminó en ERROR antes de construir. Ahora usa patrones
  `**/` equivalentes (210 caracteres), y una prueba vigila el límite.

## [3.2.0] — 2026-10-12 · iteracion-7: medidas antes de leer el plano y recorrido «Asignar materiales»

### Changed
- **planner — US-129 Medidas antes de leer el plano:** tras limpiar la foto,
  `POST /api/plans/photo-conversions/` busca primero sus cotas con una lectura
  rápida (el mismo modelo, esfuerzo bajo). Si no hay al menos una horizontal y
  una vertical legibles, responde `needs_measures: true` con los lados que faltan
  (`missing`: `width`, `height`) y la foto pulida, sin leer el plano y sin
  descontar una foto del tope diario. La foto vuelve a enviarse con `width_m` y/o
  `height_m` (mayores que 0; si no, «La medida debe ser mayor que 0»), que la IA
  recibe para aproximar los muros, o con `skip_measures` para leerla como antes.
  La respuesta trae `scale` (`cotas`, `medidas` o `null`) y `metres_per_pixel`
  de la foto pulida cuando la escala se conoce.

## [3.0.0] — 2026-10-09 · iteracion-5: importación de planos más fiel, edición más ágil y plano ↔ cotización

### Changed
- **planner — US-129 Puertas y ventanas:** la respuesta de
  `POST /api/plans/photo-conversions/` trae `openings`: cada puerta (`door`) y
  ventana (`window`) leída, con el muro en que está (`wall`, su lugar en
  `walls`) y dónde empieza y acaba a lo largo de él (`from`, `to`, de 0 a 1). Una
  puerta dibujada como hueco entre dos muros en línea une esos muros en uno; la
  que no cae en ningún muro se descarta.
- **planner — US-129 Las cotas se importan:** la respuesta trae `dimensions`:
  cada cota escrita en el plano, con la línea en que está dibujada (relativa a
  la foto) y lo que dice en metros (`value`). La escala que dan las cotas —la
  del medio, para que una mal leída no arrastre a las demás— decide qué está
  cerca al ordenar los muros; sin cotas, la provisional (1 px = 1 cm).

- **quotes — US-95 La cotización recuerda su plano:** `Quote.plan` (se borra
  el plano y la cotización se queda, sin el enlace) y `QuoteItem.from_plan`
  (la partida la midió el plano). `POST /api/quotes/` acepta `plan` y
  `items[].from_plan`; las lecturas traen `plan`, `plan_name` y
  `items[].from_plan`. Editar la cotización a mano conserva qué partidas
  vienen del plano.
- **quotes — US-95 Recotizar actualiza el borrador:**
  `POST /api/quotes/{id}/plan-sync/` con `plan` e `items`: las partidas del
  plano toman las cantidades nuevas y conservan su precio, la que ya no está
  sale, la nueva entra y las agregadas a mano no se tocan. Una cotización «En
  proyecto» responde 400.

### Fixed
- **planner — US-129 Habitaciones cerradas aunque haya puertas o huecos:** lo
  que traza la IA se ordena antes de volver (`photo_geometry`). Los extremos a
  menos de 15 cm son una sola esquina, donde se cruzan sus muros; el tabique que
  se queda corto o se pasa llega al muro. Cada espacio que cierran los muros
  —contando como cerrado el hueco de hasta 1,20 m de una puerta o un paso— sale
  como habitación con el nombre que la IA leyó dentro; el hueco sigue abierto en
  los muros. Lo cerrado de menos de 0,5 m² o de menos de 40 cm de ancho no es
  habitación.
- **planner — US-129 Muros a escuadra:** el muro convertido a menos de 8° de la
  horizontal, la vertical o la diagonal de 45° queda exactamente en ese ángulo,
  girado sobre su centro, aunque la hoja estuviera pandeada; el que se aparta
  más conserva el ángulo con que se dibujó. Un cuarto rectangular sale con sus
  esquinas a 90°.

### Notes
- Migración `quotes.0006_plano_de_la_cotizacion` (dos campos nuevos, sin
  pérdida de datos).

## [2.36.0] — 2026-10-06 · iteracion-4: de la foto de un plano en papel al plano editable

### Added
- **planner — US-129 Convertir la foto de un plano en un plano editable:**
  `POST /api/plans/photo-conversions/` recibe la foto (PNG, JPG o WEBP; hasta
  4 MB) y devuelve los muros y las habitaciones relativos a la foto, la foto
  pulida para el fondo y cuántas fotos le quedan hoy a la cuenta. La lee Claude
  con visión (`claude-opus-5-5`, salida JSON estructurada, un minuto como
  máximo). Tope de 5 fotos por cuenta al día (`PhotoConversion`, en el admin);
  lo que falla no cuenta. Sin `ANTHROPIC_API_KEY`, con error de la API o pasado
  el minuto, responde 503 «No pudimos convertir la foto ahora…».
- **planner — US-129 La foto se pule antes de la IA (OpenCV):** corrección de
  perspectiva (sin borde de hoja, como un escaneo, se sigue sin enderezar),
  recorte al dibujo, escala a 1568 px, corrección de iluminación, reducción de
  ruido, contraste y binarización. Menos de 1 s por foto.

### Notes
- Dependencias nuevas: `anthropic`, `opencv-python-headless`, `numpy`. El
  paquete de la función en Vercel pasa a 309 MB (Vercel lo optimiza al construir).
- Migración `planner.0002_photo_conversion` (tabla nueva).
- Variables nuevas: `ANTHROPIC_API_KEY` (obligatoria para convertir),
  `PHOTO_PLAN_MODEL`, `PHOTO_PLAN_DAILY_LIMIT`, `PHOTO_PLAN_MAX_BYTES`.

## [2.35.1] — 2026-10-05 · iteracion-2: enlace a la memoria en git

### Fixed
- **docs — TEC Enlace a la memoria del proyecto en git:** el README apuntaba a
  la carpeta de Google Drive; ahora enlaza al repositorio `cuotreka_docs` y al
  sitio https://cuotreka-docs.vercel.app. Sin cambios de código.

## [2.35.0] — 2026-10-01 · iteracion-1: quality gate y memoria del proyecto

### Added
- **ci — TEC Quality gate de CI:** workflow `quality-gate` en cada pull request
  a `main` y `develop`: corre las pruebas con cobertura y falla si alguna no
  pasa o si la cobertura de líneas baja de 90 % (`scripts/test_gate.py`). La
  cobertura se mide sobre `src/`, sin migraciones, pruebas ni ajustes.

### Changed
- **ci:** la integración continua corre en `main` y `develop` (antes `dev`).

### Notes
- Desde esta entrega la API comparte la **versión del producto** con la
  interfaz (antes llevaba su propia numeración; la última fue 1.19.0).

### Removed
- **docs — La documentación pasa a la memoria del proyecto:** `DEPLOY.md` se
  mueve a `cuotreka_docs` en Google Drive (`legado/backend/`). La API no
  cambia.

## [1.19.0] — 2026-09-29

### Changed
- **common/brand (US-127):** el producto se llama **CUOTREKA**, con el eslogan
  «Del plano a la obra, todo conectado.», escritos en un solo módulo sin
  dependencias. `common/branding` firma con él los correos sin membrete y el
  pie «optimizado por CUOTREKA» de los que sí lo llevan; los asuntos de los
  códigos y del aviso de cambio de correo dicen CUOTREKA.
- **common/mail (US-127):** el nombre que se lee en la bandeja es siempre el
  de la marca; de `RESEND_FROM` sólo se toma la dirección. Así el cambio de
  nombre no depende de editar la variable en el servidor.
- **apps/legal (US-123, US-127):** términos y privacidad en su versión
  **2026-09-29**, con el nombre nuevo y la nota de que CUOTREKA antes se
  llamaba presuplano. Como cambió la versión, todas las cuentas los vuelven a
  aceptar al entrar.

### Migrations
- **accounts 0008:** sólo el texto de ayuda del nombre de la organización
  («vacío los firma CUOTREKA»); no toca datos.

### Notes
- Se quedan como estaban: el dominio, el nombre del paquete, el del bucket y
  la base de la integración continua, que son identificadores y no la marca.

## [1.18.0] — 2026-09-27

### Added
- **apps/legal (US-121):** los términos y la política de privacidad viven en
  `apps/legal/documents/` como Markdown con cabecera (`title`, `version`).
  `GET /api/legal/` y `GET /api/legal/{terms|privacy}/` los sirven sin cuenta.
  Cambiar la `version` de un archivo es lo que vuelve a pedirlos a todos.
- **apps/legal (US-122, US-123):** `LegalAcceptance` guarda qué versión aceptó
  cada cuenta, cuándo, desde qué IP y con qué navegador. El registro exige
  `terms_version` y `privacy_version` vigentes; `POST /api/legal/accept/` las
  acepta después; `GET /auth/me/` dice en `legal` qué rige, qué se aceptó y si
  falta algo.
- **apps/accounts (US-124):** cambiar el correo en dos pasos: `POST
  /auth/me/email/` lo deja en `pending_email` y manda el código al correo
  nuevo; `.../verify/` lo confirma y avisa al de antes; `.../resend/` y
  `DELETE` reenvían o desisten. `PATCH /auth/me/` hace lo mismo que el primer
  paso.
- **apps/accounts (US-125):** `POST /auth/me/password/` cambia la contraseña
  con la actual.
- **apps/accounts (US-126):** `POST /auth/me/delete/` elimina la cuenta con su
  contraseña: borra en orden todas sus filas —pagos, proyectos con avances,
  fotos y reparto, cotizaciones, personal, servicios, clientes, planos,
  archivos del editor, organización, suscripción, códigos y constancias— y,
  confirmado el borrado, sus archivos del bucket: los que la base nombra y
  todo lo que cuelga de sus carpetas. No se anonimiza nada.

### Migrations
- **accounts 0007:** `pending_email` y el motivo de código «cambio de correo».
- **legal 0001:** constancias de aceptación.

## [1.17.0] — 2026-09-26

### Added
- **apps/quotes (US-115, US-116):** la cotización guarda `notes`
  (observaciones, hasta 2000 caracteres) y `validity_days` (1 a 365; 20 por
  omisión). Una pantalla que no los manda al editar —una versión vieja todavía
  abierta— conserva los que la cotización ya tenía.
- **apps/accounts (US-118):** la organización guarda `email` y `phone` de
  contacto, los que imprimen los documentos. Son opcionales y se pueden vaciar;
  el correo se valida.

### Changed
- **apps/accounts (US-01, US-02, US-03, US-82, US-89, US-104):** la cuenta
  **es su correo**. `User` pierde `phone` e `is_phone_verified`, y `email` pasa
  a ser obligatorio. Registro, acceso, verificación, reenvío y recuperación
  aceptan sólo correo (`email`; también `identifier`, el nombre del campo en
  las pantallas anteriores), sin distinguir mayúsculas; un número se rechaza
  con «Escribe un correo válido». `PATCH /auth/me/` cambia sólo el correo, que
  queda por verificar y recibe su código. El código universal sirve sólo
  mientras el correo no esté configurado.
- **apps/catalog (US-117):** la unidad `unit` se lee **«Por lote (único)»**. El
  valor guardado no cambia.

### Migrations
- **accounts 0006:** antes de exigir el correo, cualquier cuenta que sólo
  tuviera teléfono recibe uno de relleno (`sin-correo-<id>@presuplano.invalid`,
  un dominio que no existe), para no perderla; después se quitan `phone` e
  `is_phone_verified` y se agregan el correo y el teléfono de la organización.
  Probada de ida y de vuelta.
- **catalog 0005, quotes 0005:** etiqueta de la unidad; observaciones y
  vigencia de la cotización.

## [1.16.0] — 2026-09-26

### Added
- **apps/projects (US-113):** los avances se **corrigen y se borran**.
  `PATCH /progresses/{id}/` cambia cantidad, fecha o quién lo hizo; lo que el
  avance ya tenía vuelve a estar disponible, así que se puede subir de 5 a 7
  aunque falten sólo 2, pero nunca pasar de lo cotizado. Cambiar a quien lo
  hizo toma el precio acordado con esa persona; corregir sólo la cantidad
  conserva el trato con el que se hizo el trabajo. `DELETE` lo quita junto con
  sus fotos. Un proyecto finalizado no cambia.
- **apps/projects (US-16):** `DELETE /evidences/{id}/` quita una foto, también
  del almacenamiento —después de confirmar el borrado, para que un fallo no
  deje un registro apuntando a nada—.
- **apps/clients, apps/catalog, apps/quotes (US-109, US-110, US-111):** borrar
  con reglas. Un cliente o un servicio sólo si no está en ninguna cotización;
  una cotización sólo si no es proyecto. Antes el borrado tropezaba con la
  protección de la base y respondía **500**; ahora dice por qué no, en una
  frase. Al borrar una cotización se van con ella los servicios que se
  crearon sólo para ella, si nadie más los usa.
- **apps/clients, apps/catalog:** cada cliente y cada servicio dicen en
  cuántas cotizaciones están (`quotes_count`), para que la lista sepa de
  antemano cuáles se pueden borrar.

### Fixed
- **apps/projects (US-16):** la evidencia fotográfica se subía y **no se
  volvía a ver**: el proyecto no devolvía las fotos. Ahora cada avance viene
  con su id, su partida, lo que vale y sus fotos con la dirección desde la que
  se ven.

### Tests
- 258 en verde (32 nuevas).

## [1.15.3] — 2026-09-25

### Fixed
- **common/mail (crítico):** ningún correo salía. La API de Resend está detrás
  de Cloudflare, que corta las peticiones cuya firma parece un script suelto:
  con el `User-Agent` que pone `urllib` por omisión la respuesta era un **403
  con «error code: 1010»** —una página de Cloudflare, no de Resend—, y el
  intento no llegaba siquiera a aparecer en el registro de la cuenta. El
  cliente se presenta ahora con su propio nombre.

## [1.15.2] — 2026-09-25

### Fixed
- **common/mail:** un envío rechazado decía sólo «Email refused by Resend». El
  motivo viajaba en los campos extra del registro, que el visor de la
  plataforma no muestra, así que no había con qué corregir nada. Ahora el
  mensaje lleva el código HTTP, el remitente, el destinatario y lo que contestó
  Resend.
- **core/settings:** la llave y el remitente se recortan al leerlos. Un salto
  de línea pegado al copiar el valor invalida la llave —Resend contesta 401— y
  no se ve en ningún lado.

## [1.15.1] — 2026-09-25

### Changed
- **apps/accounts:** una cuenta con correo **lo verifica antes de entrar**. El
  correo es el canal que existe de verdad —por ahí llega el código y por ahí
  salen los comprobantes—, así que dejar entrar con uno sin confirmar era dejar
  una cuenta a la que no se le puede escribir. El teléfono sigue mandando en
  las cuentas que sólo tienen teléfono, que es lo único que se les puede pedir.
- **apps/accounts:** el 403 de acceso sin verificar dice ahora **a dónde salió
  el código** (`identity`). Quien entra con su teléfono y tiene el correo sin
  confirmar recibe el código en el correo; sin este dato la pantalla siguiente
  le pediría el del teléfono y confirmaría el canal equivocado.

### Added
- **apps/accounts:** `GET /api/auth/organization/logo/` entrega el logotipo
  **incrustado** en la respuesta. El PDF lo dibuja el navegador, y el navegador
  no puede bajar del bucket un archivo de otro dominio que no lo autoriza: por
  eso los documentos salían sin marca. La API sí puede leerlo.

### Notes
- El remitente por omisión (`onboarding@resend.dev`) es el de pruebas de
  Resend: entrega sólo al dueño de la cuenta, así que a un cliente no le llega.
  Con la llave puesta hay que fijar `RESEND_FROM` a un dominio verificado, y
  mientras no lo esté cada envío lo deja anotado.

### Tests
- 225 tests (10 nuevos): el correo sin verificar que no abre la cuenta, el
  código que sale solo al intentar entrar, el 403 que dice a dónde fue, la
  cuenta con sólo teléfono que no cambia, el correo agregado desde el perfil
  que cierra la puerta hasta confirmarlo, y el logotipo servido en bytes.

## [1.15.0] — 2026-09-25

### Added
- **apps/accounts (US-104):** una cuenta se identifica por **teléfono, correo, o
  ambos**. `register/`, `login/`, `verify-otp/`, `resend-otp/` y
  `password-reset/` aceptan `identifier` (y siguen entendiendo `phone`, que es
  lo que mandan las pantallas publicadas). `PATCH /api/auth/me/` cambia el
  teléfono y el correo desde el perfil: el dato nuevo entra sin verificar y con
  su código en camino, y la cuenta no puede quedarse sin ninguno de los dos.
- **apps/accounts (US-105):** **código de un solo uso de verdad**
  (`OtpCode`). Una cuenta con correo recibe el suyo, de seis cifras, guardado
  cifrado, con vencimiento (`OTP_TTL_MINUTES`) y que muere al usarse. El
  universal (`OTP_UNIVERSAL_CODE`) queda para quien no tiene por dónde recibir
  el suyo: las cuentas con sólo teléfono, mientras no haya SMS.
- **common/mail (US-105):** **Resend por su API HTTP**, no por el mailer de
  Django: en serverless no hay conexión SMTP que sostener y una llamada HTTPS es
  lo único que la plataforma siempre permite. Nunca lanza —un correo que no sale
  se anota y la pantalla sigue— y la plantilla se pinta con el membrete de la
  organización cuando lo hay, con un pie de «optimizado por presuplano», y con
  el de presuplano cuando no.
- **apps/documents (US-105):** `POST /api/documents/send/` entrega los cuatro
  documentos por correo —cotización, estatus de proyecto, comprobante de pago y
  de cobro— con el PDF adjunto. El PDF llega hecho desde el navegador, que es
  donde están las fuentes y el logotipo ya descargado; el servidor pone el
  sobre. Tope de 8 MB por adjunto (`DOCUMENT_EMAIL_MAX_BYTES`).
- **apps/assets (US-103):** `/api/plan-models/` guarda el **catálogo de
  mobiliario** de la cuenta. Los bytes de las mallas ya viajaban, pero la ficha
  que las nombra —nombre, categoría, medidas reales— se quedaba en el navegador
  que importó la biblioteca: el catálogo aparecía vacío en el teléfono aunque el
  plano dibujara los muebles. Las fichas van y vienen en lote y se guardan tal
  como las escribe el editor.

### Notes
- Sin `RESEND_API_KEY` no hay envío: el código vuelve a ser el universal para
  todas las cuentas y `documents/send/` responde 400 diciendo que no está
  configurado, en vez de fingir que envió. Ver `DEPLOY.md`.
- `phone` pasa a admitir nulo para que una cuenta pueda existir sólo con su
  correo. Van nulos —y no en blanco— cuando faltan: dos cadenas vacías chocarían
  contra el índice único, mientras que dos nulos conviven.

### Tests
- 215 tests (16 nuevos): alta y acceso con correo, el código propio que vence y
  se gasta, el universal que deja de abrir una cuenta con correo, el cambio de
  identidad desde el perfil, el catálogo de modelos que no se duplica ni se ve
  entre cuentas, el envío de cada documento con y sin membrete, y la llamada a
  Resend —con su adjunto en base64— que no tumba nada cuando falla.

## [1.14.0] — 2026-09-25

### Added
- **apps/assets (US-101):** `/api/plan-assets/` guarda en la cuenta los
  binarios del editor —las texturas y las mallas del mobiliario—, que hasta
  ahora vivían sólo en el navegador que los importó: abrir el plano en otro
  dispositivo dejaba cajas grises y muros en blanco. Se guardan una sola vez,
  direccionados por la misma ruta con la que el plano ya los nombra, y `missing/`
  dice cuáles faltan para no volver a subir una biblioteca entera en cada
  importación.
- **apps/accounts (US-102):** la organización puede llevar **logotipo**. Se sube
  a la misma cuenta y sale en los documentos junto al nombre.
- **En el bucket, una carpeta por organización**, con los nombres del oficio:
  `<uuid>/logo/`, `<uuid>/texturas/` y `<uuid>/inmobiliario/`. Lo que hay en el
  almacenamiento se puede leer sin conocer este código.

### Notes
- Los bytes **nunca viajan dentro del documento del plano**: un escaneo de fondo
  o una biblioteca de texturas se saltaría cualquier tamaño razonable, y la
  misma textura usada en diez planos se guardaría diez veces.
- Subir dos veces la misma ruta no es un error: es el mismo archivo y la cuenta
  ya lo tiene. Importar una biblioteca dos veces —o desde dos dispositivos— no
  cuesta nada.
- Tope de 10 MB por archivo del editor (`PLAN_ASSET_MAX_BYTES`) y de 2 MB por
  logotipo: es una marca, no una fotografía.

### Fixed
- **apps/staff:** el precio que se le paga a alguien viajaba como número y el
  formulario que lo lee espera texto. Ahora va como cadena, igual que el resto
  del dinero de esta API.

### Tests
- 178 tests (10 nuevos): subir una textura y una malla, la carpeta que cuelga de
  la organización, la ruta repetida que no duplica, el cotejo de lo que falta,
  el archivo por encima del tope, el aislamiento entre cuentas, y el logotipo
  que se sube, se lee y se quita.

## [1.13.0] — 2026-09-25

### Added
- **apps/dashboard (US-99):** `/api/dashboard/` responde, en un solo viaje, lo
  que el arquitecto abre la aplicación a preguntar: cuántas obras están en
  marcha, cuántas cotizaciones se hicieron y cuántas se volvieron proyecto —y
  **cuánto representan en dinero** del total cotizado, que es lo que dice si se
  están ganando las que importan—, las cuentas por cobrar y las cuentas por
  pagar, los ingresos de los últimos seis meses terminando en el actual, y las
  tablas de lo más vendido: diez servicios, cinco clientes y cinco personas del
  personal.

### Notes
- **Vendido es lo que se volvió obra:** las tablas de servicios y clientes leen
  las cotizaciones convertidas en proyecto, no todas. Una cotización que nunca
  se ganó no vendió nada.
- **Ingreso es lo cobrado**, no lo ganado: lo que la cuenta puede contar es lo
  que el cliente ya pagó.
- «Yo» —el propio despacho— no aparece entre el personal con más trabajos: no
  es alguien a quien contarle trabajos.
- La conversión se mide **en dinero**: dos cotizaciones chicas ganadas y una
  grande perdida no son un 66 % de nada.

### Tests
- 168 tests (11 nuevos): lo que hay en marcha, la conversión en dinero, lo que
  se cobra y lo que se debe, los seis meses terminando hoy —con un cobro viejo
  que no se cuela—, los más vendidos leyendo sólo lo vendido, los clientes que
  compran, el personal con más trabajos sin contar a la casa, la cuenta recién
  abierta y el aislamiento entre cuentas.

## [1.12.0] — 2026-09-24

### Added
- **apps/staff (US-96):** el personal —la persona o la empresa que ejecuta el
  trabajo— con lo que sabe hacer y **a cómo se le paga**, que no es lo que se
  le cobra al cliente: la diferencia es el margen de la obra. Un servicio lo
  pueden hacer varios y cada quien puede hacer varios. `/api/workers/`.
- **El reparto (US-97):** `/api/assignments/` entrega parte de una partida a
  alguien, a un precio acordado que se **congela ahí** —cambiar un trato de hoy
  no puede reescribir lo ya repartido—. No se puede repartir más de lo que la
  partida tiene, y repartir dos veces lo mismo a la misma persona corrige el
  reparto en vez de duplicarlo. `/api/projects/:id/distribution/` dice, partida
  por partida, quién lleva qué y qué falta por repartir.
- **El avance dice quién lo hizo (US-98):** `POST /projects/:id/progress/`
  acepta `worker`, y con él copia el precio de mano de obra del reparto. Así lo
  ejecutado se convierte en lo devengado: dos cifras separadas a propósito —lo
  **comprometido**, que es todo lo repartido, y lo **devengado**, que es lo que
  ya se trabajó—. Se paga contra lo devengado.
- **Pagos al personal (US-98):** `/api/worker-payments/` registra el pago de un
  proyecto o el de la semana entera, y `summary/` devuelve comprometido,
  devengado, pagado, saldo y anticipo. A «Yo» —el registro del propio despacho,
  uno solo por cuenta— se le reparte trabajo pero no se le paga.

### Notes
- El saldo nunca es negativo: lo entregado de más se informa aparte como
  anticipo, para que no se lea como deuda.
- Un avance sin autor no le debe nada a nadie; es trabajo de la casa.

### Tests
- 157 tests (17 nuevos + 1 app): alta de persona y de empresa, el mismo
  servicio en varias manos, «Yo» único por cuenta, aislamiento entre cuentas,
  el reparto con y sin precio acordado, el tope de lo repartible, lo que falta
  por repartir, el devengo por autor, el pago que baja el saldo, el pago
  general sin proyecto y los dos rechazos: pagarse a uno mismo y pagarle al
  personal de otra cuenta.

## [1.11.0] — 2026-09-24

### Added
- **apps/planner (US-92):** los planos dejan de vivir sólo en el navegador que
  los dibujó. `/api/plans/` los guarda por cuenta y los devuelve a cualquier
  dispositivo: la lista trae resúmenes —pintar cinco renglones no puede costar
  cinco planos enteros por la red del teléfono— y el detalle, el documento
  completo, tal como lo serializa el editor, con su propio número de versión de
  formato.
- El plano conserva **el id que le puso el editor**: es el de su dirección, y
  con otro el plano del teléfono y el de la computadora serían dos. El resumen
  incluye además la fecha que estampó el editor, que es con la que cada
  dispositivo decide qué copia es la nueva sin depender de que su reloj y el
  del servidor coincidan.
- Tope de 4 MB por documento (`PLAN_MAX_BYTES`), con un mensaje que dice qué
  suele pesar: el plano de fondo escaneado o una textura suelta, que viajan
  dentro del documento.

### Tests
- 139 tests (11 nuevos): guardar y volver a abrir, que la lista no carga el
  documento, que guardar otra vez reemplaza, que un plano ajeno no existe, que
  sin sesión no hay planos, el nombre obligatorio, el tope de peso explicado,
  el borrado, el orden por lo último tocado, el id propio y la fecha del
  documento.

## [1.10.0] — 2026-09-24

### Changed
- **apps/accounts (US-90):** entrar con un teléfono sin verificar ya no es un
  callejón. `POST /api/auth/login/` manda el código otra vez antes de negar el
  paso, y responde 403 con `code: "phone_not_verified"` junto al mensaje de
  siempre: la pantalla necesita distinguir esto de una contraseña equivocada
  para llevar a escribir el código, y hacerlo comparando el texto del mensaje
  se rompería el día que cambie la redacción.
- **apps/accounts:** el envío del código vive en un solo sitio
  (`send_verification_code`), que es donde se colgará el SMS de verdad. Lo usan
  el reenvío y el acceso sin verificar.

### Tests
- 128 tests (1 nuevo): que entrar sin verificar deja el código enviado y nombra
  el motivo con su propio código.

## [1.9.0] — 2026-09-24

### Added
- **apps/accounts (US-89):** `POST /api/auth/resend-otp/` vuelve a enviar el
  código de verificación. Quien no lo recibía se quedaba mirando la pantalla:
  la única salida era registrarse otra vez, que además falla porque el teléfono
  ya existe. Responde igual exista o no la cuenta y esté o no verificada —lo
  contrario convertiría el endpoint en un detector de clientes—; en el MVP el
  código es el OTP universal, así que lo que deja es registro del intento, con
  el envío real de SMS por detrás el día que lo haya.

### Tests
- 127 tests (5 nuevos): que una cuenta pendiente puede pedir el código otra vez
  y queda anotado, que un teléfono desconocido y uno ya verificado responden lo
  mismo, que el teléfono es obligatorio y que sólo se acepta por POST.

## [1.8.0] — 2026-09-19

### Added
- **apps/accounts (US-82):** recuperar la contraseña.
  `POST /api/auth/password-reset/` la pide y
  `POST /api/auth/password-reset/confirm/` la cambia con el mismo código que
  verifica el teléfono. No existía: quien la olvidaba quedaba fuera para
  siempre, y tampoco tenía a quién escribirle. Pedirla responde igual exista o
  no la cuenta —responder distinto convertiría el endpoint en un detector de
  clientes— y quien la recupera queda con el teléfono verificado, porque ha
  demostrado lo mismo que verificándolo.
- **apps/leads (US-83):** `POST /api/contact/` recibe un mensaje de quien
  todavía no tiene cuenta —nombre y un teléfono o un correo para responderle—.
  Se leen en el admin: la página deja mensajes, no los consulta.

### Tests
- 122 tests. Dieciséis nuevos: ocho de la recuperación (incluido que un teléfono
  desconocido responde igual y que un código inválido no cambia nada) y ocho del
  contacto.

## [1.7.0] — 2026-09-18

### Added
- **apps/accounts (US-71):** la cuenta guarda el membrete con el que firma sus
  documentos. `GET/PATCH /api/auth/organization/` lee y edita el nombre del
  despacho y su color, y `GET /api/auth/me/` lo devuelve junto a la suscripción.
  El nombre es opcional —vacío, el papel lo sigue firmando presuplano, que es
  como venía funcionando— y el color se valida como hexadecimal de seis dígitos
  y se guarda en mayúsculas, para que el mismo color escrito de dos formas sea
  uno. Pedir la organización la crea si no existía, así que ninguna pantalla se
  topa con un 404 que no pueda resolver.
- Migraciones `0002_organization` y `0003_organization_for_existing_accounts`:
  la segunda le da un membrete vacío a las cuentas anteriores, porque `/auth/me/`
  solo lo reporta y lo habrían leído como `null` hasta abrir esa pantalla.

### Tests
- 106 tests. Trece casos nuevos: el membrete vacío de una cuenta nueva, guardar
  nombre y color, la cuenta que ya lo trae, guardar dos veces sin duplicarlo,
  cuatro colores inválidos, la normalización a mayúsculas, el recorte de
  espacios, el acceso sin sesión y el aislamiento entre cuentas.

## [1.6.0] — 2026-09-18

### Added
- **apps/accounts (US-69):** `GET /api/auth/me/` devuelve la cuenta de quien
  pregunta —teléfono, verificación, fecha de alta— y su suscripción con plan y
  estado. La sesión solo llevaba el teléfono, que no alcanza para una pantalla
  de perfil. Una cuenta sin suscripción responde `null` en ese campo en lugar de
  fallar, porque la pantalla tiene que poder decir «sin suscripción».

### Tests
- 93 tests. Cuatro casos nuevos: los datos de la cuenta, la suscripción, la
  cuenta sin suscripción y el acceso sin sesión (401).

## [1.5.0] — 2026-09-18

### Changed
- **apps/quotes (US-12, US-11):** «documento generado» deja de ser un estado de
  la cotización. El documento se construye a partir de ella cada vez que se
  pide, así que existe desde que existe la cotización: desaparece la operación
  `POST /quotes/:id/generate-document/` y el estado queda en **borrador** hasta
  que se convierte en proyecto. Editar está permitido mientras no lo sea, en
  lugar de bloquearse al imprimir el papel.
- **apps/projects (US-14):** un proyecto arranca desde cualquier cotización de
  la cuenta, sin el paso previo de documentarla.
- Migración `0004_quote_document_is_not_a_state`: devuelve a borrador las
  cotizaciones marcadas como documentadas, que es lo que son.

### Tests
- 89 tests. La suite cubre que una cotización nace y sigue siendo borrador por
  muchas veces que se edite, que deja de editarse al ser proyecto, y que la
  operación de generar documento ya no existe.

## [1.4.0] — 2026-09-17

### Fixed
- **apps/quotes (US-63):** un total acordado que no se reparte en centavos ya
  no pierde dinero. 32 000 entre 15 dejaba el precio en 2 133,33 y la partida
  se cobraba a 31 999,95. `QuoteItem.unit_price` pasa a **seis decimales** —los
  que admite el valor unitario de un CFDI, que nace del mismo problema— y
  `subtotal` redondea a centavos una sola vez (`ROUND_HALF_UP`), que es lo que
  de verdad se factura; así 3 × 33,333333 se cobran como 100,00 y el total
  vuelve a ser el pactado. El serializador de entrada acepta esos decimales.
  Migración `0003_alter_quoteitem_unit_price` (solo amplía la columna: ningún
  dato existente cambia de valor).

### Tests
- 89 tests. Tres casos nuevos: el total que no divide en centavos, la línea
  cobrada en centavos enteros y el precio de siempre, que sigue comportándose
  igual.

## [1.3.1] — 2026-09-17

### Fixed
- **vercel.json, pyproject.toml, wsgi.py (incidencia de despliegue):** la API
  respondía **404 a todo** en producción. No era el código: Vercel pasó a
  entregar a la aplicación la ruta **ya reescrita** cuando hay un rewrite
  interno —lo avisa el propio build: *«Internal rewrites in backend framework
  projects now route requests using the rewritten destination path»*—, así que
  el `/(.*)` → `/api/index` que llevaba aquí desde el principio hacía que
  Django resolviera siempre `/api/index`, no encontrara ninguna URL y devolviera
  su página de «Not Found». Se quita el rewrite y se le declara a Vercel la
  instancia WSGI a servir (`[tool.vercel] entrypoint = "wsgi:application"`),
  que es la forma que hoy documenta para Django; con ella desaparece
  `api/index.py`, que además compartía nombre con la app `api` del proyecto.

### Tests
- **api/tests/test_deploy_entrypoint.py:** importa el entrypoint como lo hace
  Vercel, comprueba que resuelven rutas reales de la API y del admin, y falla si
  vuelve a aparecer un rewrite general. 86 tests. Nada bajo `src/` podía ver
  esto, que es por lo que 80 tests en verde convivieron con una API que no
  respondía a nada.

## [1.3.0] — 2026-09-17

### Added
- **apps/quotes (US-63):** `unit_price` opcional en cada partida enviada. El
  precio del catálogo es un punto de partida, no una condena: un cliente
  negocia, o se acuerda un total redondo que hay que repartir entre la
  cantidad. El precio enviado vale solo para esa cotización; omitido, se sigue
  tomando el del servicio, y el servicio conserva el suyo en cualquier caso. Un
  precio de cero o negativo se rechaza con 400.

### Changed
- **apps/catalog, apps/quotes (v2.9 del producto):** lo que la aplicación
  llamaba «tarifas» y «partidas» se llama ahora «servicios» en todo lo que se
  lee —el error que llega a la pantalla («Servicio no encontrado.»), los
  nombres del admin—. El recurso de la API sigue siendo `tariffs`: renombrarlo
  rompería a cualquier cliente ya instalado. Las migraciones 0004 (catalog) y
  0002 (quotes) solo cambian opciones de modelo, sin tocar el esquema.

### Tests
- 80 tests, ruff limpio. Cinco casos nuevos para el precio ajustable, incluido
  el que comprueba que el catálogo no se altera al ajustar una partida.

## [1.2.0] — 2026-07-24

### Changed
- **apps/payments (refactor de convenciones):** la búsqueda de proyecto por
  dueño se mueve de la vista a un selector (`selectors.get_owned_project`),
  conforme a "no queries en vistas". Comportamiento preservado (75 tests, ruff
  limpio, cobertura 95%).

## [1.1.0] — 2026-07-24

Iteración v1.1: método de pago y anticipos, avances solo por cantidad con
cantidad pendiente por partida, tarifas con descripción y tarifa única de
cotización, y renovación de sesión JWT.

### Added
- **apps/accounts (US-03):** endpoint `POST /api/auth/refresh/` y tiempos de
  token configurables (`SIMPLE_JWT`: acceso 60 min, refresh 30 días) para
  renovar la sesión sin cerrarla.
- **apps/catalog (US-04):** campo `description` (opcional) en `Tariff`.
- **apps/catalog (US-22):** campo `in_catalog` en `Tariff`; el listado del
  catálogo excluye las tarifas únicas de cotización (`in_catalog=false`).
- **apps/payments (US-18):** campo `method` en `Payment` (efectivo/transferencia).
- **apps/projects (US-15):** `ProjectSerializer.items` con `pending_quantity`.
- **apps/projects (US-23):** `ProjectSerializer.progresses` (fecha, ítem,
  cantidad) para el documento de estado del proyecto.

### Changed
- **apps/payments (US-18/20):** `register_payment` ya no topa el pago por el
  saldo (permite anticipos); el resumen expone `pending_balance` como saldo por
  cobrar = máx(cotizado − pagado, 0), `credit_balance` (saldo a favor) y el
  método por pago. `pending_balance` avanzado−pagado se conserva para el cierre.
- **apps/projects (US-15):** `register_progress` acepta solo cantidad (se elimina
  el porcentaje) y valida contra la cantidad pendiente de la partida.

## [Unreleased]

### Fixed
- **Deploy Vercel:** el backend no tenía entrypoint serverless, por lo que Vercel
  no enrutaba nada (incluida la ruta `/admin/`) y no se corrían migraciones. Se
  añadió `api/index.py` (WSGI), `vercel.json` con `buildCommand` que aplica
  **migraciones** y `collectstatic`, y `requirements.txt` de runtime. **WhiteNoise**
  sirve los estáticos del admin/DRF; `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS` se
  completan solos con los hostnames de Vercel (admin operativo en preview/prod).

### Added
- **Media en Cloudflare R2:** `core/settings_storages.py` enruta la media
  (evidencias, `ImageField`) a **R2** (S3 vía `django-storages`) cuando hay
  credenciales; en dev/tests cae a filesystem local. La media se **aísla por
  cuenta** (`evidence/<cuenta>/…`, `common/uploads.py`). Estáticos siguen en
  WhiteNoise. Variables R2 documentadas en `.env.example` y `DEPLOY.md`.
- **apps/projects (US-21):** Cierre de proyecto — acción `finalize/` que finaliza el
  proyecto y genera el **documento resumen** (avances con fechas, pagos y totales
  cotizado/avanzado/pagado). Con saldo pendiente advierte "El proyecto tiene un saldo
  pendiente de cobro de X" y solo finaliza con `confirm`; una vez finalizado bloquea
  nuevos avances/pagos ("El proyecto está finalizado").
- **apps/payments (US-18/19/20):** Pagos — `Payment` y `PaymentViewSet` en
  `/api/payments/`. Registrar pago total o parcial validando monto > 0 y que no
  supere el **saldo pendiente** (= avanzado − pagado); resumen de cobros
  (`summary/`) con total pagado y saldo; comprobante (`voucher/`) del último pago
  con su saldo resultante ("No hay pagos para generar un comprobante" si no hay).
- **apps/projects (US-14/15/16/17):** Proyecto y avances — `Project`, `Progress` y
  `Evidence`. Iniciar proyecto desde una cotización documentada (`/api/projects/`);
  registrar avance por **cantidad o porcentaje** normalizado, con validación de
  exceso ("El avance supera la cantidad cotizada") y avance > 0; adjuntar evidencia
  fotográfica (`/api/progresses/{id}/evidence/`) validando tipo imagen y tamaño;
  resumen con valor cotizado, avanzado y **porcentaje de avance**.
- **apps/quotes (US-10/11/12/13):** Cotizaciones — `QuoteViewSet` en `/api/quotes/`
  con `Quote` + `QuoteItem`. Total automático desde las partidas; cada partida
  **congela** nombre/unidad/precio de la tarifa al cotizar (histórico de precio,
  US-05). Crear valida partidas y cantidad > 0; editar borrador recalcula el total
  y se bloquea tras generar el documento; acción `generate-document/` idempotente
  ("No se puede generar… sin partidas"); listado aislado por cuenta.
- **apps/clients (US-07/08/09):** Clientes — `ClientViewSet` en `/api/clients/`
  (crear, editar, listar) con modelo `Client` propiedad por cuenta y aislamiento
  multi-tenant. Nombre obligatorio ("El nombre del cliente es obligatorio") y correo
  con formato válido ("El correo no tiene un formato válido").
- **apps/catalog (US-04/05/06):** Catálogo de tarifas — `TariffViewSet` en
  `/api/tariffs/` (crear, editar, listar) con modelo `Tariff` propiedad por cuenta.
  Aislamiento multi-tenant (cada cuenta ve solo sus tarifas), validación de precio
  positivo ("El precio debe ser mayor a 0" / "…un número mayor a 0") y nombre
  obligatorio.
- **apps/accounts (US-03):** Inicio de sesión — `POST /api/auth/login/` autentica por
  teléfono y contraseña y devuelve tokens JWT (SimpleJWT). Verifica credenciales antes
  que el estado del teléfono: contraseña incorrecta → 401 "Credenciales inválidas";
  teléfono no verificado → 403 "Debes verificar tu teléfono antes de iniciar sesión".
- **apps/accounts (US-02):** Verificación de teléfono — `POST /api/auth/verify-otp/`
  activa la cuenta comparando (constant-time) contra el código OTP universal del
  MVP. Rechaza código inválido ("Código de verificación inválido") y reverificación
  ("El teléfono ya está verificado").
- **apps/accounts (US-01):** Registro de cuenta — `POST /api/auth/register/` crea
  el usuario (teléfono + contraseña, en estado pendiente de verificación) y su
  suscripción activa con plan inicial, en una sola transacción. Valida teléfono
  único ("Ese teléfono ya está registrado") y contraseña mínima de 8 caracteres.
- **Scaffold:** proyecto Django 5.2 + DRF + SimpleJWT con arquitectura por capas
  (`view → serializer → service → model`), `User` custom por teléfono con
  suscripción por cuenta (multi-tenant), settings modular, logging con rotación y
  suite pytest con `factory-boy`.
