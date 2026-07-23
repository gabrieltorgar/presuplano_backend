# presuplano — Backend

API del cotizador para arquitectos **presuplano**. Permite registrar tarifas
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
- `dev` → integración y trabajo diario (todas las US se desarrollan aquí).

## Desarrollo

El código se construye por *user story* siguiendo el flujo de entrega del
equipo (Producto → Desarrollo TDD → Testing → Deploy). El backlog formal, la
fuente única de alcance, vive en el repositorio del frontend
(`docs/4.0_Backlog_Producto.json`).

> El scaffold del proyecto Django se genera al iniciar el desarrollo, tras la
> aprobación del backlog (GATE 1).
