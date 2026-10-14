/**
 * Reusable SSE stream parser.
 * Opens a POST request and yields { event, data } objects as they arrive.
 */
export async function* streamSSE(
  url: string,
  body: unknown,
): AsyncGenerator<{ event: string; data: Record<string, unknown> }> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    throw new Error(await res.text());
  }

  const reader = res.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";
  let currentEvent = "message";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (line.startsWith("event:")) {
        currentEvent = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        const dataStr = line.slice(5).trim();
        if (dataStr) {
          try {
            yield { event: currentEvent, data: JSON.parse(dataStr) };
          } catch {
            // skip malformed JSON
          }
          currentEvent = "message";
        }
      }
    }
  }
}
