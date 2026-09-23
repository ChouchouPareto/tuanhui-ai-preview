export async function adminRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response=await fetch(`/api/internal${path}`, {...init, cache:"no-store"});
  const body=await response.json();
  if (!response.ok) throw new Error(typeof body.detail==="string"?body.detail:"后台请求失败");
  return body;
}
