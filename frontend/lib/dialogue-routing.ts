export type DialogueRoute = {
  schema_version: "dialogue-safety-v1";
  intent: string;
  action: "prepare" | "answer" | "clarify" | "cancel";
  can_prepare: boolean;
  reply: string;
  next_steps: string[];
  duration_ms: number;
};
export type DialogueMessage = { id: string; text: string; response: DialogueRoute };

export function mayPrepare(route: DialogueRoute): boolean {
  return route?.schema_version === "dialogue-safety-v1" && route.can_prepare === true
    && route.action === "prepare" && ["new_creation", "edit_copy"].includes(route.intent);
}

export function dialogueTarget(projectId: string, search: string) {
  const params = new URLSearchParams(search);
  const fresh = params.get("compose") === "1";
  return { project_id: projectId || null, creation_id: fresh ? null : params.get("creation"), task_id: fresh ? null : params.get("task") };
}
