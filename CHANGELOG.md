# Changelog — Itzaka (backend)

Todas las notas de cambios relevantes de la API. El formato sigue
[Keep a Changelog](https://keepachangelog.com/es-ES/) y versionado semántico.

## [Unreleased]

### Security
- **seguridad — TEC Permiso por defecto IsVerifiedUser**: `REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"]` pasa de `IsAuthenticated` a `common.permissions.IsVerifiedUser` (nuevo `src/common/permissions.py`: hereda de `IsAuthenticated` y exige `is_email_verified`; sin sesión sigue siendo 401 y sin verificar es 403 `{"detail": "Verifica tu correo para continuar.", "code": "email_not_verified"}`). Las vistas que declaraban `IsAuthenticated` a secas (31 de 32: catálogo, clientes, cotizaciones, proyectos, avances, evidencias, pagos, personal, planos, modelos, documentos, folios —también el `get_permissions` de `folio-settings/<tipo>/`—, equipo, organización, aceptación legal y `me/email`, `me/password`, `me/delete`) usan `IsVerifiedUser`, antes que `IsCompanyAdmin` donde lo llevan; sólo `GET /api/auth/me/` sigue con `IsAuthenticated` (la SPA lee `is_email_verified` para llevar a la pantalla del código; `PATCH me/` pide verificar). Las rutas públicas (código, reenvío, renovar, salir, CSRF) no cambian. Las cuentas que nacen de una invitación ya nacen verificadas: los colaboradores no quedan fuera. (SEC-02 · iteracion-26 #8)
- **seguridad — TEC Sesión en cookies con la SPA en itzaka.com y la API en api.itzaka.com**: Sin `DEBUG`, los valores por omisión son los de producción: `ALLOWED_HOSTS` = `api.itzaka.com` (más los hosts que Vercel da al despliegue; antes `*`), `CORS_ALLOWED_ORIGINS` y `CSRF_TRUSTED_ORIGINS` = `https://itzaka.com`, `CSRF_COOKIE_DOMAIN` = `.itzaka.com` (la SPA lee la cookie CSRF desde su dominio y la repite en `X-CSRFToken`) y `APP_BASE_URL` = `https://itzaka.com`; con `DEBUG`, los locales (`localhost`, `127.0.0.1`, `[::1]`, `http://localhost:5173`, sin `Domain`). develop los cambia por variables (`dev.itzaka.com`, `api-dev.itzaka.com`, `CSRF_COOKIE_NAME=csrftoken_dev`). Orígenes exactos, `CORS_ALLOW_CREDENTIALS` sigue encendido y las cookies JWT siguen sin `Domain`. El `User-Agent` del correo pasa a `+https://itzaka.com`. `src/core/.env.example` documenta cada variable por entorno. Prueba nueva `test_session_cookie_settings` (producción en un subproceso con `VERCEL=1`: cookies `Secure`, dominio, orígenes y hosts; en proceso: `itzaka_access` e `itzaka_refresh` `Secure`, `HttpOnly`, `Lax` y sin `Domain`, y la CSRF legible con `Domain=.itzaka.com`). (SEC-04, SEC-04.1, SEC-04.4 · iteracion-26 #9)
- **seguridad — TEC Intercambios de credenciales sin autenticar, solo JSON y cuerpos sin tokens**: `REST_FRAMEWORK["DEFAULT_PARSER_CLASSES"]` = `JSONParser`: un cuerpo `application/x-www-form-urlencoded` o multipart en una ruta que no es de subida responde 415 (un `<form>` de otro sitio ya no inicia una sesión ni escribe). Sólo las subidas leen multipart, declarado en la vista y sin `FormParser`: `PATCH /api/auth/organization/` (multipart + JSON), `POST /api/progresses/{id}/evidence/`, `POST /api/plans/photo-conversions/`, `POST /api/plan-assets/` y `POST /api/documents/send/`; corregir un avance (`PATCH /api/progresses/{id}/`) y `POST /api/plan-assets/missing/` leen JSON. Acceso, registro, código, reenvío y recuperación (`login/`, `register/`, `verify-otp/`, `resend-otp/`, `password-reset/`, `password-reset/confirm/`) declaran `authentication_classes = []`: una cookie de acceso de una sesión muerta ya no responde 401, ni una viva sin `X-CSRFToken` 403, y unas credenciales malas siguen siendo 401 con `WWW-Authenticate` (`common.authentication.CredentialExchangeMixin`; sin autenticadores DRF las volvía 403, que la SPA lee como «sin verificar»). `POST /api/auth/refresh/` sólo lee el refresh de su cookie (el del cuerpo se ignora: 401); su cuerpo nunca lleva tokens y un 401 borra las dos cookies. Pruebas nuevas en `apps/accounts/tests/test_credential_exchanges.py`: `test_login_rejects_form_encoded_body`, `test_no_route_reads_urlencoded_and_only_uploads_read_multipart`, `test_login_works_with_a_dead_access_cookie` (y los otros cinco intercambios), `test_refresh_answered_401_clears_both_cookies`, `test_allauth_html_urls_not_mounted` y `test_user_data_does_not_expose_sensitive_fields` (acceso, `me`, organización, equipo, invitaciones, registro, código; ninguna respuesta trae contraseñas, códigos, tokens ni `is_superuser`/`is_staff`). (SEC-04.2, SEC-04.3, SEC-04.5, CRD-02.1, CRD-02.2, MAN-06 · iteracion-26 #10)
- **seguridad — TEC Rotación y lista negra de tokens con limpieza programada**: `SIMPLE_JWT["CHECK_REVOKE_TOKEN"] = True`: cada token lleva la huella de la contraseña con la que nació y deja de servir en cuanto cambia. Cambiar la contraseña (`POST /api/auth/me/password/`) deja fuera al instante a las otras sesiones, también su access (antes vivía hasta vencer, media hora), y a quien la cambió le abre una sesión nueva; recuperarla o ponerla desde el admin también. `POST /api/auth/refresh/` revisa lo mismo (`SessionRefreshSerializer`): un refresh de antes del cambio, o de una cuenta borrada (antes un 500), responde 401 y borra las cookies. Los tokens emitidos antes de este cambio no traen la huella: se rechazan una vez y se vuelve a entrar. Nueva ruta `GET /api/cron/flush-expired-tokens/` (204) que corre `flushexpiredtokens`; la abre sólo `Authorization: Bearer <CRON_SECRET>` comparado en tiempo constante (`common/cron.py`): sin `CRON_SECRET`, sin la cabecera, con otro secreto o con una sesión de usuario responde 401 y no corre. `vercel.json` la programa con `crons` a diario (`0 9 * * *`, UTC); `CRON_SECRET` en `src/core/.env.example`. (CRD-02 · iteracion-26 #11)

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
