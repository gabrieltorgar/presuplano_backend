# CUOTREKA — Backend

> Del plano a la obra, todo conectado.

API del cotizador para arquitectos **CUOTREKA**. Permite registrar tarifas
(precio por m², metro lineal, piso/muro, etc.), clientes, cotizaciones,
avances de proyecto con evidencia fotográfica, y pagos (totales o parciales)
con su comprobante, hasta el cierre del proyecto con documento resumen.

## Stack

- **Django 5.2 + Django REST Framework**
- **PostgreSQL** (Neon en la nube, por entorno)
- Gestión de dependencias con **uv** (`pyproject.toml`)
- Lint/format con **ruff**
- Testing con **pytest** (TDD estricto: RED → GREEN por user story)

## Estructura de ramas

- `main` → producción.
- `develop` → integración (protegida: sólo pull requests con pruebas en verde y
  cobertura ≥ 90 %).
- `iteracion-N` → rama de trabajo de cada iteración, que entra a `develop` por
  pull request.

## Desarrollo

El código se construye por *user story* siguiendo el flujo de entrega del
equipo (Producto → Desarrollo TDD → Testing → Deploy). El backlog formal, la
fuente única de alcance, vive en la memoria del proyecto, el repositorio
[`cuotreka_docs`](https://github.com/gabrieltorgar/cuotreka_docs)
(`producto/4.0_Backlog_Producto.json`; sitio en https://cuotreka-docs.vercel.app), junto con la guía de despliegue que antes
era `DEPLOY.md` (`legado/backend/DEPLOY.md`). Variables de entorno: ver
`src/core/.env.example`.

> El scaffold del proyecto Django se genera al iniciar el desarrollo, tras la
> aprobación del backlog (GATE 1).
