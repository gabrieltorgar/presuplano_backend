# Changelog — presuplano (backend)

Todas las notas de cambios relevantes de la API. El formato sigue
[Keep a Changelog](https://keepachangelog.com/es-ES/) y versionado semántico.

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
