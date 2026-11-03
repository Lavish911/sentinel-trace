from fastapi import APIRouter
from backend.app.api.v1.endpoints import health, dashboard, claims, network, investigations

api_router = APIRouter()
api_router.include_router(health.router, tags=["system"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(claims.router, prefix="/claims", tags=["claims"])
api_router.include_router(network.router, prefix="/network", tags=["network"])
api_router.include_router(investigations.router, prefix="/investigations", tags=["investigations"])
