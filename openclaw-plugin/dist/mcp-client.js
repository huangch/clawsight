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
export class McpHttpClient {
    mcpUrl;
    timeoutS;
    sessionId = null;
    msgId = 0;
    _mcpUrl;
    constructor(mcpUrl, timeoutS = 300) {
        this.mcpUrl = mcpUrl;
        this.timeoutS = timeoutS;
        this._mcpUrl = mcpUrl.replace(/\/$/, "");
    }
    get url() {
        return this._mcpUrl;
    }
    nextId() {
        return ++this.msgId;
    }
    reqHeaders() {
        const h = {
            "Content-Type": "application/json",
            Accept: "application/json, text/event-stream",
        };
        if (this.sessionId)
            h["Mcp-Session-Id"] = this.sessionId;
        return h;
    }
    notifyHeaders() {
        const h = { "Content-Type": "application/json" };
        if (this.sessionId)
            h["Mcp-Session-Id"] = this.sessionId;
        return h;
    }
    static parseSSE(text) {
        let last = null;
        for (const line of text.split("\n")) {
            if (line.startsWith("data: ")) {
                try {
                    last = JSON.parse(line.slice(6));
                }
                catch {
                    // skip malformed lines
                }
            }
        }
        return last;
    }
    async post(payload) {
        const controller = new AbortController();
        const t = setTimeout(() => controller.abort(), this.timeoutS * 1000);
        try {
            const resp = await fetch(this._mcpUrl, {
                method: "POST",
                headers: this.reqHeaders(),
                body: JSON.stringify(payload),
                signal: controller.signal,
            });
            const sid = resp.headers.get("mcp-session-id") ??
                resp.headers.get("Mcp-Session-Id");
            if (sid)
                this.sessionId = sid;
            if (resp.status === 202 || resp.status === 204)
                return null;
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
        }
        finally {
            clearTimeout(t);
        }
    }
    async notify(payload) {
        try {
            const resp = await fetch(this._mcpUrl, {
                method: "POST",
                headers: this.notifyHeaders(),
                body: JSON.stringify(payload),
            });
            const sid = resp.headers.get("mcp-session-id") ??
                resp.headers.get("Mcp-Session-Id");
            if (sid)
                this.sessionId = sid;
        }
        catch {
            // notifications are fire-and-forget
        }
    }
    async initialize() {
        const data = (await this.post({
            jsonrpc: "2.0",
            id: this.nextId(),
            method: "initialize",
            params: {
                protocolVersion: "2025-03-26",
                capabilities: {},
                clientInfo: { name: "clawsight", version: "1.0.0" },
            },
        }));
        await this.notify({
            jsonrpc: "2.0",
            method: "notifications/initialized",
        });
        return data ?? {};
    }
    async ensureInitialized() {
        if (!this.sessionId)
            await this.initialize();
    }
    async listTools() {
        await this.ensureInitialized();
        const data = (await this.post({
            jsonrpc: "2.0",
            id: this.nextId(),
            method: "tools/list",
        }));
        return (data?.["result"]?.["tools"] ?? []);
    }
    async callTool(name, args) {
        await this.ensureInitialized();
        const data = (await this.post({
            jsonrpc: "2.0",
            id: this.nextId(),
            method: "tools/call",
            params: { name, arguments: args },
        }));
        if (data === null || data === undefined) {
            return "[No response from MCP server]";
        }
        if (data["error"]) {
            const e = data["error"];
            return `[MCP Error ${e["code"] ?? ""}: ${e["message"] ?? ""}]`;
        }
        const content = data["result"]?.["content"] ??
            [];
        const texts = content
            .filter((c) => typeof c === "object" &&
            c !== null &&
            c.type === "text" &&
            typeof c.text === "string")
            .map((c) => c.text);
        return texts.join("\n") || "[Empty response]";
    }
    reset() {
        this.sessionId = null;
        this.msgId = 0;
    }
    static asText(title, body) {
        return { content: [{ type: "text", text: `## ${title}\n\n${body}` }] };
    }
}
