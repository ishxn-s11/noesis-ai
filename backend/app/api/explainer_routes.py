"""Explainer endpoints: the glossary of complex terms + term matching for findings.

GET  /glossary       — full curated glossary (definitions, formulas, references)
POST /explain        — locate glossary terms inside arbitrary text (agent
                       findings, report prose, paper abstracts) so the frontend
                       can highlight and explain every complex term inline.
Deterministic reference data; no LLM involved.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.auth.service import CurrentUser, get_current_user
from app.core.glossary import find_terms, glossary_payload

router = APIRouter(tags=["explainer"])


@router.get("/glossary", summary="Curated glossary of every complex term on the platform")
def glossary(user: CurrentUser = Depends(get_current_user)) -> dict:
    return glossary_payload()


class ExplainIn(BaseModel):
    text: str = Field(min_length=1, max_length=100_000)


@router.post("/explain", summary="Locate + explain glossary terms inside arbitrary text")
def explain(body: ExplainIn, user: CurrentUser = Depends(get_current_user)) -> dict:
    matches = find_terms(body.text)
    return {
        "n_chars": len(body.text),
        "n_matches": len(matches),
        "matches": matches,
        "categories": glossary_payload()["categories"],
    }
