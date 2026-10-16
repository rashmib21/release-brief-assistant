"""Deterministic checks on AI output. The AI is never trusted to cite correctly."""
from ..schemas import ClassificationOutput, GapsOutput, StatementsOutput
from .package import CLAIM_PREFIXES, CLAIM_SECTIONS, is_none_text, item_index

IMPACTS = {"high", "medium", "low"}
AUDIENCES = ("technical", "client")
SECTION_KINDS = {"summary", "risks"}
MAX_STATEMENT_CHARS = 800


class GuardrailError(Exception):
    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("; ".join(problems))


def _id(value: str) -> str:
    return str(value).strip().upper()


def normalize_output(out):
    """Fix harmless formatting slips (case, spaces, duplicate IDs) so they do not cost a retry.
    Real problems, such as an ID that does not exist, are still caught by the checks below."""
    if isinstance(out, ClassificationOutput):
        for c in out.classifications:
            c.item_id, c.impact = _id(c.item_id), c.impact.strip().lower()
    elif isinstance(out, GapsOutput):
        for m in out.missing_info:
            m.related_ids = list(dict.fromkeys(_id(i) for i in m.related_ids))
        for u in out.unsupported_claims:
            u.claim_item_id = _id(u.claim_item_id)
            u.qa_ids = list(dict.fromkeys(_id(i) for i in u.qa_ids))
    elif isinstance(out, StatementsOutput):
        for st in out.statements:
            st.audience, st.section = st.audience.strip().lower(), st.section.strip().lower()
            st.citations = list(dict.fromkeys(_id(i) for i in st.citations))
    return out


def check_classifications(out: ClassificationOutput, package: dict) -> None:
    index = item_index(package)
    problems = []
    seen = set()
    for c in out.classifications:
        if c.item_id not in index:
            problems.append(f"classification cites unknown item {c.item_id}")
        if c.impact not in IMPACTS:
            problems.append(f"{c.item_id}: impact must be high, medium or low (got {c.impact!r})")
        if not c.reason.strip():
            problems.append(f"{c.item_id}: reason is empty")
        seen.add(c.item_id)
    for key in CLAIM_SECTIONS:
        for item in package.get(key, []):
            if item["text"] and not is_none_text(item["text"]) and item["id"] not in seen:
                problems.append(f"{item['id']} was not classified")
    if problems:
        raise GuardrailError(problems)


def check_gaps(out: GapsOutput, package: dict) -> None:
    index = item_index(package)
    problems = []
    for m in out.missing_info:
        if not m.topic.strip():
            problems.append("missing_info entry has empty topic")
        for rid in m.related_ids:
            if rid not in index:
                problems.append(f"missing_info cites unknown item {rid}")
    for u in out.unsupported_claims:
        if u.claim_item_id not in index:
            problems.append(f"unsupported claim cites unknown item {u.claim_item_id}")
        for qid in u.qa_ids:
            if qid not in index or not qid.startswith("Q"):
                problems.append(f"unsupported claim cites unknown QA item {qid}")
    if problems:
        raise GuardrailError(problems)


def check_statements(out: StatementsOutput, package: dict) -> None:
    index = item_index(package)
    problems = []
    seen = {(a, k): 0 for a in AUDIENCES for k in SECTION_KINDS}
    if not out.statements:
        problems.append("no statements were produced")
    for n, s in enumerate(out.statements, start=1):
        tag = f"statement {n}"
        if s.audience not in AUDIENCES:
            problems.append(f"{tag}: audience must be technical or client")
            continue
        if s.section not in SECTION_KINDS:
            problems.append(f"{tag}: section must be summary or risks")
            continue
        seen[(s.audience, s.section)] += 1
        if not s.text.strip():
            problems.append(f"{tag}: text is empty")
        if len(s.text) > MAX_STATEMENT_CHARS:
            problems.append(f"{tag}: text longer than {MAX_STATEMENT_CHARS} characters")
        if not s.citations:
            problems.append(f"{tag}: has no citation")
        for cid in s.citations:
            if cid not in index:
                problems.append(f"{tag}: cites unknown item {cid}")
    for (audience, kind), count in seen.items():
        if count == 0:
            problems.append(f"missing {kind} statement for {audience} audience")
    if problems:
        raise GuardrailError(problems)


def deterministic_flags(citation_ids: list[str]) -> list[dict]:
    """A statement about a feature/bug fix/behaviour change must also cite QA evidence."""
    cites_claim = any(c.startswith(CLAIM_PREFIXES) for c in citation_ids)
    cites_qa = any(c.startswith("Q") for c in citation_ids)
    if cites_claim and not cites_qa:
        return [
            {
                "code": "no_qa_citation",
                "message": "Cites a feature, fix or behaviour change but no QA evidence. Treat as unsupported.",
            }
        ]
    return []
