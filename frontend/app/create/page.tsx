import { redirect } from "next/navigation";
import { originalCreationUrl } from "../../lib/creation-entry";

export default async function CreationCompatibility({ searchParams }: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  redirect(originalCreationUrl(await searchParams));
}
