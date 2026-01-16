import os
import sys

# Add project root to sys.path for local imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.api import app


def handler(request):
    """Vercel serverless handler for assessment endpoints."""
    from mangum import Mangum

    asgi_handler = Mangum(app, lifespan="off")
    return asgi_handler(request, None)
