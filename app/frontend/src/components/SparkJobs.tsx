import { useState, useEffect, useCallback } from "react";
import {
  detectSparkIssues,
  generateSparkJob,
  streamSparkDesign,
  listSavedJobs,
  saveNewJob,
  getSavedJob,
  getSavedJobVersion,
  updateSavedJob,
  deleteSavedJob,
  cloneSavedJob,
  getColumns,
} from "../api/client";
import { useAnalysisStream } from "../hooks/useAnalysisStream";
import type { QualityIssue, SparkJobResult, SavedJobEntry, SavedJobDetail, ColumnMeta } from "../types";

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

export default function SparkJobs({ focusId }: { focusId?: string | null }) {
  const [subTab, setSubTab] = useState<SubTab>(focusId ? "saved" : "generate");

  // ----- Generate tab state -----
  const [rules, setRules] = useState<QualityIssue[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [jobResult, setJobResult] = useState<SparkJobResult | null>(null);
  const [jobName, setJobName] = useState("Data Quality Remediation");
  const [outputFormat, setOutputFormat] = useState("parquet");
  const [loading, setLoading] = useState("");
  const [issuesLoaded, setIssuesLoaded] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState("");
  const [genView, setGenView] = useState<"summary" | "script" | "json">("summary");
  const designAnalysis = useAnalysisStream<SparkJobResult>("spark_job_data");

  // Rule editing state
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
  const [showAddForm, setShowAddForm] = useState(false);
  const [addForm, setAddForm] = useState<QualityIssue>(emptyRule());
  const [columns, setColumns] = useState<ColumnMeta[]>([]);

  // ----- Saved jobs tab state -----
  const [savedJobs, setSavedJobs] = useState<SavedJobEntry[]>([]);
  const [savedLoading, setSavedLoading] = useState(false);
  const [savedError, setSavedError] = useState("");

  // ----- Editor tab state -----
  const [editDetail, setEditDetail] = useState<SavedJobDetail | null>(null);
  const [editName, setEditName] = useState("");
  const [editJson, setEditJson] = useState("");
  const [editScript, setEditScript] = useState("");
  const [editNote, setEditNote] = useState("");
  const [editJsonError, setEditJsonError] = useState("");
  const [editSaving, setEditSaving] = useState(false);
  const [editSuccess, setEditSuccess] = useState("");
  const [activeVersion, setActiveVersion] = useState<number>(0);
  const [editorView, setEditorView] = useState<"summary" | "script" | "json">("summary");

  // Auto-detect issues on mount
  useEffect(() => {
    if (!issuesLoaded) {
      setLoading("detecting");
      detectSparkIssues()
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
    getColumns().then(setColumns).catch(() => {});
  }, []);

  // Load saved jobs
  const refreshSavedJobs = useCallback(() => {
    setSavedLoading(true);
    setSavedError("");
    listSavedJobs()
      .then(setSavedJobs)
      .catch((e) => {
        console.error("Failed to load saved jobs:", e);
        setSavedError("Failed to load saved jobs. Is data loaded?");
      })
      .finally(() => setSavedLoading(false));
  }, []);

  // Load on mount and when switching to saved tab
  useEffect(() => {
    refreshSavedJobs();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (subTab === "saved") refreshSavedJobs();
  }, [subTab, refreshSavedJobs]);

  // Auto-open editor when focusId is provided and jobs are loaded
  useEffect(() => {
    if (focusId && savedJobs.length > 0 && !editDetail) {
      const match = savedJobs.find((j) => j.id === focusId);
      if (match) openEditor(match.id);
    }
  }, [focusId, savedJobs]); // eslint-disable-line react-hooks/exhaustive-deps

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
      const result = await generateSparkJob(jobName, selectedRules(), outputFormat);
      setJobResult(result);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading("");
    }
  };

  const handleDesign = () => {
    const stream = streamSparkDesign(jobName, selectedRules(), outputFormat);
    designAnalysis.runAnalysis(stream);
  };

  const jobData = designAnalysis.structuredData;
  const displayResult = jobData || jobResult;
  const displayJob = displayResult?.job;
  const displayScript = displayResult?.pyspark_script || "";
  const displayIssues = displayResult?.issues;

  const handleDownloadJson = () => {
    if (!displayJob) return;
    const json = JSON.stringify(displayJob, null, 2);
    const blob = new Blob([json], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${jobName.replace(/\s+/g, "_")}_cde_job.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleDownloadScript = () => {
    if (!displayScript) return;
    const blob = new Blob([displayScript], { type: "text/x-python" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = displayResult?.script_name || `${jobName.replace(/\s+/g, "_")}.py`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleSaveJob = async () => {
    if (!displayJob) return;
    setSaveSuccess("");
    try {
      const issuesPayload = (displayIssues || []).map((iss) => ({ ...iss }));
      const rationale = designAnalysis.analysisText || null;
      await saveNewJob(
        jobName,
        displayJob as Record<string, unknown>,
        displayScript,
        displayResult?.script_name || "quality_remediation.py",
        issuesPayload,
        rationale,
      );
      setSaveSuccess("Saved! Switching to Saved Jobs...");
      refreshSavedJobs();
      setTimeout(() => {
        setSaveSuccess("");
        setSubTab("saved");
      }, 1000);
    } catch (e) {
      console.error(e);
      setSaveSuccess("Failed to save job.");
    }
  };

  // ----- Saved jobs tab handlers -----
  const openEditor = async (id: string) => {
    try {
      const detail = await getSavedJob(id);
      setEditDetail(detail);
      setEditName(detail.metadata.name);
      setEditJson(JSON.stringify(detail.job_data.job, null, 2));
      setEditScript(detail.job_data.pyspark_script || "");
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
      await cloneSavedJob(id);
      refreshSavedJobs();
    } catch (e) {
      console.error(e);
    }
  };

  const handleDeleteFromList = async (id: string) => {
    if (!confirm("Delete this job and all its versions?")) return;
    try {
      await deleteSavedJob(id);
      refreshSavedJobs();
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
      const parsedJob = JSON.parse(editJson);
      const updated = await updateSavedJob(editDetail.metadata.id, {
        name: editName,
        job: parsedJob,
        pyspark_script: editScript,
        note: editNote || "Updated",
      });
      const detail = await getSavedJob(updated.id);
      setEditDetail(detail);
      setActiveVersion(detail.metadata.current_version);
      setEditJson(JSON.stringify(detail.job_data.job, null, 2));
      setEditScript(detail.job_data.pyspark_script || "");
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

  const handleEditorDownloadJson = () => {
    if (!editJson || !editDetail) return;
    const blob = new Blob([editJson], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${editName.replace(/\s+/g, "_")}_cde_job.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleEditorDownloadScript = () => {
    if (!editScript || !editDetail) return;
    const blob = new Blob([editScript], { type: "text/x-python" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = editDetail.job_data.script_name || "quality_remediation.py";
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleEditorClone = async () => {
    if (!editDetail) return;
    try {
      const cloned = await cloneSavedJob(editDetail.metadata.id);
      const detail = await getSavedJob(cloned.id);
      setEditDetail(detail);
      setEditName(detail.metadata.name);
      setEditJson(JSON.stringify(detail.job_data.job, null, 2));
      setEditScript(detail.job_data.pyspark_script || "");
      setActiveVersion(detail.metadata.current_version);
      setEditSuccess("Job cloned!");
      setTimeout(() => setEditSuccess(""), 3000);
    } catch (e) {
      console.error(e);
    }
  };

  const handleEditorDelete = async () => {
    if (!editDetail) return;
    if (!confirm("Delete this job and all its versions?")) return;
    try {
      await deleteSavedJob(editDetail.metadata.id);
      setEditDetail(null);
      setSubTab("saved");
      refreshSavedJobs();
    } catch (e) {
      console.error(e);
    }
  };

  const loadVersion = async (version: number) => {
    if (!editDetail) return;
    try {
      const detail = await getSavedJobVersion(editDetail.metadata.id, version);
      setEditJson(JSON.stringify(detail.job_data.job, null, 2));
      setEditScript(detail.job_data.pyspark_script || "");
      setActiveVersion(version);
      setEditJsonError("");
    } catch (e) {
      console.error(e);
    }
  };

  // ----- Render helpers -----
  const renderJobSummary = (job: Record<string, unknown> | null | undefined, issues?: QualityIssue[]) => {
    if (!job) return <div className="text-dim">No job data to display.</div>;
    const sparkConf = job.spark as Record<string, unknown> | undefined;
    return (
      <div className="flow-summary">
        <div className="flow-summary-section">
          <h4>CDE Job Configuration</h4>
          <div className="processor-list">
            <div className="processor-item">
              <span className="processor-type-badge">Type</span>
              <span className="processor-name">{(job.type as string) || "spark"}</span>
            </div>
            {sparkConf && (
              <>
                <div className="processor-item">
                  <span className="processor-type-badge">Script</span>
                  <span className="processor-name">{(sparkConf.file as string) || "?"}</span>
                </div>
                <div className="processor-item">
                  <span className="processor-type-badge">Driver</span>
                  <span className="processor-name">
                    {String(sparkConf.driverCores)} cores, {String(sparkConf.driverMemory)}
                  </span>
                </div>
                <div className="processor-item">
                  <span className="processor-type-badge">Executors</span>
                  <span className="processor-name">
                    {String(sparkConf.numExecutors)} x ({String(sparkConf.executorCores)} cores, {String(sparkConf.executorMemory)})
                  </span>
                </div>
              </>
            )}
          </div>
        </div>

        {issues && issues.length > 0 && (
          <div className="flow-summary-section">
            <h4>Issues Addressed ({issues.length})</h4>
            <div className="flow-issues-list">
              {issues.map((iss, i) => (
                <div key={i} className="flow-issue-item">
                  <span className={`issue-type ${iss.issue_type || ""}`}>
                    {(iss.issue_type || "").replace(/_/g, " ")}
                  </span>
                  <span className="issue-field">{iss.field_name}</span>
                  <span className="issue-pct">{iss.affected_pct}%</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  };

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
          Saved Jobs
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
            <div className="spark-config-row">
              <label>
                Job Name:
                <input type="text" value={jobName} onChange={(e) => setJobName(e.target.value)} />
              </label>
              <label>
                Output Format:
                <select value={outputFormat} onChange={(e) => setOutputFormat(e.target.value)}>
                  <option value="parquet">Parquet</option>
                  <option value="delta">Delta</option>
                </select>
              </label>
            </div>
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
              {loading === "generating" ? "Generating..." : `Generate Job (${selected.size} rules)`}
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

          {displayResult && (
            <div className="nifi-output">
              <div className="nifi-output-header">
                <h3>Generated CDE Spark Job</h3>
                <div style={{ display: "flex", gap: 8 }}>
                  <div className="view-toggle">
                    <button className={`btn btn-sm ${genView === "summary" ? "btn-primary" : "btn-secondary"}`} onClick={() => setGenView("summary")}>
                      Summary
                    </button>
                    <button className={`btn btn-sm ${genView === "script" ? "btn-primary" : "btn-secondary"}`} onClick={() => setGenView("script")}>
                      PySpark Script
                    </button>
                    <button className={`btn btn-sm ${genView === "json" ? "btn-primary" : "btn-secondary"}`} onClick={() => setGenView("json")}>
                      Job JSON
                    </button>
                  </div>
                  <button className="btn btn-primary" onClick={handleSaveJob}>
                    Save Job
                  </button>
                  <button className="btn btn-secondary" onClick={handleDownloadJson}>
                    Download JSON
                  </button>
                  <button className="btn btn-secondary" onClick={handleDownloadScript}>
                    Download Script
                  </button>
                </div>
              </div>
              {saveSuccess && <div className="save-success">{saveSuccess}</div>}
              {genView === "summary" ? (
                renderJobSummary(displayJob as Record<string, unknown> || null, displayIssues)
              ) : genView === "script" ? (
                <pre className="pyspark-script">{displayScript}</pre>
              ) : (
                <pre className="nifi-json">{JSON.stringify(displayJob, null, 2)}</pre>
              )}
            </div>
          )}
        </div>
      )}

      {/* ===== SAVED JOBS TAB ===== */}
      {subTab === "saved" && (
        <div className="nifi-saved-tab">
          <div className="nifi-issues-header">
            <h3>Saved Jobs</h3>
            <button className="btn btn-sm" onClick={refreshSavedJobs} disabled={savedLoading}>
              {savedLoading ? "Loading..." : "Refresh"}
            </button>
          </div>

          {savedLoading && !savedJobs.length && <div className="loading">Loading saved jobs...</div>}

          {savedError && <div className="pipeline-error">{savedError}</div>}

          {!savedLoading && !savedError && savedJobs.length === 0 && (
            <div className="loading">No saved jobs yet. Generate and save a job, or run the pipeline.</div>
          )}

          {savedJobs.map((job) => (
            <div key={job.id} className="saved-flow-card">
              <div className="saved-flow-header">
                <h4>{job.name}</h4>
                <span className="text-dim">v{job.current_version} &middot; {job.issues_addressed} issues</span>
              </div>
              <div className="saved-flow-meta">
                <span className="text-dim">Created: {new Date(job.created_at).toLocaleDateString()}</span>
                <span className="text-dim">Updated: {new Date(job.updated_at).toLocaleDateString()}</span>
                <span className="text-dim">{job.versions.length} version{job.versions.length !== 1 ? "s" : ""}</span>
              </div>
              {job.issues_summary.length > 0 && (
                <div className="saved-flow-tags">
                  {job.issues_summary.slice(0, 5).map((tag, i) => (
                    <span key={i} className="issue-tag">{tag}</span>
                  ))}
                  {job.issues_summary.length > 5 && (
                    <span className="issue-tag">+{job.issues_summary.length - 5} more</span>
                  )}
                </div>
              )}
              <div className="saved-flow-actions">
                <button className="btn btn-primary btn-sm" onClick={() => openEditor(job.id)}>
                  View / Edit
                </button>
                <button className="btn btn-secondary btn-sm" onClick={() => handleCloneFromList(job.id)}>
                  Clone
                </button>
                <button className="btn btn-danger btn-sm" onClick={() => handleDeleteFromList(job.id)}>
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
              Job Name:
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
            <button className={`btn btn-sm ${editorView === "script" ? "btn-primary" : "btn-secondary"}`} onClick={() => setEditorView("script")}>
              PySpark Script
            </button>
            <button className={`btn btn-sm ${editorView === "json" ? "btn-primary" : "btn-secondary"}`} onClick={() => setEditorView("json")}>
              Job JSON
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
                renderJobSummary(
                  (() => { try { return JSON.parse(editJson); } catch { return null; } })(),
                  editDetail.job_data.issues,
                )
              ) : editorView === "script" ? (
                <textarea
                  className="json-editor"
                  value={editScript}
                  onChange={(e) => setEditScript(e.target.value)}
                  spellCheck={false}
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

          {editDetail.job_data.design_rationale && (
            <div className="editor-rationale">
              <h4>AI Design Rationale</h4>
              <div className="analysis-content">{editDetail.job_data.design_rationale}</div>
            </div>
          )}

          <div className="editor-actions">
            <button className="btn btn-primary" onClick={handleEditorSave} disabled={editSaving}>
              {editSaving ? "Saving..." : "Save Changes"}
            </button>
            <button className="btn btn-secondary" onClick={handleEditorDownloadJson}>
              Download JSON
            </button>
            <button className="btn btn-secondary" onClick={handleEditorDownloadScript}>
              Download Script
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
