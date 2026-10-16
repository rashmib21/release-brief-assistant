from typing import Annotated

from pydantic import BaseModel, Field, field_validator

from .services.package import strip_control

# Limits keep one request from becoming a huge prompt or database row.
MAX_ITEM_TEXT = 2000
MAX_ITEMS_PER_SECTION = 50


# ---------- API input ----------
class ItemIn(BaseModel):
    id: str | None = Field(default=None, max_length=20)
    text: str = Field(default="", max_length=MAX_ITEM_TEXT)
    covers: list[str] = Field(default_factory=list, max_length=MAX_ITEMS_PER_SECTION * 3)


Items = Annotated[list[ItemIn], Field(default_factory=list, max_length=MAX_ITEMS_PER_SECTION)]


class PackageIn(BaseModel):
    features: Items
    bug_fixes: Items
    changed_behaviour: Items
    qa_summary: Items
    known_limitations: Items
    migration_notes: Items
    affected_user_groups: Items


class ReleaseCreate(BaseModel):
    name: str = Field(max_length=200)

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        v = " ".join(strip_control(v).split())
        if not v:
            raise ValueError("Release name cannot be blank.")
        return v


class VersionCreate(BaseModel):
    package: PackageIn


class CitationIn(BaseModel):
    id: str


class StatementPatch(BaseModel):
    edited_text: str | None = Field(default=None, max_length=2000)
    citations: list[str] | None = Field(default=None, max_length=50)
    status: str | None = None  # approved | rejected | draft


# ---------- LLM output shapes (all fields required: friendlier to Gemini's schema support) ----------
class ClassificationItem(BaseModel):
    item_id: str
    user_groups: list[str]
    impact: str  # high | medium | low
    reason: str


class ClassificationOutput(BaseModel):
    classifications: list[ClassificationItem]


class MissingInfo(BaseModel):
    topic: str
    why_it_matters: str
    related_ids: list[str]


class UnsupportedClaim(BaseModel):
    claim_item_id: str
    claim: str
    qa_ids: list[str]
    reason: str


class GapsOutput(BaseModel):
    missing_info: list[MissingInfo]
    unsupported_claims: list[UnsupportedClaim]


class StatementOut(BaseModel):
    audience: str  # technical | client
    section: str  # summary | risks
    text: str
    citations: list[str]


class StatementsOutput(BaseModel):
    statements: list[StatementOut]
