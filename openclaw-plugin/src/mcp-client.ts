// MCP 2025-03-26 Streamable HTTP client — endpoint-agnostic.
//
// Protocol:
//   POST {url}
//     Content-Type: application/json
//     Accept: application/json, text/event-stream
//     Mcp-Session-Id: {sid}   (after initialize)
//
//   Response is either plain JSON or SSE (text/event-stream).
//   For SSE: split on lines, the last "data: {...}" frame is the result.
//
// Engine-agnostic — works equally for wsinsight / sptxinsight / hplot /
// kurtorank / wsitrain containers. Mirrors `hermes-plugin/mcpclient.py`'s
// McpHttpClient byte-for-byte in protocol semantics.

export interface TextResult {
  content: Array<{ type: "text"; text: string }>;
}

export class McpHttpClient {
  public sessionId: string | null = null;
  private msgId = 0;
  private _mcpUrl: string;
  constructor(
    public mcpUrl: string,
    private readonly timeoutS: number = 300,
  ) {
    this._mcpUrl = mcpUrl.replace(/\/$/, "");
  }
  get url(): string {
    return this._mcpUrl;
  }

  private nextId(): number {
    return ++this.msgId;
  }

  private reqHeaders(): Record<string, string> {
    const h: Record<string, string> = {
      "Content-Type": "application/json",
      Accept: "application/json, text/event-stream",
    };
    if (this.sessionId) h["Mcp-Session-Id"] = this.sessionId;
    return h;
  }

  private notifyHeaders(): Record<string, string> {
    const h: Record<string, string> = { "Content-Type": "application/json" };
    if (this.sessionId) h["Mcp-Session-Id"] = this.sessionId;
    return h;
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

  private async post(payload: unknown): Promise<unknown> {
    const controller = new AbortController();
    const t = setTimeout(() => controller.abort(), this.timeoutS * 1000);
    try {
      const resp = await fetch(this._mcpUrl, {
        method: "POST",
        headers: this.reqHeaders(),
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
      const sid =
        resp.headers.get("mcp-session-id") ??
        resp.headers.get("Mcp-Session-Id");
      if (sid) this.sessionId = sid;

      if (resp.status === 202 || resp.status === 204) return null;
      if (!resp.ok) {
        const body = await resp.text();
        throw new Error(`HTTP ${resp.status}: ${body.slice(0, 200)}`);
      }
      const ct = resp.headers.get("content-type") ?? "";
      const text = await resp.text();
      if (ct.includes("text/event-stream")) {
        return McpHttpClient.parseSSE(text);
      }
      return text.trim() ? JSON.parse(text) : null;
    } finally {
      clearTimeout(t);
    }
  }

  private async notify(payload: unknown): Promise<void> {
    try {
      const resp = await fetch(this._mcpUrl, {
        method: "POST",
        headers: this.notifyHeaders(),
        body: JSON.stringify(payload),
      });
      const sid =
        resp.headers.get("mcp-session-id") ??
        resp.headers.get("Mcp-Session-Id");
      if (sid) this.sessionId = sid;
    } catch {
      // notifications are fire-and-forget
    }
  }

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
    await this.notify({
      jsonrpc: "2.0",
      method: "notifications/initialized",
    });
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

    if (data === null || data === undefined) {
      return "[No response from MCP server]";
    }
    if (data["error"]) {
      const e = data["error"] as Record<string, unknown>;
      return `[MCP Error ${e["code"] ?? ""}: ${e["message"] ?? ""}]`;
    }
    const content =
      ((data["result"] as Record<string, unknown>)?.["content"] as unknown[]) ??
      [];
    const texts = content
      .filter(
        (c): c is { type: string; text: string } =>
          typeof c === "object" &&
          c !== null &&
          (c as { type: string }).type === "text" &&
          typeof (c as { text?: unknown }).text === "string",
      )
      .map((c) => c.text);
    return texts.join("\n") || "[Empty response]";
  }

  reset(): void {
    this.sessionId = null;
    this.msgId = 0;
  }

  static asText(title: string, body: string): TextResult {
    return { content: [{ type: "text", text: `## ${title}\n\n${body}` }] };
  }
}
