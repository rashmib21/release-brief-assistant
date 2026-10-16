import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_by_id, get_db
from ..logging_config import log_event
from ..models import Statement
from ..schemas import StatementPatch
from ..services.guardrails import deterministic_flags
from ..services.package import strip_control
from ..services.serialize import statement_to_dict

router = APIRouter(prefix="/api/statements", tags=["statements"])
logger = logging.getLogger(__name__)

USER_SETTABLE = {"approved", "rejected", "draft"}


@router.patch("/{statement_id}")
def patch_statement(statement_id: int, body: StatementPatch, db: Session = Depends(get_db)):
    """The only place a statement can become approved or rejected: a deliberate user action."""
    s = get_by_id(db, Statement, statement_id)
    if s is None:
        raise HTTPException(404, "Statement not found.")
    version = s.version
    if version.review_state == "brief_generated":
        raise HTTPException(409, "The final brief was already generated, so this version is locked.")
    hashes = version.item_hashes_json

    if body.status is not None and body.status not in USER_SETTABLE:
        raise HTTPException(422, "status must be approved, rejected or draft.")

    if body.edited_text is not None:
        if not strip_control(body.edited_text).strip():
            raise HTTPException(422, "Edited text cannot be empty. Reject the statement instead.")
        s.edited_text = strip_control(body.edited_text).strip()
        if s.status == "approved":
            s.status = "draft"  # edited content needs a fresh approval

    if body.citations is not None:
        ids = list(dict.fromkeys(c.strip().upper() for c in body.citations if c.strip()))
        if not ids:
            raise HTTPException(422, "A statement needs at least one citation.")
        unknown = [c for c in ids if c not in hashes]
        if unknown:
            raise HTTPException(422, f"Unknown item IDs: {', '.join(unknown)}.")
        s.citations_json = [{"id": c, "hash": hashes[c]} for c in ids]
        s.flags_json = deterministic_flags(ids)
        if s.status in ("stale", "approved"):
            s.status, s.stale_reason = "draft", None

    if body.status is not None:
        if body.status == "approved":
            missing = [c["id"] for c in s.citations_json if c["id"] not in hashes]
            if missing:
                raise HTTPException(422, f"Cited item(s) {', '.join(missing)} no longer exist. Edit the citations or reject the statement.")
            # Approving a stale statement means the user re-checked it against the new evidence.
            s.citations_json = [{"id": c["id"], "hash": hashes[c["id"]]} for c in s.citations_json]
            s.stale_reason = None
        s.status = body.status

    db.commit()
    log_event(logger, "statement_updated", statement_id=s.id, version_id=version.id, status=s.status)
    return statement_to_dict(s, version.package_json)
