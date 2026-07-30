"""CScode Server Routes — Route handler modules split by domain.

Each module registers its handlers on an APIRouter and exports it.
The main app.py includes these routers via app.include_router().
"""

from cscode.server.routes.config import router as config_router
from cscode.server.routes.permissions import router as permissions_router
from cscode.server.routes.sessions import router as sessions_router
from cscode.server.routes.tools import router as tools_router

__all__ = ["config_router", "permissions_router", "sessions_router", "tools_router"]
