export type CreationEntry = "oneclick" | "professional" | "fullplan";

export function entryPath(entry?: string) {
  return entry === "professional" ? "/professional" : entry === "fullplan" ? "/full-plan" : "/";
}

/** Compatibility links only carry identifiers; navigation must never execute a task. */
export function originalCreationUrl(values: Record<string, string | string[] | undefined>) {
  const entry = typeof values.entry === "string" ? values.entry : "oneclick";
  const params = new URLSearchParams();
  for (const key of ["project", "creation", "task", "run", "compose"]) {
    const value = values[key];
    if (typeof value === "string" && value) params.set(key, value);
  }
  return entryPath(entry) + (params.size ? `?${params}` : "");
}
