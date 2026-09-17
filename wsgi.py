"""WSGI entrypoint for Vercel.

Vercel's Django support imports the WSGI instance named in
``[tool.vercel] entrypoint`` of ``pyproject.toml`` and serves every request
with it, keeping the path the browser asked for. This module exists at the
repository root because that is where Vercel imports from, while the project
itself lives under ``src/`` — so it puts ``src`` on the path first, exactly as
``manage.py`` does for local commands.

There is deliberately no catch-all rewrite in ``vercel.json``: an internal
rewrite now hands the app the REWRITTEN path, so every request reached Django
as ``/api/index`` and nothing matched — the whole API answered 404.
"""

import os
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

from django.core.wsgi import get_wsgi_application  # noqa: E402

application = get_wsgi_application()
# Vercel serves whichever of these it finds; expose both names.
app = application
