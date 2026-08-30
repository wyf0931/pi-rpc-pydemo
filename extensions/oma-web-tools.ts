import { Type } from "@earendil-works/pi-ai";
import { defineTool, type ExtensionAPI } from "@earendil-works/pi-coding-agent";

const DEFAULT_SEARCH_BASE_URL = "https://qianfan.baidubce.com";
const DEFAULT_TIMEOUT_MS = 30_000;
const MAX_FETCH_CHARS = 120_000;
const MAX_SEARCH_RESULTS = 20;
const MAX_SEARCH_QUERY_CHARS = 72;

const webFetchTool = defineTool({
  name: "web_fetch",
  label: "Web Fetch",
  description: "Fetch a web page and return its readable content as Markdown using Jina Reader.",
  promptSnippet: "web_fetch: fetch a URL as Markdown before summarizing or analyzing it.",
  parameters: Type.Object({
    url: Type.String({ description: "The http(s) URL to fetch." }),
    max_chars: Type.Optional(Type.Number({ minimum: 1_000, maximum: MAX_FETCH_CHARS })),
  }),
  async execute(_toolCallId, params, signal) {
    const url = normalizeUrl(params.url);
    const readerUrl = `https://r.jina.ai/${url}`;
    const headers: Record<string, string> = { accept: "text/markdown" };
    const apiKey = process.env.JINA_API_KEY?.trim();
    if (apiKey) headers.authorization = `Bearer ${apiKey}`;
    const response = await fetchWithTimeout(readerUrl, { headers, signal });
    const maxChars = Math.min(Math.max(params.max_chars ?? 60_000, 1_000), MAX_FETCH_CHARS);
    const text = response.text.length > maxChars
      ? `${response.text.slice(0, maxChars)}\n\n[web_fetch truncated output at ${maxChars} characters]`
      : response.text;
    return { content: [{ type: "text", text }], details: { sourceUrl: url, readerUrl, truncated: response.text.length > maxChars } };
  },
});

const webSearchTool = defineTool({
  name: "web_search",
  label: "Web Search",
  description: "Search the web using Baidu Qianfan Search and return Markdown results.",
  promptSnippet: "web_search: search the web for current or source-backed information.",
  parameters: Type.Object({
    query: Type.String({ description: "Search keywords or a phrase." }),
    max_results: Type.Optional(Type.Number({ minimum: 1, maximum: MAX_SEARCH_RESULTS })),
  }),
  async execute(_toolCallId, params, signal) {
    const apiKey = process.env.BAIDU_SEARCH_API_KEY?.trim();
    if (!apiKey) throw new Error("BAIDU_SEARCH_API_KEY is not configured");
    const configuredBaseUrl = process.env.BAIDU_SEARCH_BASE_URL?.trim();
    // Keep old local .env files usable after moving from Qiniu to Qianfan.
    const baseUrl = (configuredBaseUrl && !configuredBaseUrl.includes("api.qnaigc.com")
      ? configuredBaseUrl
      : DEFAULT_SEARCH_BASE_URL).replace(/\/+$/, "");
    const query = params.query.trim().slice(0, MAX_SEARCH_QUERY_CHARS);
    const response = await fetchWithTimeout(`${baseUrl}/v2/ai_search/web_search`, {
      method: "POST",
      headers: { accept: "application/json", authorization: `Bearer ${apiKey}`, "content-type": "application/json" },
      body: JSON.stringify({
        messages: [{ role: "user", content: query }],
        search_source: "baidu_search_v2",
        resource_type_filter: [{ type: "web", top_k: params.max_results ?? 10 }],
      }),
      signal,
    });
    const payload = asRecord(response.json);
    if (payload?.code) throw new Error(`Baidu Search ${payload.code}: ${textValue(payload.message) || "request failed"}`);
    return {
      content: [{ type: "text", text: formatSearchResults(response.json, query) }],
      details: { query, requestId: textValue(payload?.request_id) || textValue(payload?.requestId) },
    };
  },
});

export default function (pi: ExtensionAPI) {
  pi.registerTool(webFetchTool);
  pi.registerTool(webSearchTool);
}

async function fetchWithTimeout(url: string, init: RequestInit): Promise<{ text: string; json: unknown }> {
  const timeout = new AbortController();
  const timer = setTimeout(() => timeout.abort(), DEFAULT_TIMEOUT_MS);
  try {
    const response = await fetch(url, { ...init, signal: mergeSignals(init.signal, timeout.signal) });
    const text = await response.text();
    if (!response.ok) throw new Error(`Request failed (${response.status}): ${text.slice(0, 300)}`);
    let json: unknown = {};
    try { json = JSON.parse(text); } catch { /* Markdown response */ }
    return { text, json };
  } finally {
    clearTimeout(timer);
  }
}

function mergeSignals(first: AbortSignal | undefined, second: AbortSignal): AbortSignal {
  if (!first) return second;
  const controller = new AbortController();
  const abort = () => controller.abort();
  first.addEventListener("abort", abort, { once: true });
  second.addEventListener("abort", abort, { once: true });
  return controller.signal;
}

function normalizeUrl(value: string): string {
  const input = value.trim();
  if (!input) throw new Error("URL is required");
  const url = new URL(/^https?:\/\//i.test(input) ? input : `https://${input}`);
  if (!['http:', 'https:'].includes(url.protocol)) throw new Error(`Unsupported URL protocol: ${url.protocol}`);
  return url.toString();
}

function formatSearchResults(value: unknown, query: string): string {
  const root = asRecord(value);
  const rows = Array.isArray(root?.references) ? root.references : [];
  const lines = [`# Web Search: ${query}`, ""];
  for (const [index, row] of rows.entries()) {
    const item = asRecord(row);
    if (!item) continue;
    const title = textValue(item.title) || "(untitled)";
    const url = textValue(item.url);
    const snippet = textValue(item.snippet) || textValue(item.content) || textValue(item.web_anchor);
    lines.push(`${index + 1}. **${title}**`, snippet, url, "");
  }
  return rows.length ? lines.join("\n") : `No web results found for '${query}'.`;
}

function asRecord(value: unknown): Record<string, any> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, any> : null;
}

function textValue(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}
