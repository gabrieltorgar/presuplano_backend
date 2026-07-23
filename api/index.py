"""Vercel serverless entrypoint for the Django WSGI application.

Vercel's ``@vercel/python`` builder imports this module and serves the
module-level ``app`` callable. The project uses a ``src/`` layout, so we put
``src`` on the import path before building the WSGI application, mirroring what
``manage.py`` does for local commands.
"""
import os
import sys
from pathlib import Path

# Project uses a src/ layout: make ``core``, ``apps`` and ``common`` importable.
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

from django.core.wsgi import get_wsgi_application  # noqa: E402

# Vercel serves whichever of these it finds; expose both names.
app = get_wsgi_application()
application = app
