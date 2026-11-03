"""Catálogo público de trabalho, sem contratos, preços ou dados de clientes."""
from fastapi import APIRouter, Response
from app.modules.commercial.catalog import CATALOG_VERSION, CATALOG_PUBLISHED, FEATURES, PLANS

router = APIRouter(prefix="/catalog", tags=["Catálogo do produto"])


@router.get("/plans")
async def plans(response: Response):
    response.headers["Cache-Control"] = "no-store"
    return {
        "version": CATALOG_VERSION, "segment": "BUSINESS", "published": CATALOG_PUBLISHED,
        "checkout_available": False,
        "plans": [{"key": plan.key.value, "companies_limit": plan.companies, "users_limit": plan.users,
                   "features": sorted(feature.value for feature in plan.features)} for plan in PLANS.values()],
        "available_features": sorted(key.value for key, value in FEATURES.items() if value.available),
    }
