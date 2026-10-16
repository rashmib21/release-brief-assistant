import type { Item, Package } from "./types";

export const SECTIONS = [
  { key: "features", prefix: "F", label: "Completed features", hint: "What shipped. One feature per item." },
  { key: "bug_fixes", prefix: "B", label: "Bug fixes", hint: "What was broken and is now fixed." },
  { key: "changed_behaviour", prefix: "C", label: "Changed behaviour", hint: "Anything that works differently for users." },
  { key: "qa_summary", prefix: "Q", label: "QA summary", hint: "What was tested, where, and the result. Link items it covers." },
  { key: "known_limitations", prefix: "L", label: "Known limitations", hint: "What does not work or is not supported yet." },
  { key: "migration_notes", prefix: "M", label: "Migration or configuration notes", hint: "Steps operators must take." },
  { key: "affected_user_groups", prefix: "U", label: "Affected user groups", hint: "Who is impacted." },
] as const;

const NONE_WORDS = new Set(["none", "n/a", "na", "nil", "not applicable"]);
export const isNoneText = (t: string) => NONE_WORDS.has(t.trim().replace(/\.$/, "").toLowerCase());

export function nextId(prefix: string, existing: string[]): string {
  let n = 1;
  while (existing.includes(`${prefix}${n}`)) n++;
  return `${prefix}${n}`;
}

export function emptyPackage(): Package {
  const pkg: Package = {};
  for (const s of SECTIONS) pkg[s.key] = [{ id: `${s.prefix}1`, text: "", ...(s.key === "qa_summary" ? { covers: [] } : {}) }];
  return pkg;
}

export function allIds(pkg: Package): string[] {
  return Object.values(pkg).flatMap((items) => items.map((i) => i.id));
}

export function claimItems(pkg: Package): Item[] {
  return ["features", "bug_fixes", "changed_behaviour"].flatMap((k) => pkg[k] ?? []).filter((i) => i.text.trim() && !isNoneText(i.text));
}

/** Sections that would fail the server's "blank section" check. */
export function blankSections(pkg: Package): string[] {
  return SECTIONS.filter((s) => !(pkg[s.key] ?? []).some((i) => i.text.trim())).map((s) => s.label);
}

export type Block = { type: "h1" | "h2" | "h3" | "li" | "quote" | "p"; text: string };

/** Minimal Markdown-to-blocks for the brief (headings, bullets, quotes). No HTML is ever injected. */
export function mdToBlocks(md: string): Block[] {
  const blocks: Block[] = [];
  for (const raw of md.split("\n")) {
    const line = raw.trimEnd();
    if (!line.trim()) continue;
    if (line.startsWith("### ")) blocks.push({ type: "h3", text: line.slice(4) });
    else if (line.startsWith("## ")) blocks.push({ type: "h2", text: line.slice(3) });
    else if (line.startsWith("# ")) blocks.push({ type: "h1", text: line.slice(2) });
    else if (line.startsWith("- ")) blocks.push({ type: "li", text: line.slice(2) });
    else if (line.startsWith("> ")) blocks.push({ type: "quote", text: line.slice(2) });
    else blocks.push({ type: "p", text: line });
  }
  return blocks;
}

export const fmtDate = (iso: string) => new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
