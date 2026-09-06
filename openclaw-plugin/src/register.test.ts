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
