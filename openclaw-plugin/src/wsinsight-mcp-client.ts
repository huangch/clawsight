// MCP 2025-03-26 Streamable HTTP client for the WSInsight MCP server.
//
// Protocol:
//   POST {url}
//     Content-Type: application/json
//     Accept: application/json, text/event-stream
//     Mcp-Session-Id: {sid}   (after initialization)
//
//   Response is either plain JSON or SSE (text/event-stream).
//   For SSE: split on newlines, last "data: {...}" line is the result.
//
// Docker lifecycle (start/stop) is managed externally via the shell scripts
// start-wsinsight.sh / stop-wsinsight.sh shipped alongside this plugin.

export type TextResult = {
  content: Array<{ type: "text"; text: string }>;
};

export class WsInsightMcpClient {
  private sessionId: string | null = null;
  private msgId = 0;

  constructor(
    public mcpUrl: string,
    private readonly timeoutMs: number = 300_000,
  ) {}

  // -------------------------------------------------------------------------
  // Session helpers
  // -------------------------------------------------------------------------

  private nextId(): number {
    return ++this.msgId;
  }

  private reqHeaders(): Record<string, string> {
    const h: Record<string, string> = {
      "Content-Type": "application/json",
      "Accept": "application/json, text/event-stream",
    };
    if (this.sessionId) h["Mcp-Session-Id"] = this.sessionId;
    return h;
  }

  private notifyHeaders(): Record<string, string> {
    const h: Record<string, string> = { "Content-Type": "application/json" };
    if (this.sessionId) h["Mcp-Session-Id"] = this.sessionId;
    return h;
  }

  private extractSession(resp: Response): void {
    const sid =
      resp.headers.get("mcp-session-id") ??
      resp.headers.get("Mcp-Session-Id");
    if (sid) this.sessionId = sid;
  }

  private static parseSSE(text: string): unknown {
    let last: unknown = null;
    for (const line of text.split("\n")) {
      if (line.startsWith("data: ")) {
        try {
          last = JSON.parse(line.slice(6));
        } catch {
          // skip malformed lines
        }
      }
    }
    return last;
  }

  // -------------------------------------------------------------------------
  // Low-level POST
  // -------------------------------------------------------------------------

  private async post(payload: unknown): Promise<unknown> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);

    try {
      const resp = await fetch(this.mcpUrl, {
        method: "POST",
        headers: this.reqHeaders(),
        body: JSON.stringify(payload),
        signal: controller.signal,
      });

      this.extractSession(resp);

      if (resp.status === 202 || resp.status === 204) return null;

      if (!resp.ok) {
        const body = await resp.text();
        throw new Error(`HTTP ${resp.status}: ${body.slice(0, 200)}`);
      }

      const ct = resp.headers.get("content-type") ?? "";
      const text = await resp.text();
      if (ct.includes("text/event-stream")) {
        return WsInsightMcpClient.parseSSE(text);
      }
      return text.trim() ? JSON.parse(text) : null;
    } finally {
      clearTimeout(timer);
    }
  }

  private async notify(payload: unknown): Promise<void> {
    try {
      const resp = await fetch(this.mcpUrl, {
        method: "POST",
        headers: this.notifyHeaders(),
        body: JSON.stringify(payload),
      });
      this.extractSession(resp);
    } catch {
      // notifications are fire-and-forget
    }
  }

  // -------------------------------------------------------------------------
  // MCP protocol
  // -------------------------------------------------------------------------

  async initialize(): Promise<Record<string, unknown>> {
    const data = (await this.post({
      jsonrpc: "2.0",
      id: this.nextId(),
      method: "initialize",
      params: {
        protocolVersion: "2025-03-26",
        capabilities: {},
        clientInfo: { name: "clawsight", version: "1.0.0" },
      },
    })) as Record<string, unknown> | null;

    await this.notify({ jsonrpc: "2.0", method: "notifications/initialized" });
    return data ?? {};
  }

  async ensureInitialized(): Promise<void> {
    if (!this.sessionId) await this.initialize();
  }

  async listTools(): Promise<Array<Record<string, unknown>>> {
    await this.ensureInitialized();
    const data = (await this.post({
      jsonrpc: "2.0",
      id: this.nextId(),
      method: "tools/list",
    })) as Record<string, unknown> | null;
    return (
      (
        (data?.["result"] as Record<string, unknown>)?.["tools"] as Array<
          Record<string, unknown>
        >
      ) ?? []
    );
  }

  async callTool(name: string, args: Record<string, unknown>): Promise<string> {
    await this.ensureInitialized();
    const data = (await this.post({
      jsonrpc: "2.0",
      id: this.nextId(),
      method: "tools/call",
      params: { name, arguments: args },
    })) as Record<string, unknown> | null;

    if (!data) return "[No response from MCP server]";

    if (data["error"]) {
      const e = data["error"] as Record<string, unknown>;
      return `[MCP Error ${e["code"] ?? ""}]: ${e["message"] ?? ""}`;
    }

    const content = (
      (data["result"] as Record<string, unknown>)?.["content"] as unknown[]
    ) ?? [];
    const texts = content
      .filter(
        (c): c is { type: string; text: string } =>
          typeof c === "object" &&
          c !== null &&
          (c as { type: string }).type === "text",
      )
      .map((c) => c.text);

    return texts.join("\n") || "[Empty response]";
  }

  reset(): void {
    this.sessionId = null;
    this.msgId = 0;
  }

  // -------------------------------------------------------------------------
  // Response helper
  // -------------------------------------------------------------------------

  static asText(title: string, body: string): TextResult {
    return { content: [{ type: "text", text: `## ${title}\n\n${body}` }] };
  }
}
