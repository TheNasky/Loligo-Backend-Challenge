"""Dynamic welcome suggestions API."""

from fastapi import APIRouter, Query

from app.schemas.suggestions import SuggestionsResponse
from app.services.suggestions import build_suggestions

router = APIRouter(prefix="/suggestions", tags=["suggestions"])


@router.get("", response_model=SuggestionsResponse)
def get_suggestions(lang: str = Query(default="es", pattern="^(es|en)$")) -> SuggestionsResponse:
    """Hourly-cached chip prompts derived from Yahoo Finance snapshot scan."""
    payload = build_suggestions(lang)
    return SuggestionsResponse(**payload)
