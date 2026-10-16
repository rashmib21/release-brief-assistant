import { describe, expect, it } from "vitest";

import { messageFrom } from "./api";
import { blankSections, emptyPackage, isNoneText, mdToBlocks, nextId } from "./utils";

describe("package helpers", () => {
  it("assigns the next free ID for a section prefix", () => {
    expect(nextId("F", [])).toBe("F1");
    expect(nextId("F", ["F1", "F2", "B1"])).toBe("F3");
    expect(nextId("F", ["F1", "F3"])).toBe("F2");
  });

  it("treats an explicit None as filled but a blank item as missing", () => {
    expect(isNoneText(" None. ")).toBe(true);
    expect(isNoneText("N/A")).toBe(true);
    expect(isNoneText("Dark mode")).toBe(false);
    const pkg = emptyPackage();
    expect(blankSections(pkg)).toHaveLength(7);
    pkg.known_limitations[0].text = "None";
    expect(blankSections(pkg)).toHaveLength(6);
  });
});

describe("api errors", () => {
  it("turns server error shapes into readable messages", () => {
    expect(messageFrom("Release not found.")).toBe("Release not found.");
    expect(messageFrom({ message: "AI step failed", retryable: true })).toBe("AI step failed");
    expect(messageFrom([{ msg: "Field required" }, { msg: "Too long" }])).toBe("Field required; Too long");
    expect(messageFrom(undefined)).toMatch(/try again/);
  });
});

describe("brief rendering", () => {
  it("parses markdown into safe blocks without HTML", () => {
    const blocks = mdToBlocks("# Title\n\n> note\n## A\n- one [F1]\n<script>x</script>");
    expect(blocks.map((b) => b.type)).toEqual(["h1", "quote", "h2", "li", "p"]);
    expect(blocks[4].text).toBe("<script>x</script>"); // kept as plain text, React escapes it
  });
});

describe("friendly API errors", () => {
  it("names the field and item for validation errors", () => {
    const detail = [{ loc: ["body", "package", "features", 1, "text"], msg: "String should have at most 2000 characters" }];
    expect(messageFrom(detail)).toBe("Completed features, item 2: String should have at most 2000 characters");
  });
  it("hides pydantic's 'Value error' prefix", () => {
    expect(messageFrom([{ loc: ["body", "name"], msg: "Value error, Release name cannot be blank." }])).toBe("Release name: Release name cannot be blank.");
  });
  it("falls back to a plain sentence for server errors with no body", () => {
    expect(messageFrom(null, 500)).toMatch(/server had a problem/);
  });
});
