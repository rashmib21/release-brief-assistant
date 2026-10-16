export type Item = { id: string; text: string; covers?: string[] };
export type Package = Record<string, Item[]>;

export type VersionSummary = {
  id: number;
  release_id: number;
  version_no: number;
  review_state: "draft" | "in_review" | "brief_generated";
  created_at: string;
  has_analysis: boolean;
  statement_counts: Record<string, number>;
};

export type ReleaseRow = {
  id: number;
  name: string;
  created_at: string;
  version_count: number;
  latest_version: VersionSummary | null;
};

export type ReleaseDetail = { id: number; name: string; created_at: string; versions: VersionSummary[] };

export type Citation = { id: string; section: string | null; item_text: string | null; exists: boolean };
export type Flag = { code: string; message: string };
export type StatementStatus = "draft" | "approved" | "rejected" | "stale";

export type Statement = {
  id: number;
  audience: "technical" | "client";
  section: "summary" | "risks";
  text: string;
  edited_text: string | null;
  effective_text: string;
  citations: Citation[];
  flags: Flag[];
  status: StatementStatus;
  stale_reason: string | null;
  carried_from_id: number | null;
};

export type Classification = { item_id: string; user_groups: string[]; impact: "high" | "medium" | "low"; reason: string };
export type MissingInfo = { topic: string; why_it_matters: string; related_ids: string[] };
export type UnsupportedClaim = { claim_item_id: string; claim: string; qa_ids: string[]; reason: string };

export type VersionDetail = VersionSummary & {
  release_name: string;
  package: Package;
  locked: boolean;
  analysis: { classifications: Classification[]; missing_info: MissingInfo[]; unsupported_claims: UnsupportedClaim[]; created_at: string } | null;
  statements: Statement[];
  final_brief: { content_md: string; created_at: string } | null;
};

export type ValidationIssue = { code: string; section: string; item_id?: string; message: string };
export type Validation = { valid: boolean; errors: ValidationIssue[]; warnings: ValidationIssue[] };

export type SectionDiff = { label: string; added: Item[]; removed: Item[]; changed: { id: string; before: Item; after: Item }[] };
export type Comparison = {
  from: VersionSummary;
  to: VersionSummary;
  diff: { sections: Record<string, SectionDiff>; totals: { added: number; removed: number; changed: number } };
  stale_statements: { statement_id: number; audience: string; text: string; reason: string; status: string }[];
};
