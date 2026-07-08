"""CScode Server Routes — Route handler modules split by domain.

Each module registers its handlers on an APIRouter and exports it.
The main app.py includes these routers via app.include_router().
"""

from cscode.server.routes.sessions import router as sessions_router

__all__ = ["sessions_router"]
