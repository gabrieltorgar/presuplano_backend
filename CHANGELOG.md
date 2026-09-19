# Changelog — presuplano (backend)

Todas las notas de cambios relevantes de la API. El formato sigue
[Keep a Changelog](https://keepachangelog.com/es-ES/) y versionado semántico.

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
