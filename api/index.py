"""
Vercel Python runtime entrypoint.

Vercel's @vercel/python builder looks for a WSGI/ASGI `app` (or `handler`)
callable in this file. We simply expose the standard Django WSGI application.
Any request to the deployment gets routed here by vercel.json's rewrite rule.
"""
import os
import sys
from pathlib import Path

# Make the project root importable (this file lives in /api)
sys.path.append(str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.core.wsgi import get_wsgi_application  # noqa: E402

app = get_wsgi_application()
