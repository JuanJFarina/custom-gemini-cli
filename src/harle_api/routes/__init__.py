from harle_api.routes.browser import router as browser_router
from harle_api.routes.health import router as health_router
from harle_api.routes.telegram import router as telegram_router

__all__ = ["browser_router", "health_router", "telegram_router"]
