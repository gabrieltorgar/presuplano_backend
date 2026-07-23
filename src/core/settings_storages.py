"""Media storage backend: Cloudflare R2 (S3-compatible) in production, local
filesystem in development.

Imported by ``settings.py`` after the ``.env`` is read (DRY). Owns ``STORAGES``.
On Vercel the filesystem is read-only and ephemeral, so uploaded media
(``ImageField`` — e.g. progress evidence) must live in an external, persistent
store — Cloudflare R2, reached through ``django-storages``' S3 backend.

R2 is enabled by ``USE_R2`` (on by default when credentials are present); otherwise
media falls back to Django's ``FileSystemStorage`` so local runs and tests need no
cloud credentials. Static files keep Django's storage — WhiteNoise serves them via
finders (see ``core/env.py``); **only media goes to R2**.
"""

import environ

env = environ.Env()

# --- Cloudflare R2 credentials / configuration ---
R2_ACCOUNT_ID = env.str("R2_ACCOUNT_ID", default="")
R2_ACCESS_KEY_ID = env.str("R2_ACCESS_KEY_ID", default="")
R2_SECRET_ACCESS_KEY = env.str("R2_SECRET_ACCESS_KEY", default="")
R2_BUCKET_NAME = env.str("R2_BUCKET_NAME", default="")
# Account-scoped S3 endpoint; derived from the account id when not given.
R2_ENDPOINT_URL = env.str(
    "R2_ENDPOINT_URL",
    default=(
        f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com" if R2_ACCOUNT_ID else ""
    ),
)
# Public host that serves the objects (an `r2.dev` subdomain or a custom domain).
# Host only; a full URL is normalized to its host below.
R2_PUBLIC_URL = env.str("R2_PUBLIC_URL", default="")

# Enable R2 explicitly with USE_R2, or implicitly when credentials are present.
_r2_configured = bool(
    R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY and R2_BUCKET_NAME and R2_ENDPOINT_URL
)
USE_R2 = env.bool("USE_R2", default=_r2_configured)

# Default (media) storage is local unless R2 is enabled below. Static files keep
# Django's storage; WhiteNoise serves them via finders.
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

if USE_R2:
    # Host without scheme or trailing slash, as django-storages expects.
    _custom_domain = R2_PUBLIC_URL.split("://", 1)[-1].rstrip("/") or None
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": R2_BUCKET_NAME,
            "endpoint_url": R2_ENDPOINT_URL,
            "access_key": R2_ACCESS_KEY_ID,
            "secret_key": R2_SECRET_ACCESS_KEY,
            # R2 ignores regions but boto3 still requires a value.
            "region_name": "auto",
            "signature_version": "s3v4",
            "addressing_style": "virtual",
            # R2 does not support ACLs; sending one breaks the upload.
            "default_acl": None,
            # Never silently overwrite an object with the same name.
            "file_overwrite": False,
            # Publicly readable media: clean URLs, no signed querystrings.
            "querystring_auth": False,
            # Serve objects from the public host instead of the S3 endpoint.
            "custom_domain": _custom_domain,
        },
    }
