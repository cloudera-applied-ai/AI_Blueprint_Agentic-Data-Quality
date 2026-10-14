import { useState, useCallback } from "react";

/**
 * Generic hook for SSE endpoints that emit structured data + LLM analysis.
 *
 * @param dataEventName  The SSE event name carrying the structured JSON
 *                       (e.g. "issues_data", "profile_data", "flow_data").
 */
export function useAnalysisStream<T>(dataEventName: string) {
  const [structuredData, setStructuredData] = useState<T | null>(null);
  const [analysisText, setAnalysisText] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runAnalysis = useCallback(
    async (stream: AsyncGenerator<{ event: string; data: Record<string, unknown> }>) => {
      setIsStreaming(true);
      setAnalysisText("");
      setError(null);
      setStructuredData(null);

      try {
        for await (const evt of stream) {
          switch (evt.event) {
            case dataEventName:
              setStructuredData(evt.data as unknown as T);
              break;
            case "content":
              setAnalysisText(evt.data.text as string);
              break;
            case "error":
              setError(evt.data.message as string);
              break;
            case "done":
              break;
          }
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setIsStreaming(false);
      }
    },
    [dataEventName],
  );

  return { structuredData, analysisText, isStreaming, error, runAnalysis };
}
