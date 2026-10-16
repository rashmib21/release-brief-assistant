import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_by_id, get_db
from ..llm.client import LLMError, get_llm_client
from ..logging_config import log_event
from ..models import FinalBrief, ReleaseVersion
from ..schemas import PackageIn
from ..services.ai_workflow import AnalysisError, run_analysis
from ..services.brief import blocking_statements, build_brief
from ..services.package import compute_hashes, normalize_package
from ..services.ratelimit import limit_analyze
from ..services.serialize import version_detail
from ..services.validation import validate_package

router = APIRouter(prefix="/api/versions", tags=["versions"])
logger = logging.getLogger(__name__)

STATUS_FOR_KIND = {"rate_limit": 429, "timeout": 504, "not_configured": 503, "unavailable": 503}


def get_version(db: Session, version_id: int) -> ReleaseVersion:
    version = get_by_id(db, ReleaseVersion, version_id)
    if version is None:
        raise HTTPException(404, "Version not found.")
    return version


def ensure_unlocked(version: ReleaseVersion) -> None:
    if version.review_state == "brief_generated":
        raise HTTPException(409, "The final brief was already generated, so this version is locked. Save a new version to make changes.")


@router.get("/{version_id}")
def get_version_detail(version_id: int, db: Session = Depends(get_db)):
    version = get_version(db, version_id)
    return version_detail(version, version.release)


@router.put("/{version_id}/package")
def replace_package(version_id: int, package: PackageIn, db: Session = Depends(get_db)):
    """Fix typos before any analysis exists. After that, a package change must be a new version."""
    version = get_version(db, version_id)
    if version.analysis is not None or version.statements:
        raise HTTPException(409, "This version already has AI output. Save a new version instead of editing it.")
    version.package_json = normalize_package(package.model_dump())
    version.item_hashes_json = compute_hashes(version.package_json)
    db.commit()
    return version_detail(version, version.release)


@router.post("/{version_id}/validate")
def validate(version_id: int, db: Session = Depends(get_db)):
    return validate_package(get_version(db, version_id).package_json)


@router.post("/{version_id}/analyze", dependencies=[Depends(limit_analyze)])
def analyze(version_id: int, force: bool = False, db: Session = Depends(get_db)):
    version = get_version(db, version_id)
    ensure_unlocked(version)

    result = validate_package(version.package_json)
    if not result["valid"]:
        raise HTTPException(422, detail={"message": "The release package has missing or invalid sections.", "errors": result["errors"]})

    if any(s.status == "approved" for s in version.statements) and not force:
        raise HTTPException(409, detail={"message": "Re-running the analysis replaces all statements, including approved ones.", "needs_force": True})

    try:
        llm = get_llm_client()
        run_analysis(db, version, llm)
    except LLMError as exc:  # raised when the client cannot be created (no API key)
        raise HTTPException(STATUS_FOR_KIND.get(exc.kind, 502), detail={"message": str(exc), "kind": exc.kind}) from exc
    except AnalysisError as exc:
        db.rollback()
        log_event(logger, "analysis_failed", level=logging.ERROR, version_id=version.id, step=exc.step, kind=exc.kind)
        raise HTTPException(
            STATUS_FOR_KIND.get(exc.kind, 502),
            detail={"message": f"AI step '{exc.step}' failed: {exc.message}", "kind": exc.kind, "step": exc.step, "retryable": True},
        ) from exc
    except IntegrityError as exc:  # a second analysis of the same version finished first
        db.rollback()
        raise HTTPException(409, detail={"message": "This version is already being analysed. Wait a moment, reload and check the result.", "retryable": True}) from exc
    except Exception:
        # Anything else (for example a database hiccup while saving) must not leave a half-written analysis.
        db.rollback()
        raise

    db.refresh(version)
    return version_detail(version, version.release)


@router.post("/{version_id}/final-brief", status_code=201)
def create_final_brief(version_id: int, db: Session = Depends(get_db)):
    version = get_version(db, version_id)
    ensure_unlocked(version)
    blockers = blocking_statements(version.statements)
    if not version.statements or blockers:
        raise HTTPException(
            409,
            detail={
                "message": "Every statement must be approved or rejected (and none stale) before the brief can be generated.",
                "blocking_statement_ids": [s.id for s in blockers],
            },
        )
    if not any(s.status == "approved" for s in version.statements):
        raise HTTPException(409, detail={"message": "No statement is approved yet.", "blocking_statement_ids": []})

    content = build_brief(version, version.statements, version.analysis, version.release.name)
    if version.final_brief is not None:  # a leftover row from an earlier try must not cause an error
        version.final_brief.content_md = content
    else:
        db.add(FinalBrief(version_id=version.id, content_md=content))
    version.review_state = "brief_generated"
    db.commit()
    log_event(logger, "final_brief_generated", version_id=version.id)
    return {"content_md": content, "review_state": version.review_state}


@router.get("/{version_id}/final-brief")
def get_final_brief(version_id: int, db: Session = Depends(get_db)):
    version = get_version(db, version_id)
    if version.final_brief is None:
        raise HTTPException(404, "No final brief has been generated for this version.")
    return {"content_md": version.final_brief.content_md, "created_at": version.final_brief.created_at.isoformat()}
