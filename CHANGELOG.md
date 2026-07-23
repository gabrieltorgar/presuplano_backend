# Changelog — presuplano (backend)

Todas las notas de cambios relevantes de la API. El formato sigue
[Keep a Changelog](https://keepachangelog.com/es-ES/) y versionado semántico.

## [Unreleased]

### Added
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
