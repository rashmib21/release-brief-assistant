"""The 3-step AI workflow: classify -> find gaps/unsupported claims -> write statements.

Each step: call the LLM, run deterministic guardrails, retry once with the problems as feedback.
Every attempt is logged to the ai_runs table. Output is always saved as 'draft'; only a human can approve.
"""
import hashlib
import logging
import time

from sqlalchemy.orm import Session

from ..llm.client import LLMClient, LLMError
from ..llm.prompts import STEP_SYSTEM, build_user_prompt
from ..logging_config import log_event, request_id_var
from ..models import AiRun, Analysis, ReleaseVersion, Statement
from ..schemas import ClassificationOutput, GapsOutput, StatementsOutput
from . import guardrails
from .package import qa_coverage

logger = logging.getLogger(__name__)

STEPS = {
    "classify": (ClassificationOutput, guardrails.check_classifications),
    "gaps": (GapsOutput, guardrails.check_gaps),
    "statements": (StatementsOutput, guardrails.check_statements),
}


class AnalysisError(Exception):
    def __init__(self, step: str, kind: str, message: str):
        self.step, self.kind, self.message = step, kind, message
        super().__init__(f"{step}: {message}")


def _record(db: Session, version_id: int, step: str, model: str, prompt_hash: str, started: float, status: str, error: str | None):
    latency = int((time.perf_counter() - started) * 1000)
    db.add(
        AiRun(
            version_id=version_id,
            request_id=request_id_var.get(),
            step=step,
            model=model,
            prompt_hash=prompt_hash,
            latency_ms=latency,
            status=status,
            error=error,
        )
    )
    db.commit()
    log_event(
        logger,
        "ai_step",
        level=logging.INFO if status == "ok" else logging.WARNING,
        step=step,
        model=model,
        status=status,
        latency_ms=latency,
        version_id=version_id,
        error=error,
    )


def _run_step(db: Session, version: ReleaseVersion, llm: LLMClient, step: str, extra: dict, context: dict):
    schema, check = STEPS[step]
    package = version.package_json
    feedback: list[str] | None = None
    for attempt in (1, 2):
        user = build_user_prompt(step, package, extra, feedback)
        system = STEP_SYSTEM[step]
        prompt_hash = hashlib.sha256((system + user).encode()).hexdigest()[:16]
        started = time.perf_counter()
        try:
            out = guardrails.normalize_output(llm.generate(step, system, user, schema, {"package": package, **context}))
            check(out, package)
        except guardrails.GuardrailError as exc:
            _record(db, version.id, step, llm.model_name, prompt_hash, started, "guardrail_failed", str(exc)[:1000])
            feedback = exc.problems
            continue
        except LLMError as exc:
            _record(db, version.id, step, llm.model_name, prompt_hash, started, "error", f"{exc.kind}: {exc}"[:1000])
            if exc.kind == "invalid_output" and attempt == 1:
                feedback = [str(exc)]
                continue
            raise AnalysisError(step, exc.kind, str(exc)) from exc
        _record(db, version.id, step, llm.model_name, prompt_hash, started, "ok", None)
        return out
    raise AnalysisError(step, "guardrail_failed", "The AI output failed validation twice: " + "; ".join((feedback or [])[:3]))


def run_analysis(db: Session, version: ReleaseVersion, llm: LLMClient) -> None:
    package = version.package_json
    hashes = version.item_hashes_json

    classification = _run_step(db, version, llm, "classify", {}, {})
    cls_json = [c.model_dump() for c in classification.classifications]

    gaps = _run_step(db, version, llm, "gaps", {"classification": cls_json}, {})
    gaps_json = gaps.model_dump()

    statements = _run_step(
        db,
        version,
        llm,
        "statements",
        {"classification": cls_json, "gaps": gaps_json, "qa_coverage": qa_coverage(package)},
        {"gaps": gaps_json},
    )

    # Persist only after all three steps passed, so a failure never leaves half an analysis.
    if version.analysis is not None:
        db.delete(version.analysis)
    for old in list(version.statements):
        db.delete(old)
    db.flush()

    db.add(
        Analysis(
            version_id=version.id,
            classifications_json=cls_json,
            missing_info_json=gaps_json["missing_info"],
            unsupported_claims_json=gaps_json["unsupported_claims"],
        )
    )
    for s in statements.statements:
        cite_ids = list(dict.fromkeys(s.citations))
        db.add(
            Statement(
                version_id=version.id,
                audience=s.audience,
                section=s.section,
                text=s.text.strip(),
                citations_json=[{"id": cid, "hash": hashes[cid]} for cid in cite_ids],
                flags_json=guardrails.deterministic_flags(cite_ids),
                status="draft",  # AI output is never pre-approved
            )
        )
    version.review_state = "in_review"
    db.commit()
    db.refresh(version)
