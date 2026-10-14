import { useState, useCallback, useRef } from "react";
import { streamPipeline } from "../api/client";
import type { PipelineStage, ColumnProfile, QualityIssue, DataQualityRule } from "../types";

export function usePipeline() {
  const [currentStage, setCurrentStage] = useState<PipelineStage | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [profiles, setProfiles] = useState<ColumnProfile[]>([]);
  const [issues, setIssues] = useState<QualityIssue[]>([]);
  const [rules, setRules] = useState<DataQualityRule[]>([]);
  const [schemaText, setSchemaText] = useState("");
  const [completedStages, setCompletedStages] = useState<Set<string>>(new Set());
  const [generatedNifiId, setGeneratedNifiId] = useState<string | null>(null);
  const [generatedSparkId, setGeneratedSparkId] = useState<string | null>(null);
  const [generatedMetadataId, setGeneratedMetadataId] = useState<string | null>(null);
  const [generatedClassificationId, setGeneratedClassificationId] = useState<string | null>(null);
  const abortRef = useRef(false);

  const startPipeline = useCallback(async () => {
    // Reset state
    setCurrentStage(null);
    setIsRunning(true);
    setError(null);
    setProfiles([]);
    setIssues([]);
    setRules([]);
    setSchemaText("");
    setCompletedStages(new Set());
    setGeneratedNifiId(null);
    setGeneratedSparkId(null);
    setGeneratedMetadataId(null);
    setGeneratedClassificationId(null);
    abortRef.current = false;

    try {
      for await (const event of streamPipeline()) {
        if (abortRef.current) break;

        switch (event.event) {
          case "stage": {
            const stage = event.data as unknown as PipelineStage;
            setCurrentStage(stage);
            if (stage.status === "completed" || stage.status === "skipped") {
              setCompletedStages((prev) => new Set([...prev, stage.stage]));
            }
            break;
          }

          case "profile_result":
            setProfiles((prev) => [...prev, event.data as unknown as ColumnProfile]);
            break;

          case "issues_data":
            setIssues(event.data as unknown as QualityIssue[]);
            break;

          case "schema_content": {
            const text = (event.data as { text?: string }).text || "";
            setSchemaText(text);
            break;
          }

          case "rules_data":
            setRules(event.data as unknown as DataQualityRule[]);
            break;

          case "nifi_generated": {
            const nifiData = event.data as { flow_id?: string };
            if (nifiData.flow_id) setGeneratedNifiId(nifiData.flow_id);
            break;
          }

          case "spark_generated": {
            const sparkData = event.data as { job_id?: string };
            if (sparkData.job_id) setGeneratedSparkId(sparkData.job_id);
            break;
          }

          case "metadata_generated": {
            const metaData = event.data as { meta_id?: string };
            if (metaData.meta_id) setGeneratedMetadataId(metaData.meta_id);
            break;
          }

          case "classification_generated": {
            const clfData = event.data as { classification_id?: string };
            if (clfData.classification_id) setGeneratedClassificationId(clfData.classification_id);
            break;
          }

          case "error":
            setError((event.data as { message?: string }).message || "Pipeline error");
            setIsRunning(false);
            return;

          case "done":
            setIsRunning(false);
            return;
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsRunning(false);
    }
  }, []);

  const updateRule = useCallback((id: number, updates: Partial<DataQualityRule>) => {
    setRules((prev) =>
      prev.map((r) => (r.id === id ? { ...r, ...updates } : r))
    );
  }, []);

  const toggleRule = useCallback((id: number) => {
    setRules((prev) =>
      prev.map((r) => (r.id === id ? { ...r, enabled: !r.enabled } : r))
    );
  }, []);

  const toggleAllRules = useCallback((enabled: boolean) => {
    setRules((prev) => prev.map((r) => ({ ...r, enabled })));
  }, []);

  const getEnabledRules = useCallback(() => {
    return rules.filter((r) => r.enabled);
  }, [rules]);

  const reset = useCallback(() => {
    abortRef.current = true;
    setCurrentStage(null);
    setIsRunning(false);
    setError(null);
    setProfiles([]);
    setIssues([]);
    setRules([]);
    setSchemaText("");
    setCompletedStages(new Set());
    setGeneratedNifiId(null);
    setGeneratedSparkId(null);
    setGeneratedMetadataId(null);
    setGeneratedClassificationId(null);
  }, []);

  return {
    currentStage,
    isRunning,
    error,
    profiles,
    issues,
    rules,
    schemaText,
    completedStages,
    generatedNifiId,
    generatedSparkId,
    generatedMetadataId,
    generatedClassificationId,
    startPipeline,
    updateRule,
    toggleRule,
    toggleAllRules,
    getEnabledRules,
    reset,
  };
}
