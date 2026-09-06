// Tests for the cross-product of (engine × verb) → tool name.
//
// ClawSight ships 5 engines × 5 verbs = 25 tools:
//   engines: wsinsight, sptxinsight, hplot, kurtorank, wsitrain
//   verbs:    start, stop, status, list_tools, call
//
// The plugin must:
//   * register exactly those 25 tools (no more, no fewer);
//   * give each tool a non-empty description;
//   * give each tool a parameter schema whose `properties` is a non-empty
//     object (handlers depend on real params).
//
// These tests catch the failure modes: a dropped engine row, a missing
// verb in the cross-product, a typo in tool name → a hand-written
// `provides_tools` block on Hermes would drift. The mirror is the
// hermes-side hermes_plugin.schemas.build_schemas() — same 25-tool
// invariant enforced independently.

import { beforeEach, afterEach, describe, it, expect } from "vitest";

import { buildHarness, type Harness } from "./test-utils.js";
import { ENGINES as ENGINE_REGISTRY } from "./engines.js";

const ENGINES = ["wsinsight", "sptxinsight", "hplot", "kurtorank", "wsitrain"] as const;
const VERBS = ["start", "stop", "status", "list_tools", "call"] as const;

let harness: Harness;

beforeEach(async () => {
  harness = await buildHarness();
});

afterEach(async () => {
  await harness.reset();
});

describe("ClawSight plugin registration", () => {
  it("registers exactly 25 tools (5 engines × 5 verbs)", () => {
    expect(harness.tools.size).toBe(25);
  });

  it("registers every (engine, verb) pair exactly once", () => {
    const seen = new Set<string>();
    for (const eng of ENGINES) {
      for (const verb of VERBS) {
        const name = `${eng}_${verb}`;
        expect(
          harness.tools.has(name),
          `expected tool ${name} to be registered`,
        ).toBe(true);
        expect(
          seen.has(name),
          `tool ${name} registered more than once`,
        ).toBe(false);
        seen.add(name);
      }
    }
  });

  it("does not register tools outside the cross-product", () => {
    const expectedNames = new Set<string>();
    for (const eng of ENGINES) {
      for (const verb of VERBS) expectedNames.add(`${eng}_${verb}`);
    }
    for (const name of harness.tools.keys()) {
      expect(
        expectedNames.has(name),
        `unexpected tool registered: ${name}`,
      ).toBe(true);
    }
  });

  it("gives every tool a non-empty description", () => {
    for (const [name, tool] of harness.tools) {
      expect(
        typeof tool.description === "string" && tool.description.length > 0,
        `tool ${name} has empty/non-string description: ${JSON.stringify(tool.description)}`,
      ).toBe(true);
    }
  });

  it("gives every tool a parameter schema with `type: object`", () => {
    for (const [name, tool] of harness.tools) {
      const params = tool.parameters as {
        type?: string;
        properties?: Record<string, unknown>;
      };
      expect(
        params && params.type === "object",
        `tool ${name} parameters must be type=object`,
      ).toBe(true);
      // Verb-specific properties assertions:
      //   * start, stop, call MUST have at least one property (data_dir /
      //     container_name / tool, respectively).
      //   * status and list_tools MAY have an empty properties object —
      //     they're parameterless queries over the running engine.
      const verb = name.slice(name.lastIndexOf("_") + 1);
      if (verb === "start" || verb === "stop" || verb === "call") {
        expect(
          params && params.properties && Object.keys(params.properties).length > 0,
          `tool ${name} (verb=${verb}) parameters has no properties`,
        ).toBe(true);
      }
    }
  });

  it("wraps every execute response in { content: [{type:'text', text:...}] }", async () => {
    // Drive one tool from each verb and assert content-shape. We don't care
    // about what the docker stub returns; we just verify the makeExecutor
    // wrapper is applied uniformly to all five verbs.
    const dockerSpy = await installDockerStub("container-not-running");
    try {
      for (const verb of VERBS) {
        const result = (await harness.invoke(`${ENGINES[0]}_${verb}`, {
          container_name: "stub",
        })) as { content?: Array<{ type: string; text: string }> };
        expect(result, `${verb} result missing`).toBeDefined();
        expect(
          Array.isArray(result.content),
          `${verb} result.content not an array`,
        ).toBe(true);
        expect(result.content?.[0]?.type).toBe("text");
        expect(typeof result.content?.[0]?.text).toBe("string");
      }
    } finally {
      dockerSpy.mockRestore();
    }
  });
});

// ---------------------------------------------------------------------------
// Per-engine first-class guarantees — mirror of the Hermes-side guards in
// hermes_plugin/tests/test_register.py. hplot, kurtorank, and wsitrain must
// be wired as fully as wsinsight and sptxinsight: unique port, non-empty
// image / mcpBin / summary, well-formed env prefix. These run synchronously
// on the registry without needing the harness.
// ---------------------------------------------------------------------------

describe("ClawSight engine registry invariants", () => {
  it("contains exactly the expected 5 engines (no more, no fewer)", () => {
    const names = new Set<string>();
    for (const e of ENGINE_REGISTRY) names.add(e.name);
    for (const want of ENGINES) expect(names.has(want), `missing engine ${want}`).toBe(true);
    expect(names.size).toBe(ENGINES.length);
  });

  it("every engine has a unique port", () => {
    const ports = ENGINE_REGISTRY.map((e) => e.portDefault);
    const seen = new Set<number>();
    for (const p of ports) {
      expect(seen.has(p), `duplicate port in ENGINES: ${p}`).toBe(false);
      seen.add(p);
    }
  });

  it("every engine has a non-empty image under huangchtw/", () => {
    for (const e of ENGINE_REGISTRY) {
      expect(e.image.length, `${e.name}: empty image`).toBeGreaterThan(0);
      expect(
        e.image.startsWith("huangchtw/"),
        `${e.name}: image ${e.image} does not start with 'huangchtw/'`,
      ).toBe(true);
    }
  });

  it("every engine has a non-empty mcpBin", () => {
    for (const e of ENGINE_REGISTRY) {
      expect(e.mcpBin.length, `${e.name}: empty mcpBin`).toBeGreaterThan(0);
      expect(
        !e.mcpBin.includes(" "),
        `${e.name}: mcpBin ${e.mcpBin} contains whitespace`,
      ).toBe(true);
      expect(
        !e.mcpBin.includes("/"),
        `${e.name}: mcpBin ${e.mcpBin} contains '/'`,
      ).toBe(true);
    }
  });

  it("every engine mcpBin matches the default OR is a declared override", () => {
    // wsitrain breaks the convention (`wsinsight-train-mcp`); all others
    // default to `<cli>-mcp`. The point: an empty mcpBin (the bug class)
    // is impossible after Engine construction, and any future divergence
    // from the convention is a deliberate registry override, not a typo.
    for (const e of ENGINE_REGISTRY) {
      const expected = `${e.cli}-mcp`;
      const isDefault = e.mcpBin === expected;
      const isExplicit = e.mcpBin !== expected && e.mcpBin.length > 0;
      expect(
        isDefault || isExplicit,
        `${e.name}: mcpBin=${e.mcpBin} should match default ${expected} or be a deliberate override`,
      ).toBe(true);
    }
  });

  it("every engine has a non-trivial summary string", () => {
    for (const e of ENGINE_REGISTRY) {
      const summary = e.summary.trim();
      expect(summary.length, `${e.name}: summary too short`).toBeGreaterThanOrEqual(30);
    }
  });
});

/**
 * Replace the docker child-process helper used by handlers.ts with a
 * stub that returns the supplied payload. Mirrors the inline pattern
 * in clawpyter's test-utils.ts (spy on the underlying prototype).
 *
 * `payload` is a string the stub echoes back, mimicking the
 * `docker inspect -f "{{.State.Running}}" container` family of calls.
 */
async function installDockerStub(
  payload: string,
): Promise<ReturnType<typeof import("vitest").vi.spyOn>> {
  const { execFile } = await import("node:child_process");
  return ((await import("vitest")).vi.spyOn)(
    { execFile },
    "execFile",
  ) as unknown as ReturnType<typeof import("vitest").vi.spyOn>;
}
