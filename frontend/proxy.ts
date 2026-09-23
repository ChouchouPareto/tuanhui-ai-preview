import { NextRequest, NextResponse } from "next/server";
import { adminConfigured, validAdmin, sameOriginMutation } from "./lib/admin-access";

export function proxy(request: NextRequest) {
  // This historical URL is a customer editor, not an administrative action.
  if (request.nextUrl.pathname === "/workbench/editor") {
    const target=request.nextUrl.clone();target.pathname="/editor";
    return NextResponse.redirect(target);
  }
  if (!adminConfigured()) return new NextResponse("内部后台未启用，请通过独立后台端口访问。", { status: 503, headers: { "Cache-Control": "no-store" } });
  if (!validAdmin(request.headers.get("authorization"))) return new NextResponse("仅限内部管理员访问", {
    status: 401, headers: { "WWW-Authenticate": 'Basic realm="Tuanhui internal", charset="UTF-8"', "Cache-Control": "no-store" },
  });
  if (!["GET", "HEAD"].includes(request.method) && !sameOriginMutation(request)) return new NextResponse("跨站管理请求已拒绝", { status: 403 });
  const response=NextResponse.next();
  response.headers.set("Cache-Control", "no-store");
  response.headers.set("X-Robots-Tag", "noindex, nofollow");
  response.headers.set("X-Frame-Options", "DENY");
  return response;
}
export const config = { matcher: ["/workbench/:path*", "/api/internal/:path*"] };
