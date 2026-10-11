"""What the harness agent writes after reading the evidence. The tools never fill these in themselves.

identity.json: what the product really is.  pmf.json: which niche has pull, with evidence.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError, field_validator

HEX = r"^#[0-9A-Fa-f]{6}$"


class Claim(BaseModel):
    claim: str
    evidence_url: str = Field(description="page or post that supports it; must come from evidence.json or market.json")


class Segment(BaseModel):
    name: str
    pain: str
    why_they_care: str


class Voice(BaseModel):
    adjectives: list[str] = Field(min_length=3, max_length=3)
    do: list[str] = Field(min_length=1)
    dont: list[str] = Field(min_length=1)


class Visual(BaseModel):
    palette: list[str] = Field(min_length=2, max_length=6, description="hex colors taken from evidence.json")
    type: list[str] = Field(min_length=1, description="font families from evidence.json")
    imagery: str

    @field_validator("palette")
    @classmethod
    def _hex(cls, v: list[str]) -> list[str]:
        import re

        bad = [c for c in v if not re.match(HEX, c)]
        if bad:
            raise ValueError(f"not #RRGGBB: {bad}")
        return v


class Niche(BaseModel):
    name: str
    why: str
    search_terms: list[str] = Field(min_length=1, max_length=4)


class Identity(BaseModel):
    product: str
    one_liner: str = Field(max_length=120)
    what_it_really_is: str = Field(description="2-3 plain sentences, no marketing language")
    category: str
    audience: list[Segment] = Field(min_length=1, max_length=4)
    value_props: list[Claim] = Field(min_length=2, max_length=5)
    proof: list[Claim] = Field(default_factory=list)
    voice: Voice
    visual: Visual
    keywords: list[str] = Field(min_length=3, max_length=12)
    competitors: list[str] = Field(default_factory=list)
    niches: list[Niche] = Field(min_length=2, max_length=5, description="candidate niches for `identity market`")


class NicheScore(BaseModel):
    name: str
    demand: int = Field(ge=1, le=5, description="how much people are talking about it now")
    urgency: int = Field(ge=1, le=5, description="how painful the problem is")
    competition: int = Field(ge=1, le=5, description="5 = crowded")
    fit: int = Field(ge=1, le=5, description="how well the product solves it today")
    signals: list[Claim] = Field(min_length=2)
    pains: list[str] = Field(min_length=1)


class PMF(BaseModel):
    niches: list[NicheScore] = Field(min_length=1)
    chosen_niche: str = Field(description="handed to the research stage as its niche")
    hypothesis: str = Field(description="For <segment> who <pain>, <product> <does what>, unlike <alternative>.")
    risks: list[str] = Field(min_length=1)
    next_tests: list[str] = Field(min_length=1)

    @field_validator("chosen_niche")
    @classmethod
    def _chosen_is_scored(cls, v: str, info) -> str:
        names = [n.name for n in info.data.get("niches", [])]
        if names and v not in names:
            raise ValueError(f"chosen_niche must be one of the scored niches {names}")
        return v


MODELS = {"identity": Identity, "pmf": PMF}


def validate(kind: str, path: Path) -> list[str]:
    """Return a list of problems; empty means valid."""
    try:
        MODELS[kind].model_validate(json.loads(path.read_text()))
        return []
    except FileNotFoundError:
        return [f"{path} does not exist"]
    except json.JSONDecodeError as e:
        return [f"not valid JSON: {e}"]
    except ValidationError as e:
        return [f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}" for err in e.errors()]
