/** Log execution metadata, never tool arguments, prompts, or credentials. */
export function safeError(error: unknown): string {
  let message = error instanceof Error ? error.message : String(error);
  for (const [name, value] of Object.entries(process.env)) {
    if (value && /KEY|TOKEN|SECRET|PASSWORD/i.test(name)) {
      message = message.split(value).join("[redacted]");
    }
  }
  return message
    .replace(/Bearer\s+\S+/gi, "Bearer [redacted]")
    .replace(/https?:\/\/[^\s]+/g, "[URL]")
    .slice(0, 600);
}

export function logChannel(stage: string, fields: Record<string, unknown> = {}) {
  console.info("[trip-planner]", JSON.stringify({ time: new Date().toISOString(), stage, ...fields }));
}
