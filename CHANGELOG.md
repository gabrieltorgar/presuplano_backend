# Changelog — presuplano (backend)

Todas las notas de cambios relevantes de la API. El formato sigue
[Keep a Changelog](https://keepachangelog.com/es-ES/) y versionado semántico.

## [Unreleased]

### Added
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
