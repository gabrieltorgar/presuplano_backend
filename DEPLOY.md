# Deploy — presuplano backend

La base de datos compartida (frontend + backend) es **Neon Postgres**. El
`DATABASE_URL` se configura por entorno en el host y **nunca** se commitea.

## Base de datos (Neon)

1. Crear un proyecto en [Neon](https://neon.tech) y una base `presuplano`.
2. Rama primaria → producción; ramas de Neon efímeras → previews.
3. Copiar la cadena de conexión (`postgres://…`) como `DATABASE_URL` en el host.

## Host del backend (Django/DRF)

Vercel es JS-first; Django corre allí solo como *Serverless Functions* (con
cold starts y un adaptador WSGI/ASGI). Dos caminos:

- **Recomendado:** hospedar la API en una plataforma Python (Railway, Render,
  Fly.io o un contenedor) y dejar solo el frontend en Vercel. Neon es la
  Postgres compartida.
- **Vercel Functions:** empaquetar `core.wsgi:application` como función Python
  y servir estáticos con WhiteNoise/S3. Válido para tráfico bajo; vigilar cold
  starts.

Registrar el host elegido aquí una vez decidido.

## Variables de entorno (producción)

| Variable | Ejemplo | Notas |
|---|---|---|
| `DATABASE_URL` | `postgres://…` | Neon (por entorno) |
| `SECRET_KEY` | (aleatorio ≥ 32) | nunca commitear |
| `DEBUG` | `False` | producción |
| `ALLOWED_HOSTS` | `api.midominio.com` | host público |
| `CORS_ALLOWED_ORIGINS` | `https://midominio.com` | origen del frontend |
| `OTP_UNIVERSAL_CODE` | `123456` | MVP; reemplazar por SMS real |

## Pasos por despliegue

```bash
uv run pytest --cov=src --cov-fail-under=80   # CI: no desplegar en rojo
uv run python manage.py migrate               # release step contra el DATABASE_URL destino
uv run python manage.py collectstatic --noinput
```

> Crear cuentas, cargar credenciales y autorizar OAuth son acciones del usuario.
> Este documento indica los pasos; no ejecuta el despliegue.
