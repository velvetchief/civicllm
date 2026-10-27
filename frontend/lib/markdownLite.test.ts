// The frontend half of the citation promise: inline [n] markers become
// citation chips ONLY when they match a real source number — everything else
// (including while streaming, before sources arrive) must stay literal text,
// with no HTML injection path. These tests inspect the React element tree
// directly; no DOM is required.

import { isValidElement, type ReactElement, type ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { renderAnswerText, safeHref, stripMarkdown } from "./markdownLite";
import type { Source } from "./types";

const opts = { anchorPrefix: "ans1", lang: "en" as const };

const source = (n: number): Source => ({
  number: n,
  title: "Site Development Regulations",
  hierarchy: ["Title 25"],
  section_ref: "§ 25-2-492",
  source_url: null,
  excerpt: "…",
});

function elements(nodes: ReactNode[]): ReactElement[] {
  return nodes.filter((n): n is ReactElement => isValidElement(n));
}

describe("renderAnswerText", () => {
  it("renders **bold** as <strong> and keeps surrounding text literal", () => {
    const out = renderAnswerText("Max height is **35 feet** [no cite].", [], opts);
    const strongs = elements(out).filter((e) => e.type === "strong");
    expect(strongs).toHaveLength(1);
    expect((strongs[0].props as { children: ReactNode }).children).toBe("35 feet");
    // Non-token text passes through untouched — including bracket-like text
    // that is not a numeric marker.
    expect(out.join("")).toContain("Max height is ");
    expect(out.some((n) => typeof n === "string" && n.includes("[no cite]"))).toBe(true);
  });

  it("turns a matched [n] into a citation chip anchored to its source card", () => {
    const out = renderAnswerText("A setback of 10 feet applies [2].", [source(2)], opts);
    const sups = elements(out).filter((e) => e.type === "sup");
    expect(sups).toHaveLength(1);
    const sup = sups[0].props as { className: string; children: ReactElement };
    expect(sup.className).toBe("cite");
    const anchor = sup.children.props as Record<string, unknown>;
    expect(anchor.href).toBe("#ans1-src-2");
    expect(anchor["aria-label"]).toBe("Source 2: § 25-2-492");
    expect(anchor.children).toBe(2);
  });

  it("leaves unmatched markers literal (streaming, wrong numbers)", () => {
    const out = renderAnswerText("Height is 35 feet [1] [3].", [source(1)], opts);
    expect(elements(out).filter((e) => e.type === "sup")).toHaveLength(1); // only [1]
    expect(out).toContain("[3]"); // no source 3 -> literal, never a dead link
  });

  it("tokenizes [n] inside **bold** spans", () => {
    const out = renderAnswerText("Max is **35 feet [2]** here.", [source(2)], opts);
    const strongs = elements(out).filter((e) => e.type === "strong");
    expect(strongs).toHaveLength(1);
    const children = (strongs[0].props as { children: ReactNode[] }).children;
    const sups = elements(children).filter((e) => e.type === "sup");
    expect(sups).toHaveLength(1);
    const anchor = (sups[0].props as { children: ReactElement }).children
      .props as Record<string, unknown>;
    expect(anchor.href).toBe("#ans1-src-2");
  });

  it("renders an unclosed ** at end of text as bold-to-end (streaming)", () => {
    const out = renderAnswerText("The limit is **35 fe", [], opts);
    const strongs = elements(out).filter((e) => e.type === "strong");
    expect(strongs).toHaveLength(1);
    expect((strongs[0].props as { children: ReactNode }).children).toBe("35 fe");
    // No literal asterisks anywhere in the output text nodes.
    expect(out.some((n) => typeof n === "string" && n.includes("*"))).toBe(false);
  });

  it("maps retrieval numbers to display numbers via numberMap", () => {
    const numberMap = new Map([[4, 1]]);
    const out = renderAnswerText(
      "Setback is 25 feet [4], see also [7].",
      [source(4)],
      { ...opts, numberMap }
    );
    const sups = elements(out).filter((e) => e.type === "sup");
    expect(sups).toHaveLength(1);
    const anchor = (sups[0].props as { children: ReactElement }).children
      .props as Record<string, unknown>;
    expect(anchor.href).toBe("#ans1-src-1"); // anchored by display number
    expect(anchor["aria-label"]).toBe("Source 1: § 25-2-492"); // announced as display
    expect(anchor.children).toBe(1); // chip shows display number
    expect(out).toContain("[7]"); // no mapping -> literal
  });
});

describe("safeHref", () => {
  it("allows http and https only", () => {
    expect(safeHref("https://example.gov/code")).toBe("https://example.gov/code");
    expect(safeHref("http://example.gov")).toBe("http://example.gov");
    expect(safeHref("javascript:alert(1)")).toBeNull();
    expect(safeHref("data:text/html,hi")).toBeNull();
    expect(safeHref("/relative/path")).toBeNull();
    expect(safeHref("")).toBeNull();
    expect(safeHref(null)).toBeNull();
    expect(safeHref(undefined)).toBeNull();
  });
});

describe("stripMarkdown", () => {
  it("strips bold markers for plain-text export", () => {
    expect(stripMarkdown("Max is **35 feet** [2].")).toBe("Max is 35 feet [2].");
  });
});
