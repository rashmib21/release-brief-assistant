"""Deterministic stand-in for the LLM. Used by tests and for offline demos (LLM_PROVIDER=mock).

It follows the same contract as the Gemini client, so guardrails and the workflow are exercised for real.
"""
import re
from typing import TypeVar

from pydantic import BaseModel

from ..schemas import (
    ClassificationItem,
    ClassificationOutput,
    GapsOutput,
    MissingInfo,
    StatementOut,
    StatementsOutput,
    UnsupportedClaim,
)
from ..services.package import CLAIM_SECTIONS, is_none_text, qa_coverage

T = TypeVar("T", bound=BaseModel)

UNIVERSAL = re.compile(r"\b(all|every|always|never|fully|100%|any)\b", re.I)
LOW_WORDS = re.compile(r"\b(dark mode|theme|cosmetic|typo|label|colou?r|icon)\b", re.I)
HIGH_WORDS = re.compile(r"\b(payment|upi|security|login|auth|data loss|checkout|refund|cancel)\b", re.I)


def _claims(package: dict):
    for key in CLAIM_SECTIONS:
        for item in package.get(key, []):
            if item["text"] and not is_none_text(item["text"]):
                yield key, item


def _short(text: str, limit: int = 420) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _bare(text: str) -> str:
    """Item text without its trailing full stop, so we can append our own punctuation."""
    return text.strip().rstrip(".")


class MockLLM:
    model_name = "mock-llm"
    # Set by tests to simulate bad model output once, then recover.
    fail_first_statements_with: StatementsOutput | None = None

    def __init__(self):
        self._statement_calls = 0

    def generate(self, step: str, system: str, user: str, schema: type[T], context: dict) -> T:
        package = context["package"]
        if step == "classify":
            return self._classify(package)  # type: ignore[return-value]
        if step == "gaps":
            return self._gaps(package)  # type: ignore[return-value]
        if step == "statements":
            self._statement_calls += 1
            if self.fail_first_statements_with is not None and self._statement_calls == 1:
                return self.fail_first_statements_with  # type: ignore[return-value]
            return self._statements(package, context["gaps"])  # type: ignore[return-value]
        raise ValueError(f"unknown step {step}")

    def _classify(self, package: dict) -> ClassificationOutput:
        groups = [g["text"] for g in package.get("affected_user_groups", []) if not is_none_text(g["text"])]
        out = []
        for key, item in _claims(package):
            if key == "changed_behaviour" or HIGH_WORDS.search(item["text"]):
                impact = "high"
            elif LOW_WORDS.search(item["text"]):
                impact = "low"
            else:
                impact = "medium"
            out.append(
                ClassificationItem(
                    item_id=item["id"],
                    user_groups=groups[:3] or ["Unspecified"],
                    impact=impact,
                    reason=_short(f"Rated {impact} from the wording of {item['id']}.", 200),
                )
            )
        return ClassificationOutput(classifications=out)

    def _gaps(self, package: dict) -> GapsOutput:
        coverage = qa_coverage(package)
        qa_text = {q["id"]: q["text"] for q in package.get("qa_summary", [])}
        missing, unsupported = [], []
        for _key, item in _claims(package):
            qa_ids = coverage.get(item["id"], [])
            if not qa_ids:
                missing.append(
                    MissingInfo(
                        topic=f"No QA evidence for {item['id']}",
                        why_it_matters="Readers cannot tell whether this change was tested.",
                        related_ids=[item["id"]],
                    )
                )
                unsupported.append(
                    UnsupportedClaim(
                        claim_item_id=item["id"],
                        claim=_short(item["text"], 200),
                        qa_ids=[],
                        reason="No QA item covers this claim.",
                    )
                )
            elif UNIVERSAL.search(item["text"]) and any(re.search(r"\bonly\b", qa_text[q], re.I) for q in qa_ids):
                unsupported.append(
                    UnsupportedClaim(
                        claim_item_id=item["id"],
                        claim=_short(item["text"], 200),
                        qa_ids=qa_ids,
                        reason="The claim is broad, but the QA evidence says testing was limited.",
                    )
                )
        migrations = [m for m in package.get("migration_notes", []) if not is_none_text(m["text"])]
        if migrations and not any("rollback" in m["text"].lower() for m in migrations):
            missing.append(
                MissingInfo(
                    topic="Migration has no rollback steps",
                    why_it_matters="Operators need to know how to undo the migration if it fails.",
                    related_ids=[m["id"] for m in migrations],
                )
            )
        return GapsOutput(missing_info=missing, unsupported_claims=unsupported)

    def _statements(self, package: dict, gaps: dict) -> StatementsOutput:
        coverage = qa_coverage(package)
        stmts: list[StatementOut] = []
        for _key, item in _claims(package):
            qa_ids = coverage.get(item["id"], [])
            cites = [item["id"], *qa_ids]
            verified = "QA verified." if qa_ids else "Not verified by QA yet."
            stmts.append(StatementOut(audience="technical", section="summary", text=_short(f"{_bare(item['text'])} ({verified})"), citations=cites))
            stmts.append(
                StatementOut(
                    audience="client",
                    section="summary",
                    text=_short(f"What is new for you: {_bare(item['text'])}. {verified}"),
                    citations=cites,
                )
            )
        for m in package.get("migration_notes", []):
            if m["text"] and not is_none_text(m["text"]):
                stmts.append(
                    StatementOut(audience="technical", section="summary", text=_short(f"Migration or configuration step: {_bare(m['text'])}."), citations=[m["id"]])
                )
        limits = package.get("known_limitations", [])
        real_limits = [l for l in limits if l["text"] and not is_none_text(l["text"])]
        for lim in real_limits:
            stmts.append(StatementOut(audience="technical", section="risks", text=_short(f"Known limitation: {_bare(lim['text'])}."), citations=[lim["id"]]))
            stmts.append(StatementOut(audience="client", section="risks", text=_short(f"Please note: {_bare(lim['text'])}."), citations=[lim["id"]]))
        for u in gaps.get("unsupported_claims", []):
            cites = [u["claim_item_id"], *u["qa_ids"]]
            stmts.append(StatementOut(audience="technical", section="risks", text=_short(f"Unsupported by QA: {_bare(u['claim'])}. {u['reason']}"), citations=cites))
            stmts.append(StatementOut(audience="client", section="risks", text=_short(f"Not yet confirmed by testing: {_bare(u['claim'])}."), citations=cites))
        if not real_limits:
            anchor = limits[0]["id"]
            stmts.append(StatementOut(audience="technical", section="risks", text="No known limitations were reported.", citations=[anchor]))
            stmts.append(StatementOut(audience="client", section="risks", text="No known limitations were reported.", citations=[anchor]))
        return StatementsOutput(statements=stmts)
