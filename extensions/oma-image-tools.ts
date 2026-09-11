import { Type } from "@earendil-works/pi-ai";
import { defineTool, type ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { basename, extname, relative, resolve } from "node:path";

const DEFAULT_BASE_URL = "https://token.sensenova.cn";
const DEFAULT_MODEL = "sensenova-u1.5-lite";
const DEFAULT_TIMEOUT_MS = 120_000;
const OUTPUT_FORMATS = ["png", "jpeg", "webp"] as const;
type OutputFormat = (typeof OUTPUT_FORMATS)[number];

type ImageRequest = {
  prompt: string;
  provider?: string;
  size?: string;
  output_format?: OutputFormat;
  watermark?: boolean;
  prompt_extend?: boolean;
};

type ImageOutput = { data: string; mimeType: string; provider: string; model: string };

interface ImageProvider {
  readonly id: string;
  generate(request: ImageRequest, signal?: AbortSignal): Promise<ImageOutput>;
  edit(request: ImageRequest & { imagePath: string }, signal?: AbortSignal): Promise<ImageOutput>;
}

class ImageProviderRegistry {
  constructor(
    private readonly providers: ImageProvider[],
    private readonly autoProviderId: string,
  ) {}

  resolve(id = "auto"): ImageProvider {
    const providerId = id === "auto" ? this.autoProviderId : id;
    const provider = this.providers.find((item) => item.id === providerId);
    if (!provider) throw new Error(`Unsupported image provider: ${id}`);
    return provider;
  }
}

class SenseNovaImageProvider implements ImageProvider {
  readonly id = "sensenova";
  private readonly apiKey = process.env.SENSENOVA_API_KEY?.trim();
  private readonly baseUrl = (process.env.SENSENOVA_BASE_URL?.trim() || DEFAULT_BASE_URL).replace(/\/+$/, "");
  private readonly model = process.env.SENSENOVA_IMAGE_MODEL?.trim() || DEFAULT_MODEL;

  generate(request: ImageRequest, signal?: AbortSignal): Promise<ImageOutput> {
    return this.request("/v1/images/generations", request, signal);
  }

  edit(request: ImageRequest & { imagePath: string }, signal?: AbortSignal): Promise<ImageOutput> {
    const input = readWorkspaceImage(request.imagePath);
    return this.request(
      "/v1/images/edits",
      { ...request, images: [{ image_url: `data:${input.mimeType};base64,${input.data}` }] },
      signal,
    );
  }

  private async request(
    endpoint: string,
    request: ImageRequest & Record<string, unknown>,
    signal?: AbortSignal,
  ): Promise<ImageOutput> {
    if (!this.apiKey) throw new Error("SENSENOVA_API_KEY is not configured");
    const timeout = new AbortController();
    const timer = setTimeout(() => timeout.abort(), DEFAULT_TIMEOUT_MS);
    try {
      const response = await fetch(`${this.baseUrl}${endpoint}`, {
        method: "POST",
        headers: { authorization: `Bearer ${this.apiKey}`, "content-type": "application/json" },
        body: JSON.stringify({
          model: this.model,
          prompt: request.prompt,
          n: 1,
          size: request.size || "auto",
          output_format: request.output_format || "png",
          response_format: "b64_json",
          watermark: request.watermark ?? environmentBoolean("SENSENOVA_WATERMARK", true),
          prompt_extend: request.prompt_extend ?? environmentBoolean("SENSENOVA_PROMPT_EXTEND", true),
          ...(endpoint.endsWith("/edits") ? { images: request.images } : {}),
        }),
        signal: mergeSignals(signal, timeout.signal),
      });
      const text = await response.text();
      if (!response.ok) throw new Error(`SenseNova request failed (${response.status}): ${text.slice(0, 300)}`);
      const payload = JSON.parse(text) as { data?: Array<{ b64_json?: string }> };
      const data = payload.data?.[0]?.b64_json;
      if (!data) throw new Error("SenseNova response did not contain image data");
      return { data, mimeType: `image/${request.output_format || "png"}`, provider: this.id, model: this.model };
    } finally {
      clearTimeout(timer);
    }
  }
}

const registry = new ImageProviderRegistry([new SenseNovaImageProvider()], "sensenova");
const sharedParameters = {
  prompt: Type.String({ minLength: 1, description: "Describe the desired final image." }),
  provider: Type.Optional(
    Type.String({ description: "Image strategy. Use auto unless a configured provider is explicitly required." }),
  ),
  size: Type.Optional(
    Type.String({
      description: "Output size. Defaults to auto; dimensions must be supported by the selected provider.",
    }),
  ),
  output_format: Type.Optional(Type.String({ enum: OUTPUT_FORMATS })),
  watermark: Type.Optional(Type.Boolean()),
  prompt_extend: Type.Optional(Type.Boolean()),
};

const generateImageTool = defineTool({
  name: "generate_image",
  label: "Generate Image",
  description: "Generate a durable image file with the configured image provider.",
  promptSnippet: "generate_image: create a new image when the user asks for one.",
  parameters: Type.Object(sharedParameters),
  async execute(_toolCallId, params, signal, _onUpdate, ctx) {
    const output = await registry.resolve(params.provider).generate(params, signal);
    const path = writeChatImage(ctx.sessionManager.getSessionId(), output.data, params.output_format);
    return imageToolResult(path, output);
  },
});

const editImageTool = defineTool({
  name: "edit_image",
  label: "Edit Image",
  description: "Edit a user-uploaded or previously generated image from this chat and save a new image file.",
  promptSnippet:
    "edit_image: modify an image only when the user supplied it in this chat or it was previously generated here.",
  parameters: Type.Object({
    ...sharedParameters,
    image_path: Type.String({
      description: "The relative path of a current-chat upload or image previously generated in this chat.",
    }),
  }),
  async execute(_toolCallId, params, signal, _onUpdate, ctx) {
    const sessionId = ctx.sessionManager.getSessionId();
    const sourcePath = authorizedSourcePath(params.image_path, sessionId, ctx.sessionManager.getSessionFile());
    const output = await registry.resolve(params.provider).edit({ ...params, imagePath: sourcePath }, signal);
    const path = writeChatImage(sessionId, output.data, params.output_format);
    return imageToolResult(path, output);
  },
});

export default function (pi: ExtensionAPI) {
  pi.registerTool(generateImageTool);
  pi.registerTool(editImageTool);
}

function imageToolResult(path: string, output: ImageOutput) {
  return {
    content: [
      { type: "text", text: `Saved image: ${path}` },
      { type: "image", data: output.data, mimeType: output.mimeType },
    ],
    details: { path, provider: output.provider, model: output.model, mimeType: output.mimeType },
  };
}

function authorizedSourcePath(path: string, sessionId: string, sessionFile: string | undefined): string {
  const resolved = workspacePath(path);
  const relativePath = relative(resolve(process.cwd()), resolved);
  if (relativePath.startsWith(`uploads/${sessionId}/`)) return resolved;
  if (
    relativePath.startsWith(`generated/${sessionId}/`) &&
    sessionFile &&
    generatedPaths(sessionFile).has(relativePath)
  ) {
    return resolved;
  }
  throw new Error("Image source must be an upload or generated image from the current chat");
}

function generatedPaths(sessionFile: string): Set<string> {
  const paths = new Set<string>();
  for (const line of readFileSync(sessionFile, "utf8").split("\n")) {
    try {
      const entry = JSON.parse(line) as {
        message?: {
          role?: string;
          toolName?: string;
          details?: { path?: unknown };
          content?: Array<{
            type?: string;
            name?: string;
            arguments?: { path?: unknown };
          }>;
        };
      };
      const message = entry.message;
      if (
        message?.role === "toolResult" &&
        ["generate_image", "edit_image"].includes(message.toolName || "") &&
        typeof message.details?.path === "string"
      ) {
        paths.add(message.details.path);
      }
    } catch {
      /* Ignore malformed session lines. */
    }
  }
  return paths;
}

function workspacePath(path: string): string {
  const root = resolve(process.cwd());
  const resolved = resolve(root, path.trim());
  const workspacePath = relative(root, resolved);
  if (!workspacePath || workspacePath.startsWith("..") || workspacePath.includes(".." + "/"))
    throw new Error("Image path must resolve inside the workspace");
  return resolved;
}

function readWorkspaceImage(path: string): { data: string; mimeType: string } {
  const mimeType = imageMimeType(path);
  if (!mimeType) throw new Error("Source file must be a PNG, JPEG, WebP, GIF, or AVIF image");
  return { data: readFileSync(path).toString("base64"), mimeType };
}

function writeChatImage(sessionId: string, data: string, format: OutputFormat | undefined): string {
  const outputFormat = format || "png";
  const relativePath = `generated/${sessionId}/${Date.now()}-${Math.random().toString(36).slice(2, 10)}.${outputFormat}`;
  const resolved = workspacePath(relativePath);
  mkdirSync(resolve(resolved, ".."), { recursive: true });
  writeFileSync(resolved, Buffer.from(data, "base64"), { flag: "wx" });
  return relativePath;
}

function imageMimeType(path: string): string | null {
  switch (extname(basename(path)).toLowerCase()) {
    case ".png":
      return "image/png";
    case ".jpg":
    case ".jpeg":
      return "image/jpeg";
    case ".webp":
      return "image/webp";
    case ".gif":
      return "image/gif";
    case ".avif":
      return "image/avif";
    default:
      return null;
  }
}

function environmentBoolean(name: string, fallback: boolean): boolean {
  const raw = process.env[name];
  return raw === undefined ? fallback : ["1", "true", "yes", "on"].includes(raw.toLowerCase());
}

function mergeSignals(first: AbortSignal | undefined, second: AbortSignal): AbortSignal {
  if (!first) return second;
  const controller = new AbortController();
  const abort = () => controller.abort();
  first.addEventListener("abort", abort, { once: true });
  second.addEventListener("abort", abort, { once: true });
  return controller.signal;
}
