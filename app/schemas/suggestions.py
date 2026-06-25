"""Suggestion chip schemas."""

from typing import Literal

from pydantic import BaseModel, Field


class SuggestionItem(BaseModel):
    kind: Literal["overview", "explain", "compare", "news", "ideas"]
    label: str
    message: str


class SuggestionsResponse(BaseModel):
    generated_at: str
    expires_at: str
    source: Literal["yahoo_finance", "fallback"]
    suggestions: list[SuggestionItem] = Field(min_length=3, max_length=12)
