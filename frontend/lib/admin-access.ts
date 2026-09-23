// Server-only callers: proxy and route handlers. Never import from client components.
import { createHash, timingSafeEqual } from "node:crypto";

export function adminConfigured(env: NodeJS.ProcessEnv = process.env): boolean {
  return env.TUANHUI_ADMIN_ENABLED === "1" && (env.ADMIN_API_TOKEN || "").length >= 32;
}

export function validAdmin(authorization: string | null, env: NodeJS.ProcessEnv = process.env): boolean {
  if (!adminConfigured(env) || !authorization?.startsWith("Basic ")) return false;
  const supplied = Buffer.from(authorization.slice(6), "base64").toString("utf8");
  const expected = `admin:${env.ADMIN_API_TOKEN}`;
  return timingSafeEqual(createHash("sha256").update(supplied).digest(), createHash("sha256").update(expected).digest());
}

export function adminUpstream(path: string, method: string): string | null {
  if (method === "GET" && path === "contracts") return "/agent/contracts";
  if (method === "GET" && path === "templates") return "/templates/reviews";
  if (method === "POST" && /^templates\/L\d{2}\/review$/.test(path)) return `/${path}`;
  return null;
}

export function sameOriginMutation(request: Request): boolean {
  return request.headers.get("origin") === new URL(request.url).origin;
}
