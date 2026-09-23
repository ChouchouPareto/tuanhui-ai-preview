import { redirect } from "next/navigation";
export default async function LegacyEditor({searchParams}:{searchParams:Promise<Record<string,string|string[]|undefined>>}) {
  const params=await searchParams;
  const query=new URLSearchParams();
  for (const key of ["project","task"]) if(typeof params[key]==="string") query.set(key,params[key]);
  redirect(`/editor?${query}`);
}
