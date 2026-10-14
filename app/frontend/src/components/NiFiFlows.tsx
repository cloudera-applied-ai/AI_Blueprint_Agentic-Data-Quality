import { useState, useEffect, useCallback } from "react";
import {
  detectNiFiIssues,
  generateNiFiFlow,
  streamNiFiDesign,
  listSavedFlows,
  saveNewFlow,
  getSavedFlow,
  getSavedFlowVersion,
  updateSavedFlow,
  deleteSavedFlow,
  cloneSavedFlow,
  getColumns,
} from "../api/client";
import { useAnalysisStream } from "../hooks/useAnalysisStream";
import type { QualityIssue, NiFiFlowResult, SavedFlowEntry, SavedFlowDetail, ColumnMeta } from "../types";

type SubTab = "generate" | "saved" | "editor";

const ISSUE_TYPES = [
  "invalid_code_value",
  "invalid_phone_number",
  "length_violation",
  "data_in_blank_field",
  "format_mismatch",
  "corrupted_data",
  "custom",
];

interface ProcessorInfo {
  name: string;
  type: string;
}

interface ConnectionInfo {
  sourceName: string;
  destName: string;
  relationships: string[];
}

function extractFlowSummary(flowObj: Record<string, unknown> | null): {
  processors: ProcessorInfo[];
  connections: ConnectionInfo[];
} | null {
  if (!flowObj) return null;
  const rootGroup = (flowObj.rootGroup || flowObj.flowContents) as Record<string, unknown> | undefined;
  if (!rootGroup) return null;

  const processors = (rootGroup.processors as Array<Record<string, unknown>> || []).map((p) => ({
    name: (p.name as string) || "?",
    type: ((p.type as string) || "?").split(".").pop() || "?",
  }));

  const procMap = new Map<string, string>();
  for (const p of rootGroup.processors as Array<Record<string, unknown>> || []) {
    procMap.set(p.identifier as string, p.name as string);
    if (p.instanceIdentifier) procMap.set(p.instanceIdentifier as string, p.name as string);
  }

  const connections = (rootGroup.connections as Array<Record<string, unknown>> || []).map((c) => {
    const src = c.source as Record<string, unknown> | undefined;
    const dest = c.destination as Record<string, unknown> | undefined;
    const srcId = (src?.id as string) || "";
    const destId = (dest?.id as string) || "";
    return {
      sourceName: procMap.get(srcId) || (src?.name as string) || "?",
      destName: procMap.get(destId) || (dest?.name as string) || "?",
      relationships: ((c.selectedRelationships as string[]) || []),
    };
  });

  return { processors, connections };
}

function FlowSummaryPanel({ flowObj, issues }: { flowObj: Record<string, unknown> | null; issues?: Array<Record<string, unknown>> }) {
  const summary = extractFlowSummary(flowObj);
  if (!summary) return <div className="text-dim">No flow data to display.</div>;

  return (
    <div className="flow-summary">
      <div className="flow-summary-section">
        <h4>Processors ({summary.processors.length})</h4>
        <div className="processor-list">
          {summary.processors.map((p, i) => (
            <div key={i} className="processor-item">
              <span className="processor-type-badge">{p.type}</span>
              <span className="processor-name">{p.name}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="flow-summary-section">
        <h4>Connections ({summary.connections.length})</h4>
        <div className="connection-list">
          {summary.connections.map((c, i) => (
            <div key={i} className="connection-item">
              <span className="connection-src">{c.sourceName}</span>
              <span className="connection-arrow">&rarr;</span>
              <span className="connection-rel">[{c.relationships.join(", ")}]</span>
              <span className="connection-arrow">&rarr;</span>
              <span className="connection-dest">{c.destName}</span>
            </div>
          ))}
        </div>
      </div>

      {issues && issues.length > 0 && (
        <div className="flow-summary-section">
          <h4>Issues Addressed ({issues.length})</h4>
          <div className="flow-issues-list">
            {issues.map((iss, i) => (
              <div key={i} className="flow-issue-item">
                <span className={`issue-type ${(iss.issue_type as string) || ""}`}>
                  {((iss.issue_type as string) || "").replace(/_/g, " ")}
                </span>
                <span className="issue-field">{iss.field_name as string}</span>
                <span className="issue-pct">{iss.affected_pct as number}%</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function emptyRule(): QualityIssue {
  return {
    field_name: "",
    issue_type: "custom",
    description: "",
    affected_count: 0,
    affected_pct: 0,
    sample_bad_values: [],
    suggested_fix: "",
    params: {},
  };
}

export default function NiFiFlows({ focusId }: { focusId?: string | null }) {
  const [subTab, setSubTab] = useState<SubTab>(focusId ? "saved" : "generate");

  // ----- Generate tab state -----
  const [rules, setRules] = useState<QualityIssue[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [flowJson, setFlowJson] = useState<string>("");
  const [flowResult, setFlowResult] = useState<NiFiFlowResult | null>(null);
  const [flowName, setFlowName] = useState("Data Quality Remediation");
  const [loading, setLoading] = useState("");
  const [issuesLoaded, setIssuesLoaded] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState("");
  const [genView, setGenView] = useState<"summary" | "json">("summary");
  const designAnalysis = useAnalysisStream<NiFiFlowResult>("flow_data");

  // Rule editing state
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
  const [showAddForm, setShowAddForm] = useState(false);
  const [addForm, setAddForm] = useState<QualityIssue>(emptyRule());
  const [columns, setColumns] = useState<ColumnMeta[]>([]);

  // ----- Saved flows tab state -----
  const [savedFlows, setSavedFlows] = useState<SavedFlowEntry[]>([]);
  const [savedLoading, setSavedLoading] = useState(false);
  const [savedError, setSavedError] = useState("");

  // ----- Editor tab state -----
  const [editDetail, setEditDetail] = useState<SavedFlowDetail | null>(null);
  const [editName, setEditName] = useState("");
  const [editJson, setEditJson] = useState("");
  const [editNote, setEditNote] = useState("");
  const [editJsonError, setEditJsonError] = useState("");
  const [editSaving, setEditSaving] = useState(false);
  const [editSuccess, setEditSuccess] = useState("");
  const [activeVersion, setActiveVersion] = useState<number>(0);
  const [editorView, setEditorView] = useState<"summary" | "json">("summary");

  // Auto-detect issues on mount
  useEffect(() => {
    if (!issuesLoaded) {
      setLoading("detecting");
      detectNiFiIssues()
        .then((issues) => {
          setRules(issues.map((i) => ({ ...i })));
          setSelected(new Set(issues.map((_, idx) => idx)));
          setIssuesLoaded(true);
        })
        .catch((e) => console.error("Issue detection failed:", e))
        .finally(() => setLoading(""));
    }
  }, [issuesLoaded]);

  // Load columns for the add-rule form
  useEffect(() => {
    getColumns()
      .then(setColumns)
      .catch(() => {});
  }, []);

  // Load saved flows
  const refreshSavedFlows = useCallback(() => {
    setSavedLoading(true);
    setSavedError("");
    listSavedFlows()
      .then(setSavedFlows)
      .catch((e) => {
        console.error("Failed to load saved flows:", e);
        setSavedError("Failed to load saved flows. Is data loaded?");
      })
      .finally(() => setSavedLoading(false));
  }, []);

  // Load on mount and when switching to saved tab
  useEffect(() => {
    refreshSavedFlows();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (subTab === "saved") refreshSavedFlows();
  }, [subTab, refreshSavedFlows]);

  // Auto-open editor when focusId is provided and flows are loaded
  useEffect(() => {
    if (focusId && savedFlows.length > 0 && !editDetail) {
      const match = savedFlows.find((f) => f.id === focusId);
      if (match) openEditor(match.id);
    }
  }, [focusId, savedFlows]); // eslint-disable-line react-hooks/exhaustive-deps

  // ----- Generate tab: rule management -----
  const toggleRule = (idx: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  };

  const toggleAll = () => {
    if (selected.size === rules.length) setSelected(new Set());
    else setSelected(new Set(rules.map((_, i) => i)));
  };

  const updateRule = (idx: number, patch: Partial<QualityIssue>) => {
    setRules((prev) => prev.map((r, i) => (i === idx ? { ...r, ...patch } : r)));
  };

  const deleteRule = (idx: number) => {
    setRules((prev) => prev.filter((_, i) => i !== idx));
    setSelected((prev) => {
      const next = new Set<number>();
      for (const s of prev) {
        if (s < idx) next.add(s);
        else if (s > idx) next.add(s - 1);
        // s === idx is removed
      }
      return next;
    });
    if (expandedIdx === idx) setExpandedIdx(null);
    else if (expandedIdx !== null && expandedIdx > idx) setExpandedIdx(expandedIdx - 1);
  };

  const addRule = () => {
    if (!addForm.field_name || !addForm.issue_type) return;
    const newRule: QualityIssue = { ...addForm };
    setRules((prev) => [...prev, newRule]);
    setSelected((prev) => new Set([...prev, rules.length]));
    setAddForm(emptyRule());
    setShowAddForm(false);
  };

  const selectedRules = (): QualityIssue[] => {
    return rules.filter((_, i) => selected.has(i));
  };

  // ----- Generate tab handlers -----
  const handleGenerate = async () => {
    setLoading("generating");
    try {
      const result = await generateNiFiFlow(flowName, selectedRules());
      setFlowResult(result);
      setFlowJson(JSON.stringify(result.flow, null, 2));
    } catch (e) {
      console.error(e);
    } finally {
      setLoading("");
    }
  };

  const handleDesign = () => {
    const stream = streamNiFiDesign(flowName, selectedRules());
    designAnalysis.runAnalysis(stream);
  };

  const flowData = designAnalysis.structuredData;
  const displayFlowJson = flowData ? JSON.stringify(flowData.flow, null, 2) : flowJson;
  const displayFlowObj = flowData ? flowData.flow : flowResult?.flow;
  const displayIssues = flowData ? flowData.issues : flowResult?.issues;

  const handleDownload = () => {
    const json = displayFlowJson;
    if (!json) return;
    const blob = new Blob([json], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${flowName.replace(/\s+/g, "_")}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleSaveFlow = async () => {
    if (!displayFlowObj) return;
    setSaveSuccess("");
    try {
      const issuesPayload = (displayIssues || []).map((iss) => ({ ...iss }));
      const rationale = designAnalysis.analysisText || null;
      await saveNewFlow(flowName, displayFlowObj as Record<string, unknown>, issuesPayload, rationale);
      setSaveSuccess("Saved! Switching to Saved Flows...");
      refreshSavedFlows();
      setTimeout(() => {
        setSaveSuccess("");
        setSubTab("saved");
      }, 1000);
    } catch (e) {
      console.error(e);
      setSaveSuccess("Failed to save flow.");
    }
  };

  // ----- Saved flows tab handlers -----
  const openEditor = async (id: string) => {
    try {
      const detail = await getSavedFlow(id);
      setEditDetail(detail);
      setEditName(detail.metadata.name);
      setEditJson(JSON.stringify(detail.flow_data.flow, null, 2));
      setEditNote("");
      setEditJsonError("");
      setEditSuccess("");
      setActiveVersion(detail.metadata.current_version);
      setSubTab("editor");
    } catch (e) {
      console.error(e);
    }
  };

  const handleCloneFromList = async (id: string) => {
    try {
      await cloneSavedFlow(id);
      refreshSavedFlows();
    } catch (e) {
      console.error(e);
    }
  };

  const handleDeleteFromList = async (id: string) => {
    if (!confirm("Delete this flow and all its versions?")) return;
    try {
      await deleteSavedFlow(id);
      refreshSavedFlows();
    } catch (e) {
      console.error(e);
    }
  };

  // ----- Editor tab handlers -----
  const handleEditorSave = async () => {
    if (!editDetail) return;
    try {
      JSON.parse(editJson);
    } catch {
      setEditJsonError("Invalid JSON");
      return;
    }
    setEditJsonError("");
    setEditSaving(true);
    setEditSuccess("");
    try {
      const parsedFlow = JSON.parse(editJson);
      const updated = await updateSavedFlow(editDetail.metadata.id, {
        name: editName,
        flow: parsedFlow,
        note: editNote || "Updated",
      });
      const detail = await getSavedFlow(updated.id);
      setEditDetail(detail);
      setActiveVersion(detail.metadata.current_version);
      setEditJson(JSON.stringify(detail.flow_data.flow, null, 2));
      setEditNote("");
      setEditSuccess("Changes saved (v" + detail.metadata.current_version + ")");
      setTimeout(() => setEditSuccess(""), 3000);
    } catch (e) {
      console.error(e);
      setEditSuccess("Failed to save changes.");
    } finally {
      setEditSaving(false);
    }
  };

  const handleEditorDownload = () => {
    if (!editJson || !editDetail) return;
    const blob = new Blob([editJson], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${editName.replace(/\s+/g, "_")}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleEditorClone = async () => {
    if (!editDetail) return;
    try {
      const cloned = await cloneSavedFlow(editDetail.metadata.id);
      const detail = await getSavedFlow(cloned.id);
      setEditDetail(detail);
      setEditName(detail.metadata.name);
      setEditJson(JSON.stringify(detail.flow_data.flow, null, 2));
      setActiveVersion(detail.metadata.current_version);
      setEditSuccess("Flow cloned!");
      setTimeout(() => setEditSuccess(""), 3000);
    } catch (e) {
      console.error(e);
    }
  };

  const handleEditorDelete = async () => {
    if (!editDetail) return;
    if (!confirm("Delete this flow and all its versions?")) return;
    try {
      await deleteSavedFlow(editDetail.metadata.id);
      setEditDetail(null);
      setSubTab("saved");
      refreshSavedFlows();
    } catch (e) {
      console.error(e);
    }
  };

  const loadVersion = async (version: number) => {
    if (!editDetail) return;
    try {
      const detail = await getSavedFlowVersion(editDetail.metadata.id, version);
      setEditJson(JSON.stringify(detail.flow_data.flow, null, 2));
      setActiveVersion(version);
      setEditJsonError("");
    } catch (e) {
      console.error(e);
    }
  };

  // ----- Render helpers -----
  const renderRuleRow = (rule: QualityIssue, idx: number) => {
    const isExpanded = expandedIdx === idx;
    const isSelected = selected.has(idx);

    return (
      <div key={idx} className={`rule-card ${isExpanded ? "expanded" : ""}`}>
        <div className="rule-row">
          <input
            type="checkbox"
            checked={isSelected}
            onChange={() => toggleRule(idx)}
          />
          <span className={`issue-type ${rule.issue_type}`}>
            {rule.issue_type.replace(/_/g, " ")}
          </span>
          <span className="issue-field">{rule.field_name}</span>
          {rule.affected_pct > 0 && (
            <span className="issue-pct">{rule.affected_pct}%</span>
          )}
          <span className="issue-desc-short">
            {rule.description.slice(0, 60)}
          </span>
          <div className="rule-row-actions">
            <button
              className="btn btn-sm btn-secondary"
              onClick={() => setExpandedIdx(isExpanded ? null : idx)}
              title={isExpanded ? "Collapse" : "Edit rule"}
            >
              {isExpanded ? "Done" : "Edit"}
            </button>
            <button
              className="btn btn-sm btn-danger"
              onClick={() => deleteRule(idx)}
              title="Remove rule"
            >
              &times;
            </button>
          </div>
        </div>

        {isExpanded && (
          <div className="rule-edit-panel">
            <div className="rule-edit-row">
              <label>
                Field:
                <select
                  value={rule.field_name}
                  onChange={(e) => updateRule(idx, { field_name: e.target.value })}
                >
                  <option value="">-- select --</option>
                  {columns.map((c) => (
                    <option key={c.field_name} value={c.field_name}>
                      {c.field_name}
                    </option>
                  ))}
                  {/* Keep current value if not in columns list */}
                  {rule.field_name && !columns.find((c) => c.field_name === rule.field_name) && (
                    <option value={rule.field_name}>{rule.field_name}</option>
                  )}
                </select>
              </label>
              <label>
                Issue Type:
                <select
                  value={rule.issue_type}
                  onChange={(e) => updateRule(idx, { issue_type: e.target.value })}
                >
                  {ISSUE_TYPES.map((t) => (
                    <option key={t} value={t}>
                      {t.replace(/_/g, " ")}
                    </option>
                  ))}
                  {!ISSUE_TYPES.includes(rule.issue_type) && (
                    <option value={rule.issue_type}>{rule.issue_type}</option>
                  )}
                </select>
              </label>
            </div>
            <label>
              Description:
              <input
                type="text"
                value={rule.description}
                onChange={(e) => updateRule(idx, { description: e.target.value })}
              />
            </label>
            <label>
              Suggested Fix:
              <input
                type="text"
                value={rule.suggested_fix}
                onChange={(e) => updateRule(idx, { suggested_fix: e.target.value })}
              />
            </label>
            {rule.issue_type === "invalid_code_value" && (
              <label>
                Valid Values (comma-separated):
                <input
                  type="text"
                  value={((rule.params?.valid_values as string[]) || []).join(", ")}
                  onChange={(e) => {
                    const vals = e.target.value
                      .split(",")
                      .map((v) => v.trim())
                      .filter(Boolean);
                    updateRule(idx, { params: { ...rule.params, valid_values: vals } });
                  }}
                  placeholder="e.g. M, F, U"
                />
              </label>
            )}
            {rule.issue_type === "length_violation" && (
              <label>
                Max Length:
                <input
                  type="number"
                  value={(rule.params?.max_length as number) || ""}
                  onChange={(e) =>
                    updateRule(idx, {
                      params: { ...rule.params, max_length: parseInt(e.target.value) || 0 },
                    })
                  }
                />
              </label>
            )}
            {rule.sample_bad_values && rule.sample_bad_values.length > 0 && (
              <div className="rule-samples">
                <span className="text-dim">Sample bad values: </span>
                {rule.sample_bad_values.map((v, i) => (
                  <code key={i}>{v}</code>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    );
  };

  const renderAddForm = () => (
    <div className="rule-add-form">
      <h4>Add Custom Rule</h4>
      <div className="rule-edit-row">
        <label>
          Field:
          <select
            value={addForm.field_name}
            onChange={(e) => setAddForm({ ...addForm, field_name: e.target.value })}
          >
            <option value="">-- select field --</option>
            {columns.map((c) => (
              <option key={c.field_name} value={c.field_name}>
                {c.field_name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Issue Type:
          <select
            value={addForm.issue_type}
            onChange={(e) => setAddForm({ ...addForm, issue_type: e.target.value })}
          >
            {ISSUE_TYPES.map((t) => (
              <option key={t} value={t}>
                {t.replace(/_/g, " ")}
              </option>
            ))}
          </select>
        </label>
      </div>
      <label>
        Description:
        <input
          type="text"
          value={addForm.description}
          onChange={(e) => setAddForm({ ...addForm, description: e.target.value })}
          placeholder="Describe the data quality issue..."
        />
      </label>
      <label>
        Suggested Fix:
        <input
          type="text"
          value={addForm.suggested_fix}
          onChange={(e) => setAddForm({ ...addForm, suggested_fix: e.target.value })}
          placeholder="How to remediate..."
        />
      </label>
      {addForm.issue_type === "invalid_code_value" && (
        <label>
          Valid Values (comma-separated):
          <input
            type="text"
            value={((addForm.params?.valid_values as string[]) || []).join(", ")}
            onChange={(e) => {
              const vals = e.target.value
                .split(",")
                .map((v) => v.trim())
                .filter(Boolean);
              setAddForm({ ...addForm, params: { ...addForm.params, valid_values: vals } });
            }}
            placeholder="e.g. M, F, U"
          />
        </label>
      )}
      {addForm.issue_type === "length_violation" && (
        <label>
          Max Length:
          <input
            type="number"
            value={(addForm.params?.max_length as number) || ""}
            onChange={(e) =>
              setAddForm({
                ...addForm,
                params: { ...addForm.params, max_length: parseInt(e.target.value) || 0 },
              })
            }
          />
        </label>
      )}
      <div className="rule-add-actions">
        <button
          className="btn btn-primary btn-sm"
          onClick={addRule}
          disabled={!addForm.field_name || !addForm.issue_type}
        >
          Add Rule
        </button>
        <button
          className="btn btn-secondary btn-sm"
          onClick={() => {
            setShowAddForm(false);
            setAddForm(emptyRule());
          }}
        >
          Cancel
        </button>
      </div>
    </div>
  );

  // ----- Render -----
  return (
    <div className="nifi-flows">
      <div className="nifi-sub-tabs">
        <button className={subTab === "generate" ? "active" : ""} onClick={() => setSubTab("generate")}>
          Generate
        </button>
        <button className={subTab === "saved" ? "active" : ""} onClick={() => setSubTab("saved")}>
          Saved Flows
        </button>
        {editDetail && (
          <button className={subTab === "editor" ? "active" : ""} onClick={() => setSubTab("editor")}>
            Editor
          </button>
        )}
      </div>

      {/* ===== GENERATE TAB ===== */}
      {subTab === "generate" && (
        <div className="nifi-generate-tab">
          <div className="nifi-config">
            <label>
              Flow Name:
              <input type="text" value={flowName} onChange={(e) => setFlowName(e.target.value)} />
            </label>
          </div>

          <div className="nifi-issues">
            <div className="nifi-issues-header">
              <h3>Rules ({rules.length})</h3>
              <div className="nifi-issues-header-actions">
                <button className="btn btn-sm" onClick={toggleAll}>
                  {selected.size === rules.length ? "Deselect All" : "Select All"}
                </button>
                <button
                  className="btn btn-sm btn-primary"
                  onClick={() => setShowAddForm(!showAddForm)}
                >
                  {showAddForm ? "Cancel" : "+ Add Rule"}
                </button>
              </div>
            </div>

            {loading === "detecting" && <div className="loading">Detecting issues...</div>}

            {rules.map((rule, i) => renderRuleRow(rule, i))}

            {!loading && rules.length === 0 && (
              <div className="text-dim" style={{ padding: 12 }}>
                No rules detected. Load data first or add rules manually.
              </div>
            )}

            {showAddForm && renderAddForm()}
          </div>

          <div className="nifi-actions">
            <button
              className="btn btn-primary"
              onClick={handleGenerate}
              disabled={selected.size === 0 || loading === "generating"}
            >
              {loading === "generating" ? "Generating..." : `Generate Flow (${selected.size} rules)`}
            </button>
            <button
              className="btn btn-primary btn-ai"
              onClick={handleDesign}
              disabled={selected.size === 0 || designAnalysis.isStreaming}
            >
              {designAnalysis.isStreaming ? "Designing..." : "Design with AI"}
            </button>
          </div>

          {/* AI Design Rationale panel */}
          {(designAnalysis.analysisText || designAnalysis.isStreaming || designAnalysis.error) && (
            <div className="ai-analysis-panel">
              <h4>AI Design Rationale</h4>
              {designAnalysis.error && <p className="analysis-error">{designAnalysis.error}</p>}
              {designAnalysis.analysisText && <div className="analysis-content">{designAnalysis.analysisText}</div>}
              {designAnalysis.isStreaming && !designAnalysis.analysisText && (
                <div className="loading">Waiting for LLM response...</div>
              )}
            </div>
          )}

          {(displayFlowJson || flowJson) && (
            <div className="nifi-output">
              <div className="nifi-output-header">
                <h3>Generated NiFi v2 Flow</h3>
                <div style={{ display: "flex", gap: 8 }}>
                  <div className="view-toggle">
                    <button className={`btn btn-sm ${genView === "summary" ? "btn-primary" : "btn-secondary"}`} onClick={() => setGenView("summary")}>
                      Summary
                    </button>
                    <button className={`btn btn-sm ${genView === "json" ? "btn-primary" : "btn-secondary"}`} onClick={() => setGenView("json")}>
                      JSON
                    </button>
                  </div>
                  <button className="btn btn-primary" onClick={handleSaveFlow}>
                    Save Flow
                  </button>
                  <button className="btn btn-secondary" onClick={handleDownload}>
                    Download JSON
                  </button>
                </div>
              </div>
              {saveSuccess && <div className="save-success">{saveSuccess}</div>}
              {genView === "summary" ? (
                <FlowSummaryPanel
                  flowObj={displayFlowObj as Record<string, unknown> || null}
                  issues={(displayIssues || []) as unknown as Array<Record<string, unknown>>}
                />
              ) : (
                <pre className="nifi-json">{displayFlowJson || flowJson}</pre>
              )}
            </div>
          )}
        </div>
      )}

      {/* ===== SAVED FLOWS TAB ===== */}
      {subTab === "saved" && (
        <div className="nifi-saved-tab">
          <div className="nifi-issues-header">
            <h3>Saved Flows</h3>
            <button className="btn btn-sm" onClick={refreshSavedFlows} disabled={savedLoading}>
              {savedLoading ? "Loading..." : "Refresh"}
            </button>
          </div>

          {savedLoading && !savedFlows.length && <div className="loading">Loading saved flows...</div>}

          {savedError && <div className="pipeline-error">{savedError}</div>}

          {!savedLoading && !savedError && savedFlows.length === 0 && (
            <div className="loading">No saved flows yet. Generate and save a flow, or run the pipeline.</div>
          )}

          {savedFlows.map((flow) => (
            <div key={flow.id} className="saved-flow-card">
              <div className="saved-flow-header">
                <h4>{flow.name}</h4>
                <span className="text-dim">v{flow.current_version} &middot; {flow.issues_addressed} issues</span>
              </div>
              <div className="saved-flow-meta">
                <span className="text-dim">Created: {new Date(flow.created_at).toLocaleDateString()}</span>
                <span className="text-dim">Updated: {new Date(flow.updated_at).toLocaleDateString()}</span>
                <span className="text-dim">{flow.versions.length} version{flow.versions.length !== 1 ? "s" : ""}</span>
              </div>
              {flow.issues_summary.length > 0 && (
                <div className="saved-flow-tags">
                  {flow.issues_summary.slice(0, 5).map((tag, i) => (
                    <span key={i} className="issue-tag">{tag}</span>
                  ))}
                  {flow.issues_summary.length > 5 && (
                    <span className="issue-tag">+{flow.issues_summary.length - 5} more</span>
                  )}
                </div>
              )}
              <div className="saved-flow-actions">
                <button className="btn btn-primary btn-sm" onClick={() => openEditor(flow.id)}>
                  View / Edit
                </button>
                <button className="btn btn-secondary btn-sm" onClick={() => handleCloneFromList(flow.id)}>
                  Clone
                </button>
                <button className="btn btn-danger btn-sm" onClick={() => handleDeleteFromList(flow.id)}>
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ===== EDITOR TAB ===== */}
      {subTab === "editor" && editDetail && (
        <div className="nifi-editor-tab">
          <div className="editor-header">
            <label>
              Flow Name:
              <input type="text" value={editName} onChange={(e) => setEditName(e.target.value)} />
            </label>
            <label>
              Version Note:
              <input
                type="text"
                value={editNote}
                onChange={(e) => setEditNote(e.target.value)}
                placeholder="Describe your changes..."
              />
            </label>
          </div>

          <div className="view-toggle" style={{ marginBottom: 8 }}>
            <button className={`btn btn-sm ${editorView === "summary" ? "btn-primary" : "btn-secondary"}`} onClick={() => setEditorView("summary")}>
              Summary
            </button>
            <button className={`btn btn-sm ${editorView === "json" ? "btn-primary" : "btn-secondary"}`} onClick={() => setEditorView("json")}>
              JSON Editor
            </button>
          </div>

          <div className="editor-body">
            <div className="version-history">
              <h4>Versions</h4>
              {[...editDetail.metadata.versions].reverse().map((v) => (
                <button
                  key={v.version}
                  className={`version-item ${v.version === activeVersion ? "active" : ""}`}
                  onClick={() => loadVersion(v.version)}
                >
                  <span className="version-num">v{v.version}</span>
                  <span className="version-note">{v.note}</span>
                  <span className="version-date">{new Date(v.created_at).toLocaleDateString()}</span>
                </button>
              ))}
            </div>

            <div className="editor-main">
              {editorView === "summary" ? (
                <FlowSummaryPanel
                  flowObj={(() => { try { return JSON.parse(editJson); } catch { return null; } })()}
                  issues={editDetail.flow_data.issues as unknown as Array<Record<string, unknown>>}
                />
              ) : (
                <>
                  <textarea
                    className={`json-editor ${editJsonError ? "json-error" : ""}`}
                    value={editJson}
                    onChange={(e) => {
                      setEditJson(e.target.value);
                      setEditJsonError("");
                    }}
                    spellCheck={false}
                  />
                  {editJsonError && <div className="json-error-msg">{editJsonError}</div>}
                </>
              )}
            </div>
          </div>

          {editDetail.flow_data.design_rationale && (
            <div className="editor-rationale">
              <h4>AI Design Rationale</h4>
              <div className="analysis-content">{editDetail.flow_data.design_rationale}</div>
            </div>
          )}

          <div className="editor-actions">
            <button className="btn btn-primary" onClick={handleEditorSave} disabled={editSaving}>
              {editSaving ? "Saving..." : "Save Changes"}
            </button>
            <button className="btn btn-secondary" onClick={handleEditorDownload}>
              Download
            </button>
            <button className="btn btn-secondary" onClick={handleEditorClone}>
              Clone
            </button>
            <button className="btn btn-danger" onClick={handleEditorDelete}>
              Delete
            </button>
            <button className="btn btn-secondary" onClick={() => setSubTab("saved")}>
              Back to List
            </button>
          </div>
          {editSuccess && <div className="save-success">{editSuccess}</div>}
        </div>
      )}
    </div>
  );
}
