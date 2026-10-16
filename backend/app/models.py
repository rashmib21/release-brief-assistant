from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Release(Base):
    __tablename__ = "releases"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    versions: Mapped[list["ReleaseVersion"]] = relationship(
        back_populates="release", order_by="ReleaseVersion.version_no", cascade="all, delete-orphan"
    )


class ReleaseVersion(Base):
    __tablename__ = "release_versions"
    __table_args__ = (UniqueConstraint("release_id", "version_no"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    release_id: Mapped[int] = mapped_column(ForeignKey("releases.id"))
    version_no: Mapped[int] = mapped_column(Integer)
    package_json: Mapped[dict] = mapped_column(JSON)
    item_hashes_json: Mapped[dict] = mapped_column(JSON)
    # draft -> in_review -> brief_generated (this is NOT a release approval)
    review_state: Mapped[str] = mapped_column(String(30), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    release: Mapped[Release] = relationship(back_populates="versions")
    analysis: Mapped["Analysis | None"] = relationship(
        back_populates="version", uselist=False, cascade="all, delete-orphan"
    )
    statements: Mapped[list["Statement"]] = relationship(
        back_populates="version", order_by="Statement.id", cascade="all, delete-orphan"
    )
    final_brief: Mapped["FinalBrief | None"] = relationship(
        back_populates="version", uselist=False, cascade="all, delete-orphan"
    )


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("release_versions.id"), unique=True)
    classifications_json: Mapped[list] = mapped_column(JSON)
    missing_info_json: Mapped[list] = mapped_column(JSON)
    unsupported_claims_json: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    version: Mapped[ReleaseVersion] = relationship(back_populates="analysis")


class Statement(Base):
    __tablename__ = "statements"

    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("release_versions.id"))
    audience: Mapped[str] = mapped_column(String(20))  # technical | client
    section: Mapped[str] = mapped_column(String(20))  # summary | risks
    text: Mapped[str] = mapped_column(Text)
    edited_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    citations_json: Mapped[list] = mapped_column(JSON)  # [{"id": "F1", "hash": "..."}]
    flags_json: Mapped[list] = mapped_column(JSON, default=list)  # [{"code","message"}]
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft|approved|rejected|stale
    stale_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    carried_from_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    version: Mapped[ReleaseVersion] = relationship(back_populates="statements")


class AiRun(Base):
    __tablename__ = "ai_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int | None] = mapped_column(ForeignKey("release_versions.id"), nullable=True)
    request_id: Mapped[str] = mapped_column(String(64), default="-")
    step: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(80))
    prompt_hash: Mapped[str] = mapped_column(String(64))
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20))  # ok | error | guardrail_failed
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FinalBrief(Base):
    __tablename__ = "final_briefs"

    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("release_versions.id"), unique=True)
    content_md: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    version: Mapped[ReleaseVersion] = relationship(back_populates="final_brief")
