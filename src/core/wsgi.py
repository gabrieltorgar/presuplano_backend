"""WSGI config for presuplano backend."""

import os
import sys
from pathlib import Path

src_path = Path(__file__).resolve().parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

from django.core.wsgi import get_wsgi_application  # noqa: E402

application = get_wsgi_application()
app = application
