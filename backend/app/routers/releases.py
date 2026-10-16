import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_by_id, get_db
from ..logging_config import log_event
from ..models import Release, ReleaseVersion
from ..schemas import PackageIn, ReleaseCreate, VersionCreate
from ..services.diffing import carry_statements, compare_packages
from ..services.package import compute_hashes, normalize_package
from ..services.serialize import live_stale, version_summary

router = APIRouter(prefix="/api/releases", tags=["releases"])
logger = logging.getLogger(__name__)
SAMPLE_PATH = Path(__file__).resolve().parent.parent / "seed" / "sample_release.json"


def _get_release(db: Session, release_id: int) -> Release:
    release = get_by_id(db, Release, release_id)
    if release is None:
        raise HTTPException(404, "Release not found.")
    return release


def create_version(db: Session, release: Release, package_in: PackageIn) -> ReleaseVersion:
    """Save a new immutable package version. Statements from the previous version are carried over
    and marked stale where the items they cite changed or disappeared."""
    package = normalize_package(package_in.model_dump())
    hashes = compute_hashes(package)
    previous = release.versions[-1] if release.versions else None
    version = ReleaseVersion(
        release_id=release.id,
        version_no=(previous.version_no + 1) if previous else 1,
        package_json=package,
        item_hashes_json=hashes,
        review_state="draft",
    )
    if previous:
        version.statements = carry_statements(previous.statements, hashes)
        if version.statements:
            version.review_state = "in_review"
    db.add(version)
    try:
        db.commit()
    except IntegrityError as exc:  # two people saved the same next version number at once
        db.rollback()
        raise HTTPException(409, "Another version was saved at the same moment. Reload and try again.") from exc
    db.refresh(version)
    stale = sum(1 for s in version.statements if s.status == "stale")
    log_event(logger, "version_created", release_id=release.id, version_id=version.id, version_no=version.version_no, carried=len(version.statements), stale=stale)
    return version


@router.get("")
def list_releases(db: Session = Depends(get_db)):
    releases = db.scalars(select(Release).order_by(Release.id.desc())).all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "created_at": r.created_at.isoformat(),
            "version_count": len(r.versions),
            "latest_version": version_summary(r.versions[-1]) if r.versions else None,
        }
        for r in releases
    ]


@router.post("", status_code=201)
def create_release(body: ReleaseCreate, db: Session = Depends(get_db)):
    release = Release(name=body.name)
    db.add(release)
    db.commit()
    db.refresh(release)
    log_event(logger, "release_created", release_id=release.id)
    return {"id": release.id, "name": release.name}


@router.post("/sample", status_code=201)
def create_sample(db: Session = Depends(get_db)):
    data = json.loads(SAMPLE_PATH.read_text())
    release = Release(name=data["name"])
    db.add(release)
    db.commit()
    db.refresh(release)
    version = create_version(db, release, PackageIn(**data["package"]))
    return {"id": release.id, "name": release.name, "version_id": version.id}


@router.get("/{release_id}")
def get_release(release_id: int, db: Session = Depends(get_db)):
    release = _get_release(db, release_id)
    return {
        "id": release.id,
        "name": release.name,
        "created_at": release.created_at.isoformat(),
        "versions": [version_summary(v) for v in release.versions],
    }


@router.post("/{release_id}/versions", status_code=201)
def add_version(release_id: int, body: VersionCreate, db: Session = Depends(get_db)):
    release = _get_release(db, release_id)
    version = create_version(db, release, body.package)
    return version_summary(version)


@router.get("/{release_id}/versions")
def list_versions(release_id: int, db: Session = Depends(get_db)):
    return [version_summary(v) for v in _get_release(db, release_id).versions]


@router.get("/{release_id}/compare")
def compare(release_id: int, from_: int = Query(alias="from"), to: int = Query(), db: Session = Depends(get_db)):
    release = _get_release(db, release_id)
    by_no = {v.version_no: v for v in release.versions}
    if from_ not in by_no or to not in by_no:
        raise HTTPException(404, "One of the versions does not exist for this release.")
    a, b = by_no[from_], by_no[to]
    return {
        "from": version_summary(a),
        "to": version_summary(b),
        "diff": compare_packages(a.package_json, b.package_json),
        # statements written for `from` whose cited items differ in `to`
        "stale_statements": live_stale(a.statements, b.item_hashes_json),
    }
