"""Typed records the agent writes into the owner workspace and the catalog holds. Field names follow spec §6."""
from typing import Annotated, Literal

from pydantic import BaseModel, Field

# Ids that end up in file names. Catalog ids are slugs (catalog extract.slug), so no dots, slashes or "..".
ID_PATTERN = r"^[a-z0-9][a-z0-9-]{0,63}$"
APPROVAL_ID_PATTERN = r"^ap_[A-Za-z0-9]{1,32}$"
ToolId = Annotated[str, Field(pattern=ID_PATTERN)]
ApprovalId = Annotated[str, Field(pattern=APPROVAL_ID_PATTERN)]

BusinessType = Literal["restaurant", "coffee_shop", "hvac", "landscaping", "salon", "other"]
NeedId = Literal[
    "missed-calls", "reviews", "social-posts", "booking", "website-chat",
    "books", "marketing-msgs", "quotes", "menu-inventory",
]
Integration = Literal[
    "square", "toast", "clover", "google_business", "quickbooks", "facebook",
    "instagram", "yelp", "gmail", "outlook", "website", "sms",
]
Badge = Literal["verified", "caution", "unknown"]


class Price(BaseModel):
    free_plan: bool
    from_usd_month: float | None = None
    pricing_url: str | None = None
    notes: str = ""


class ToolSetup(BaseModel):
    minutes: int
    difficulty: Literal["easy", "medium", "hard"]
    agent_setup: bool = False
    playbook: str | None = None


class Signal(BaseModel):
    points: int
    max: int
    value: str
    evidence_url: str | None = None


class Trust(BaseModel):
    score: int = Field(ge=0, le=100)
    badge: Badge
    signals: dict[str, Signal] = {}


class SimTest(BaseModel):
    score: int = Field(ge=0, le=10)
    persona: str
    task: str
    notes: str
    label: Literal["simulated"] = "simulated"


class Tool(BaseModel):
    id: str
    name: str
    vendor: str
    url: str
    need_ids: list[NeedId] = Field(min_length=1)
    business_types: list[BusinessType] = Field(min_length=1)
    what_it_does: str
    price: Price
    setup: ToolSetup
    integrations: list[Integration] = []
    trust: Trust
    sim_test: SimTest | None = None
    sources: list[str] = []
    status: Literal["approved", "pending", "rejected"] = "pending"
    reviewed_by: str | None = None
    reviewed_at: str | None = None


class Profile(BaseModel):
    name: str
    business_type: BusinessType
    city: str
    state: str
    size: str
    website: str | None = None
    uses: list[Integration] = []
    pains: list[str] = []
    summary: str


class NeedItem(BaseModel):
    need_id: NeedId
    title: str
    why: str
    est_hours_saved_week: float


class Needs(BaseModel):
    items: list[NeedItem] = Field(min_length=3, max_length=5)


class CompareOption(BaseModel):
    tool_id: ToolId
    fit_sentence: str
    works_with: list[Integration] = []


class Compare(BaseModel):
    need_id: NeedId
    options: list[CompareOption] = Field(min_length=1, max_length=3)
    recommended_tool_id: ToolId


class Preview(BaseModel):
    tool_id: ToolId
    prompt: str
    status: Literal["completed", "failed", "capped"]
    video_file: str | None = None
    cost_usd: float = 0.0


class SetupRecord(BaseModel):
    tool_id: ToolId
    status: Literal["planned", "awaiting_approval", "running", "needs_owner", "done", "failed"]
    approval_id: str | None = None
    run_id: str | None = None
    streaming_url: str | None = None
    inbox: str | None = None
    login_url: str | None = None
    username: str | None = None
    password: str | None = None
    configured: list[str] = []
    next_steps: list[str] = []
    handoff_reason: str | None = None


class Approval(BaseModel):
    id: ApprovalId
    tool_id: ToolId
    summary: str
    status: Literal["pending", "approved", "rejected"] = "pending"
    created_at: str
    decided_at: str | None = None


KINDS: dict[str, type[BaseModel]] = {
    "profile": Profile,
    "needs": Needs,
    "compare": Compare,
    "preview": Preview,
    "setup": SetupRecord,
    "approval": Approval,
}
