import { adminUpstream, validAdmin, sameOriginMutation } from "../../../../lib/admin-access";

async function handle(request: Request, context: { params: Promise<{path: string[]}> }) {
  if (!validAdmin(request.headers.get("authorization"))) return Response.json({detail:"需要管理员身份"}, {status:401});
  if (request.method !== "GET" && !sameOriginMutation(request)) return Response.json({detail:"跨站请求已拒绝"}, {status:403});
  const upstream=adminUpstream((await context.params).path.join("/"), request.method);
  if (!upstream) return Response.json({detail:"管理接口不存在"}, {status:404});
  const base=process.env.ADMIN_API_BASE || "http://127.0.0.1:8011/api/v1";
  try {
    const response=await fetch(base+upstream, {method:request.method, cache:"no-store", redirect:"error", signal:AbortSignal.timeout(10000),
      headers:{"Authorization":`Bearer ${process.env.ADMIN_API_TOKEN}`,"Content-Type":"application/json"},
      body:request.method==="GET"?undefined:await request.text()});
    return new Response(await response.text(), {status:response.status, headers:{"Content-Type":"application/json", "Cache-Control":"no-store"}});
  } catch { return Response.json({detail:"后台服务暂时不可用，请检查 API 与后台密钥配置"}, {status:502}); }
}
export { handle as GET, handle as POST };
