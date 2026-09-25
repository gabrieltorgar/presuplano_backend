# Deploy — presuplano backend (Vercel + Neon)

El backend se despliega en **Vercel** como **función serverless de Python**
(soporte nativo de Django) y usa **Neon Postgres** como base de datos. Config
incluida:

- `wsgi.py` (raíz del repo) — entrypoint WSGI: pone `src/` en el path y expone
  `application`. Está en la raíz porque es desde ahí desde donde Vercel importa.
- `pyproject.toml` — `[tool.vercel] entrypoint = "wsgi:application"`, que le dice
  a Vercel qué instancia servir. Vercel la usa para **todas** las rutas,
  conservando la ruta que pidió el cliente.
- `vercel.json` — solo el `buildCommand`, que corre **migraciones** y
  **collectstatic**:
  ```json
  {
    "buildCommand": "uv sync && uv run python src/manage.py migrate && uv run python src/manage.py collectstatic --noinput"
  }
  ```

> **Nada de rewrites generales.** Un `{"source": "/(.*)", "destination": "/api/index"}`
> funcionó hasta que Vercel pasó a entregar a la aplicación la ruta **ya
> reescrita**: desde entonces Django recibía siempre `/api/index`, no encontraba
> ninguna URL y **toda la API respondía 404**. Lo cubre
> `src/api/tests/test_deploy_entrypoint.py`.
- `requirements.txt` — dependencias de runtime que Vercel instala para la función
  (incluye `psycopg-binary` con libpq y `whitenoise`).
- **WhiteNoise** sirve los estáticos del **admin/DRF** desde la función (por eso
  `/admin/` se ve con estilos, sin servidor de estáticos aparte).
- En Vercel, `ALLOWED_HOSTS` y `CSRF_TRUSTED_ORIGINS` se completan **solos** con
  los hostnames del deployment (`VERCEL_URL`, `VERCEL_BRANCH_URL`,
  `VERCEL_PROJECT_PRODUCTION_URL`), así el admin funciona en preview y producción.

## Pasos para poner en línea

1. **Neon:** crear proyecto + BD; copiar el `DATABASE_URL` (`postgres://…`).
2. **Vercel:** importar el repo `presuplano_backend`. Framework: *Other*
   (Vercel detecta `api/*.py` como función Python).
3. **Variables de entorno en Vercel** (Production y Preview):

| Variable | Obligatoria | Valor |
|---|---|---|
| `DATABASE_URL` | **Sí** | Neon Postgres — sin ella el build de `migrate` falla y no hay tablas |
| `SECRET_KEY` | **Sí** | aleatorio ≥ 32 caracteres |
| `CORS_ALLOWED_ORIGINS` | Sí | `https://tu-frontend.vercel.app` |
| `OTP_UNIVERSAL_CODE` | opcional | MVP; def. `123456` (ver *Correo saliente*) |
| `RESEND_API_KEY` | opcional | sin ella no sale correo: ni códigos ni documentos |
| `DEBUG` | opcional | en Vercel es `False` por defecto (no definir en prod) |
| `ALLOWED_HOSTS` | opcional | los hosts de Vercel se añaden solos; agrega tu dominio propio si lo usas |

4. **Deploy:** cada push a `main` → producción; a otras ramas → preview. El
   `buildCommand` aplica migraciones y recolecta estáticos automáticamente.
5. **Crear superusuario** (una vez, para entrar al admin): desde tu máquina con el
   `DATABASE_URL` de Neon apuntando a producción:
   ```bash
   DATABASE_URL="postgres://…neon…" uv run python manage.py createsuperuser
   ```
   Luego entra a `https://tu-backend.vercel.app/admin/`.

## Media (evidencias fotográficas) — Cloudflare R2

El filesystem de Vercel es **de solo lectura** en runtime, así que la media
(evidencias de avance, US-16) se guarda en **Cloudflare R2** (S3-compatible) vía
`django-storages`. Ya está integrado (`core/settings_storages.py`): R2 se activa
**solo** con las credenciales presentes; sin ellas, dev/tests usan filesystem
local sin credenciales. La media se aísla por cuenta: `evidence/<cuenta>/…`.

Pasos para activarlo:

1. En **Cloudflare R2**, crear un bucket (p. ej. `presuplano-media`) y un token
   de API S3 (Access Key ID + Secret). Habilitar acceso público (subdominio
   `*.r2.dev`) o un dominio propio para servir las imágenes.
2. Cargar en Vercel (Production + Preview):

| Variable | Valor |
|---|---|
| `R2_ACCOUNT_ID` | ID de cuenta de Cloudflare |
| `R2_ACCESS_KEY_ID` | Access Key del token R2 |
| `R2_SECRET_ACCESS_KEY` | Secret del token R2 |
| `R2_BUCKET_NAME` | `presuplano-media` |
| `R2_PUBLIC_URL` | host público (`https://<hash>.r2.dev` o tu dominio) |
| `R2_ENDPOINT_URL` | *(opcional)* def. `https://<account_id>.r2.cloudflarestorage.com` |

Con esas variables, `default_storage` apunta a R2 y las evidencias persisten
entre invocaciones. Los estáticos del admin/DRF los sigue sirviendo WhiteNoise
(no van a R2).

## Correo saliente — Resend

El correo sale por la **API HTTP de Resend**, no por el mailer de Django: en
serverless no hay conexión SMTP que sostener y una llamada HTTPS es lo único
que la plataforma siempre permite. Vive en `common/mail.py` y nunca lanza: un
correo que no sale se anota y la pantalla sigue.

| Variable | Obligatoria | Valor |
|---|---|---|
| `RESEND_API_KEY` | para mandar correo | la llave `re_…` de Resend |
| `RESEND_FROM` | **sí, en cuanto haya llave** | remitente de un dominio verificado, p. ej. `presuplano <no-reply@tudominio.com>` |
| `APP_BASE_URL` | opcional | a dónde llevan los enlaces; def. `https://presuplano.vercel.app` |
| `DOCUMENT_EMAIL_MAX_BYTES` | opcional | tope del adjunto; def. 8 MB |

El remitente por omisión (`onboarding@resend.dev`) es el de pruebas de Resend:
funciona sin configurar nada, pero **sólo entrega al correo del dueño de la
cuenta de Resend**. A un cliente nunca le llega, así que en cuanto la llave
esté puesta hay que fijar `RESEND_FROM` a una dirección de un dominio
verificado; mientras no lo esté, cada envío lo deja anotado en el log.

Qué cambia al configurarla:

- **El código de verificación deja de ser universal** para las cuentas con
  correo: cada una recibe el suyo, de seis cifras, guardado cifrado y con
  vencimiento (`OTP_TTL_MINUTES`). Las cuentas que sólo tienen teléfono siguen
  con `OTP_UNIVERSAL_CODE` mientras no haya SMS por donde mandarles el suyo.
- **Se habilita el envío de documentos** (`POST /api/documents/send/`):
  cotización, estatus de proyecto, comprobante de pago y de cobro. Sin llave,
  ese endpoint responde 400 diciendo que no está configurado, en vez de fingir
  que envió.

## Base de datos (Neon)

- Rama primaria de Neon → producción; ramas efímeras → previews.
- Las migraciones se aplican en el `buildCommand` de cada deploy.

> Crear cuentas, cargar credenciales y autorizar integraciones son acciones del
> usuario. Este documento indica los pasos; no ejecuta el despliegue.
