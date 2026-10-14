import { useState } from "react";
import { generateSchema } from "../api/client";
import type { PipelineStage, ColumnProfile, QualityIssue, DataQualityRule } from "../types";

interface PipelineViewProps {
  currentStage: PipelineStage | null;
  isRunning: boolean;
  error: string | null;
  profiles: ColumnProfile[];
  issues: QualityIssue[];
  rules: DataQualityRule[];
  schemaText: string;
  completedStages: Set<string>;
  onToggleRule: (id: number) => void;
  onToggleAllRules: (enabled: boolean) => void;
  onUpdateRule: (id: number, updates: Partial<DataQualityRule>) => void;
  onSwitchToNiFi: () => void;
  onSwitchToSpark: () => void;
  onSwitchToMetadata: () => void;
  onSwitchToClassification?: () => void;
  generatedNifiId: string | null;
  generatedSparkId: string | null;
  generatedMetadataId: string | null;
  generatedClassificationId?: string | null;
}

const STAGES = [
  { key: "profiling", label: "Profiling" },
  { key: "detecting", label: "Issues" },
  { key: "schema", label: "Schema" },
  { key: "rules", label: "Rules" },
  { key: "nifi_generation", label: "NiFi" },
  { key: "spark_generation", label: "Spark" },
  { key: "classification", label: "Classification" },
  { key: "metadata_generation", label: "Metadata" },
] as const;

const SEVERITY_ORDER = { critical: 0, high: 1, medium: 2, low: 3 };

export default function PipelineView({
  currentStage,
  isRunning,
  error,
  profiles,
  issues,
  rules,
  schemaText,
  completedStages,
  onToggleRule,
  onToggleAllRules,
  onUpdateRule,
  onSwitchToNiFi,
  onSwitchToSpark,
  onSwitchToMetadata,
  onSwitchToClassification,
  generatedNifiId,
  generatedSparkId,
  generatedMetadataId,
  generatedClassificationId,
}: PipelineViewProps) {
  // Output tabs
  const [activeOutputTab, setActiveOutputTab] = useState<"schema" | "rules">("schema");

  // Schema tab state
  const [schemaData, setSchemaData] = useState<{ json_schema: Record<string, unknown>; columns: Record<string, unknown>[] } | null>(null);
  const [schemaLoading, setSchemaLoading] = useState(false);
  const [tableName, setTableName] = useState("agt_member_eligibility");
  const [copySuccess, setCopySuccess] = useState(false);

  // Rules tab state
  const [editingRuleId, setEditingRuleId] = useState<number | null>(null);

  // Profiles collapsible
  const [profilesOpen, setProfilesOpen] = useState(false);

  const enabledCount = rules.filter((r) => r.enabled).length;
  const sortedRules = [...rules].sort(
    (a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity]
  );

  const pipelineDone = !isRunning && rules.length > 0;

  const handleGenerateSchema = async () => {
    setSchemaLoading(true);
    try {
      const data = await generateSchema(tableName || undefined);
      setSchemaData(data);
    } catch (err) {
      console.error("Schema generation failed:", err);
    } finally {
      setSchemaLoading(false);
    }
  };

  const handleDownload = (data: unknown, filename: string) => {
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleCopySchema = async () => {
    if (!schemaData) return;
    try {
      await navigator.clipboard.writeText(JSON.stringify(schemaData.json_schema, null, 2));
      setCopySuccess(true);
      setTimeout(() => setCopySuccess(false), 2000);
    } catch {
      // fallback
      const textarea = document.createElement("textarea");
      textarea.value = JSON.stringify(schemaData.json_schema, null, 2);
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
      setCopySuccess(true);
      setTimeout(() => setCopySuccess(false), 2000);
    }
  };

  const hasAnyArtifact = generatedNifiId || generatedSparkId || generatedMetadataId || generatedClassificationId;

  // No data yet state
  if (!isRunning && !currentStage && rules.length === 0 && profiles.length === 0) {
    return (
      <div className="pipeline-empty">
        <p>Load data to start the automated pipeline.</p>
      </div>
    );
  }

  return (
    <div className="pipeline-container">
      {/* Progress Tracker */}
      <div className="pipeline-progress">
        {STAGES.map((s, i) => {
          const isCompleted = completedStages.has(s.key);
          const isActive = currentStage?.stage === s.key && !isCompleted;
          let detail = "";

          if (s.key === "profiling" && currentStage?.stage === "profiling" && currentStage.status === "progress") {
            detail = `${currentStage.completed}/${currentStage.total}`;
          } else if (s.key === "detecting" && isCompleted) {
            detail = `${issues.length} found`;
          } else if (s.key === "rules" && isCompleted) {
            detail = `${rules.length} rules`;
          } else if (s.key === "nifi_generation" && isCompleted) {
            detail = generatedNifiId ? "saved" : "skipped";
          } else if (s.key === "spark_generation" && isCompleted) {
            detail = generatedSparkId ? "saved" : "skipped";
          } else if (s.key === "classification" && isCompleted) {
            detail = generatedClassificationId ? "saved" : "skipped";
          } else if (s.key === "metadata_generation" && isCompleted) {
            detail = generatedMetadataId ? "saved" : "skipped";
          }

          return (
            <div key={s.key} className="pipeline-step-wrapper">
              {i > 0 && <div className={`pipeline-connector ${isCompleted || isActive ? "active" : ""}`} />}
              <div className={`pipeline-step ${isActive ? "active" : ""} ${isCompleted ? "completed" : ""}`}>
                <span className="step-number">
                  {isCompleted ? "\u2713" : i + 1}
                </span>
                <span className="step-label">{s.label}</span>
                {detail && <span className="step-detail">{detail}</span>}
              </div>
            </div>
          );
        })}
      </div>

      {/* Error */}
      {error && <div className="pipeline-error">{error}</div>}

      {/* Content Area */}
      <div className="pipeline-content">
        {/* Running: show live progress */}
        {isRunning && currentStage && (
          <div className="pipeline-live">
            {currentStage.stage === "profiling" && (
              <p className="pipeline-status-text">
                Profiling columns... {currentStage.completed || 0}/{currentStage.total || "?"}
              </p>
            )}
            {currentStage.stage === "detecting" && (
              <p className="pipeline-status-text">Detecting quality issues...</p>
            )}
            {currentStage.stage === "schema" && (
              <p className="pipeline-status-text">Generating schema recommendation...</p>
            )}
            {currentStage.stage === "rules" && (
              <p className="pipeline-status-text">Deriving rules...</p>
            )}
            {currentStage.stage === "nifi_generation" && (
              <p className="pipeline-status-text">Generating NiFi flow...</p>
            )}
            {currentStage.stage === "spark_generation" && (
              <p className="pipeline-status-text">Generating Spark job...</p>
            )}
            {currentStage.stage === "metadata_generation" && (
              <p className="pipeline-status-text">Generating metadata YAML...</p>
            )}
          </div>
        )}

        {/* Schema streaming while running */}
        {isRunning && schemaText && (
          <div className="schema-panel open">
            <div className="schema-panel-header">
              <h4>Schema Recommendation (streaming...)</h4>
            </div>
            <div className="schema-panel-body">
              <pre className="schema-text">{schemaText}</pre>
            </div>
          </div>
        )}

        {/* Output Tabs (when pipeline is done) */}
        {pipelineDone && (
          <>
            <div className="pipeline-output-tabs">
              <button
                className={`pipeline-output-tab ${activeOutputTab === "schema" ? "active" : ""}`}
                onClick={() => setActiveOutputTab("schema")}
              >
                Schema & Download
              </button>
              <button
                className={`pipeline-output-tab ${activeOutputTab === "rules" ? "active" : ""}`}
                onClick={() => setActiveOutputTab("rules")}
              >
                Data Quality Rules ({rules.length})
              </button>
            </div>

            {/* === Schema & Download Tab === */}
            {activeOutputTab === "schema" && (
              <div className="schema-tab-content">
                {/* LLM Schema Recommendation — always visible */}
                <div className="schema-llm-section">
                  <h4>Schema Recommendation (LLM)</h4>
                  {schemaText ? (
                    <pre className="schema-text">{schemaText}</pre>
                  ) : (
                    <p className="text-dim">LLM analysis not available — LLM may not be configured.</p>
                  )}
                </div>

                {/* Generated Schema */}
                <div className="schema-generate-section">
                  <h4>Generated Schema</h4>
                  <div className="schema-generate-controls">
                    <label className="schema-table-label">
                      Table name:
                      <input
                        type="text"
                        value={tableName}
                        onChange={(e) => setTableName(e.target.value)}
                      />
                    </label>
                    <button
                      className="btn btn-primary"
                      onClick={handleGenerateSchema}
                      disabled={schemaLoading}
                    >
                      {schemaLoading ? "Generating..." : "Generate"}
                    </button>
                  </div>

                  {schemaData && (
                    <>
                      <pre className="schema-code">
                        {JSON.stringify(schemaData.json_schema, null, 2)}
                      </pre>
                      <div className="schema-actions">
                        <button
                          className="btn btn-secondary btn-sm"
                          onClick={() => handleDownload(schemaData.json_schema, `${tableName}_schema.json`)}
                        >
                          Download JSON Schema
                        </button>
                        <button
                          className="btn btn-secondary btn-sm"
                          onClick={() => handleDownload(schemaData.columns, `${tableName}_columns.json`)}
                        >
                          Download Column Defs
                        </button>
                        <button
                          className="btn btn-secondary btn-sm"
                          onClick={handleCopySchema}
                        >
                          {copySuccess ? "Copied!" : "Copy to Clipboard"}
                        </button>
                      </div>
                    </>
                  )}
                </div>
              </div>
            )}

            {/* === Data Quality Rules Tab === */}
            {activeOutputTab === "rules" && (
              <div className="rules-panel">
                <div className="rules-header">
                  <h3>Data Quality Rules</h3>
                  <span className="rules-summary">
                    {enabledCount} of {rules.length} rules enabled
                  </span>
                  <div className="rules-bulk-actions">
                    <button className="btn btn-sm btn-secondary" onClick={() => onToggleAllRules(true)}>
                      Enable All
                    </button>
                    <button className="btn btn-sm btn-secondary" onClick={() => onToggleAllRules(false)}>
                      Disable All
                    </button>
                  </div>
                </div>

                <div className="rules-list">
                  {sortedRules.map((rule) => (
                    <div key={rule.id} className={`pipeline-rule-card ${rule.enabled ? "" : "disabled"}`}>
                      <div
                        className="rule-toggle-row"
                        onClick={() => setEditingRuleId(editingRuleId === rule.id ? null : rule.id)}
                      >
                        <label className="toggle-switch" onClick={(e) => e.stopPropagation()}>
                          <input
                            type="checkbox"
                            checked={rule.enabled}
                            onChange={() => onToggleRule(rule.id)}
                          />
                          <span className="toggle-slider"></span>
                        </label>
                        <span className={`severity-badge ${rule.severity}`}>{rule.severity}</span>
                        <span className="rule-field">{rule.field_name}</span>
                        <span className="rule-issue-type">{rule.issue_type.replace(/_/g, " ")}</span>
                        <span className="rule-pct">{rule.affected_pct}%</span>
                        <span className="rule-expand-icon">
                          {editingRuleId === rule.id ? "\u25BE" : "\u25B8"}
                        </span>
                      </div>

                      {/* Expanded edit form */}
                      {editingRuleId === rule.id && (
                        <div className="rule-edit-inline">
                          <div className="rule-edit-row">
                            <label>
                              Field Name
                              <input
                                type="text"
                                value={rule.field_name}
                                onChange={(e) => onUpdateRule(rule.id, { field_name: e.target.value })}
                              />
                            </label>
                            <label>
                              Severity
                              <select
                                value={rule.severity}
                                onChange={(e) => onUpdateRule(rule.id, { severity: e.target.value as DataQualityRule["severity"] })}
                              >
                                <option value="critical">Critical</option>
                                <option value="high">High</option>
                                <option value="medium">Medium</option>
                                <option value="low">Low</option>
                              </select>
                            </label>
                          </div>
                          <label>
                            Description
                            <textarea
                              value={rule.description}
                              onChange={(e) => onUpdateRule(rule.id, { description: e.target.value })}
                              rows={2}
                            />
                          </label>
                          <label>
                            Suggested Fix
                            <textarea
                              value={rule.suggested_fix}
                              onChange={(e) => onUpdateRule(rule.id, { suggested_fix: e.target.value })}
                              rows={2}
                            />
                          </label>
                          {rule.sample_bad_values.length > 0 && (
                            <div className="rule-samples">
                              <span className="text-dim">Samples:</span>
                              {rule.sample_bad_values.map((v, i) => (
                                <code key={i}>{v}</code>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}

        {/* Column Profiles (collapsible, when done) */}
        {!isRunning && profiles.length > 0 && (
          <div className={`schema-panel ${profilesOpen ? "open" : ""}`}>
            <button className="schema-panel-header" onClick={() => setProfilesOpen(!profilesOpen)}>
              <h4>{profilesOpen ? "\u25BE" : "\u25B8"} Column Profiles ({profiles.length})</h4>
            </button>
            {profilesOpen && (
              <div className="schema-panel-body">
                <div className="profile-grid">
                  {profiles.map((p) => (
                    <div key={p.field_name} className="profile-mini-card">
                      <div className="mini-card-header">{p.field_name}</div>
                      <div className="mini-card-stats">
                        <span>Distinct: {p.distinct_count}</span>
                        <span>Nulls: {p.null_pct}%</span>
                        <span>MaxLen: {p.max_length}</span>
                      </div>
                      {p.top_values.slice(0, 3).map((tv, i) => (
                        <div key={i} className="mini-card-value">
                          {tv.value} ({tv.count})
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Generated Artifacts Bar (sticky bottom) */}
      {pipelineDone && hasAnyArtifact && (
        <div className="deploy-bar">
          <span style={{ fontSize: 13, fontWeight: 600 }}>Generated Artifacts:</span>
          {generatedNifiId && (
            <button className="btn btn-sm btn-secondary" onClick={onSwitchToNiFi}>
              NiFi Flow
            </button>
          )}
          {generatedSparkId && (
            <button className="btn btn-sm btn-secondary" onClick={onSwitchToSpark}>
              Spark Job
            </button>
          )}
          {generatedMetadataId && (
            <button className="btn btn-sm btn-secondary" onClick={onSwitchToMetadata}>
              Metadata YAML
            </button>
          )}
          {generatedClassificationId && onSwitchToClassification && (
            <button className="btn btn-sm btn-secondary" onClick={onSwitchToClassification}>
              Classification
            </button>
          )}
        </div>
      )}
    </div>
  );
}
