import { useState, useEffect, useCallback } from "react";
import {
  streamClassification,
  listSavedClassifications,
  saveNewClassification,
  getSavedClassification,
  getSavedClassificationVersion,
  updateSavedClassification,
  deleteSavedClassification,
  cloneSavedClassification,
} from "../api/client";
import type {
  ClassificationResult,
  ColumnClassificationResult,
  SavedClassificationEntry,
  SavedClassificationDetail,
} from "../types";

type SubTab = "generate" | "saved" | "editor";
type SortKey = "field_name" | "sensitivity_label" | "semantic_type" | "format_label" | "sensitivity_confidence" | "classified_by";

export default function Classifications() {
  const [subTab, setSubTab] = useState<SubTab>("generate");

  // ----- Generate tab state -----
  const [classificationName, setClassificationName] = useState("AGT Classification");
  const [confidenceThreshold, setConfidenceThreshold] = useState(0.7);
  const [useLlm, setUseLlm] = useState(true);
  const [classResult, setClassResult] = useState<ClassificationResult | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [progress, setProgress] = useState("");
  const [saveSuccess, setSaveSuccess] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("field_name");
  const [sortAsc, setSortAsc] = useState(true);
  const [filterSensitivity, setFilterSensitivity] = useState<string>("all");

  // ----- Saved tab state -----
  const [savedFiles, setSavedFiles] = useState<SavedClassificationEntry[]>([]);
  const [savedLoading, setSavedLoading] = useState(false);
  const [savedError, setSavedError] = useState("");

  // ----- Editor tab state -----
  const [editDetail, setEditDetail] = useState<SavedClassificationDetail | null>(null);
  const [editName, setEditName] = useState("");
  const [editNote, setEditNote] = useState("");
  const [editSaving, setEditSaving] = useState(false);
  const [editSuccess, setEditSuccess] = useState("");
  const [activeVersion, setActiveVersion] = useState<number>(0);
  const [editColumns, setEditColumns] = useState<ColumnClassificationResult[]>([]);

  // Load saved files
  const refreshSavedFiles = useCallback(() => {
    setSavedLoading(true);
    setSavedError("");
    listSavedClassifications()
      .then(setSavedFiles)
      .catch((e) => {
        console.error("Failed to load saved classifications:", e);
        setSavedError("Failed to load saved classifications.");
      })
      .finally(() => setSavedLoading(false));
  }, []);

  useEffect(() => {
    refreshSavedFiles();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (subTab === "saved") refreshSavedFiles();
  }, [subTab, refreshSavedFiles]);

  // ----- Generate tab handlers -----
  const handleRunClassification = async () => {
    setIsRunning(true);
    setProgress("Starting classification...");
    setClassResult(null);
    setSaveSuccess("");

    try {
      for await (const event of streamClassification(classificationName, confidenceThreshold, useLlm)) {
        switch (event.event) {
          case "classifier_start":
            setProgress(`Running ML classifiers on ${(event.data as { total_columns?: number }).total_columns || "?"} columns...`);
            break;
          case "classifier_done":
            setProgress("ML classifiers complete.");
            break;
          case "classifier_confidence": {
            const lowCount = (event.data as { low_confidence_count?: number }).low_confidence_count || 0;
            setProgress(`ML done. ${lowCount} columns below confidence threshold.`);
            break;
          }
          case "llm_start":
            setProgress("Starting LLM classification for business terms & ontology...");
            break;
          case "llm_batch": {
            const d = event.data as { batch?: number; total_batches?: number };
            setProgress(`LLM batch ${d.batch || "?"}/${d.total_batches || "?"}...`);
            break;
          }
          case "llm_batch_result":
            break;
          case "llm_done":
            setProgress("LLM classification complete.");
            break;
          case "llm_error":
            setProgress("LLM unavailable — using ML classifier results only.");
            break;
          case "classification_result":
            setClassResult(event.data as unknown as ClassificationResult);
            setProgress("Classification complete!");
            break;
          case "done":
            setIsRunning(false);
            return;
          case "error":
            setProgress(`Error: ${(event.data as { message?: string }).message || "Unknown error"}`);
            setIsRunning(false);
            return;
        }
      }
    } catch (err) {
      setProgress(`Error: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setIsRunning(false);
    }
  };

  const handleSaveClassification = async () => {
    if (!classResult) return;
    setSaveSuccess("");
    try {
      await saveNewClassification(classificationName, classResult as unknown as Record<string, unknown>);
      setSaveSuccess("Saved! Switching to Saved Files...");
      refreshSavedFiles();
      setTimeout(() => {
        setSaveSuccess("");
        setSubTab("saved");
      }, 1000);
    } catch (e) {
      console.error(e);
      setSaveSuccess("Failed to save classification.");
    }
  };

  // Sorting
  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(key);
      setSortAsc(true);
    }
  };

  const getSortedColumns = (): ColumnClassificationResult[] => {
    if (!classResult) return [];
    let cols = [...classResult.columns];
    if (filterSensitivity !== "all") {
      cols = cols.filter((c) => c.sensitivity_label === filterSensitivity);
    }
    cols.sort((a, b) => {
      const av = a[sortKey] ?? "";
      const bv = b[sortKey] ?? "";
      if (typeof av === "number" && typeof bv === "number") {
        return sortAsc ? av - bv : bv - av;
      }
      return sortAsc ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
    });
    return cols;
  };

  // ----- Saved tab handlers -----
  const openEditor = async (id: string) => {
    try {
      const detail = await getSavedClassification(id);
      setEditDetail(detail);
      setEditName(detail.metadata.name);
      const clfData = detail.classification_data?.classification_data;
      setEditColumns(clfData?.columns || []);
      setEditNote("");
      setEditSuccess("");
      setActiveVersion(detail.metadata.current_version);
      setSubTab("editor");
    } catch (e) {
      console.error(e);
    }
  };

  const handleCloneFromList = async (id: string) => {
    try {
      await cloneSavedClassification(id);
      refreshSavedFiles();
    } catch (e) {
      console.error(e);
    }
  };

  const handleDeleteFromList = async (id: string) => {
    if (!confirm("Delete this classification and all its versions?")) return;
    try {
      await deleteSavedClassification(id);
      refreshSavedFiles();
    } catch (e) {
      console.error(e);
    }
  };

  // ----- Editor tab handlers -----
  const handleEditorSave = async () => {
    if (!editDetail) return;
    setEditSaving(true);
    setEditSuccess("");
    try {
      const clfData = editDetail.classification_data?.classification_data || {};
      const updatedData = { ...clfData, columns: editColumns };
      const updated = await updateSavedClassification(editDetail.metadata.id, {
        name: editName,
        classification_data: updatedData as Record<string, unknown>,
        note: editNote || "Updated",
      });
      const detail = await getSavedClassification(updated.id);
      setEditDetail(detail);
      setActiveVersion(detail.metadata.current_version);
      setEditColumns(detail.classification_data?.classification_data?.columns || []);
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

  const handleEditorClone = async () => {
    if (!editDetail) return;
    try {
      const cloned = await cloneSavedClassification(editDetail.metadata.id);
      const detail = await getSavedClassification(cloned.id);
      setEditDetail(detail);
      setEditName(detail.metadata.name);
      setActiveVersion(detail.metadata.current_version);
      setEditColumns(detail.classification_data?.classification_data?.columns || []);
      setEditSuccess("Classification cloned!");
      setTimeout(() => setEditSuccess(""), 3000);
    } catch (e) {
      console.error(e);
    }
  };

  const handleEditorDelete = async () => {
    if (!editDetail) return;
    if (!confirm("Delete this classification and all its versions?")) return;
    try {
      await deleteSavedClassification(editDetail.metadata.id);
      setEditDetail(null);
      setSubTab("saved");
      refreshSavedFiles();
    } catch (e) {
      console.error(e);
    }
  };

  const loadVersion = async (version: number) => {
    if (!editDetail) return;
    try {
      const detail = await getSavedClassificationVersion(editDetail.metadata.id, version);
      setEditColumns(detail.classification_data?.classification_data?.columns || []);
      setActiveVersion(version);
    } catch (e) {
      console.error(e);
    }
  };

  const handleDownloadJson = () => {
    const data = classResult || (editDetail?.classification_data?.classification_data);
    if (!data) return;
    const content = JSON.stringify(data, null, 2);
    const blob = new Blob([content], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${(classificationName || "classification").replace(/\s+/g, "_")}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // ----- Editor column update -----
  const updateEditColumn = (idx: number, key: string, value: unknown) => {
    setEditColumns((prev) => {
      const next = [...prev];
      next[idx] = { ...next[idx], [key]: value } as ColumnClassificationResult;
      return next;
    });
  };

  // ----- Render helpers -----
  const sensitivityBadge = (label: string) => {
    const cls =
      label === "PHI" ? "classification-badge-phi" :
      label === "PII" ? "classification-badge-pii" :
      label === "internal" ? "classification-badge-internal" :
      "classification-badge-public";
    return <span className={`classification-badge ${cls}`}>{label || "—"}</span>;
  };

  const confidenceIndicator = (conf: number) => {
    const cls =
      conf >= 0.9 ? "confidence-high" :
      conf >= 0.7 ? "confidence-medium" :
      "confidence-low";
    return <span className={`confidence-indicator ${cls}`}>{(conf * 100).toFixed(0)}%</span>;
  };

  const renderSummaryCards = (result: ClassificationResult) => {
    const counts = result.summary?.sensitivity_counts || {};
    return (
      <div className="classification-summary-cards">
        <div className="classification-summary-card" style={{ borderColor: "var(--error)" }}>
          <span className="summary-card-count">{counts["PHI"] || 0}</span>
          <span className="summary-card-label">PHI</span>
        </div>
        <div className="classification-summary-card" style={{ borderColor: "var(--warning)" }}>
          <span className="summary-card-count">{counts["PII"] || 0}</span>
          <span className="summary-card-label">PII</span>
        </div>
        <div className="classification-summary-card" style={{ borderColor: "var(--accent)" }}>
          <span className="summary-card-count">{counts["internal"] || 0}</span>
          <span className="summary-card-label">Internal</span>
        </div>
        <div className="classification-summary-card" style={{ borderColor: "var(--success)" }}>
          <span className="summary-card-count">{counts["public"] || 0}</span>
          <span className="summary-card-label">Public</span>
        </div>
      </div>
    );
  };

  const renderResultsTable = (columns: ColumnClassificationResult[], editable = false) => {
    const displayCols = editable ? columns : getSortedColumns();
    const sensitivityOptions = ["PII", "PHI", "internal", "public"];

    return (
      <div className="classification-table-wrap">
        <table className="classification-table">
          <thead>
            <tr>
              <th onClick={() => !editable && handleSort("field_name")} style={{ cursor: editable ? "default" : "pointer" }}>
                Field Name {!editable && sortKey === "field_name" && (sortAsc ? "▲" : "▼")}
              </th>
              <th>Business Term</th>
              <th onClick={() => !editable && handleSort("sensitivity_label")} style={{ cursor: editable ? "default" : "pointer" }}>
                Sensitivity {!editable && sortKey === "sensitivity_label" && (sortAsc ? "▲" : "▼")}
              </th>
              <th onClick={() => !editable && handleSort("semantic_type")} style={{ cursor: editable ? "default" : "pointer" }}>
                Semantic Type {!editable && sortKey === "semantic_type" && (sortAsc ? "▲" : "▼")}
              </th>
              <th onClick={() => !editable && handleSort("format_label")} style={{ cursor: editable ? "default" : "pointer" }}>
                Format {!editable && sortKey === "format_label" && (sortAsc ? "▲" : "▼")}
              </th>
              <th onClick={() => !editable && handleSort("sensitivity_confidence")} style={{ cursor: editable ? "default" : "pointer" }}>
                Confidence {!editable && sortKey === "sensitivity_confidence" && (sortAsc ? "▲" : "▼")}
              </th>
              <th onClick={() => !editable && handleSort("classified_by")} style={{ cursor: editable ? "default" : "pointer" }}>
                Source {!editable && sortKey === "classified_by" && (sortAsc ? "▲" : "▼")}
              </th>
            </tr>
          </thead>
          <tbody>
            {displayCols.map((col, i) => (
              <tr key={col.field_name}>
                <td className="classification-field-name">{col.field_name}</td>
                <td>
                  {editable ? (
                    <input
                      className="structured-input"
                      type="text"
                      value={col.business_term || ""}
                      onChange={(e) => updateEditColumn(i, "business_term", e.target.value)}
                      style={{ width: "100%" }}
                    />
                  ) : (
                    <span className="text-dim">{col.business_term || "—"}</span>
                  )}
                </td>
                <td>
                  {editable ? (
                    <select
                      className="structured-input"
                      value={col.sensitivity_label}
                      onChange={(e) => updateEditColumn(i, "sensitivity_label", e.target.value)}
                    >
                      {sensitivityOptions.map((o) => <option key={o} value={o}>{o}</option>)}
                    </select>
                  ) : (
                    sensitivityBadge(col.sensitivity_label)
                  )}
                </td>
                <td>
                  {editable ? (
                    <input
                      className="structured-input"
                      type="text"
                      value={col.semantic_type || ""}
                      onChange={(e) => updateEditColumn(i, "semantic_type", e.target.value)}
                      style={{ width: "100%" }}
                    />
                  ) : (
                    <span>{col.semantic_type || "—"}</span>
                  )}
                </td>
                <td>
                  {editable ? (
                    <input
                      className="structured-input"
                      type="text"
                      value={col.format_label || ""}
                      onChange={(e) => updateEditColumn(i, "format_label", e.target.value)}
                      style={{ width: "100%" }}
                    />
                  ) : (
                    <span className="text-dim">{col.format_label || "—"}</span>
                  )}
                </td>
                <td>
                  {confidenceIndicator(Math.min(col.sensitivity_confidence, col.semantic_confidence, col.format_confidence))}
                </td>
                <td>
                  <span className="issue-tag" style={{ fontSize: 10 }}>
                    {col.classified_by || "—"}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  };

  // ----- Render -----
  return (
    <div className="nifi-flows">
      <div className="nifi-sub-tabs">
        <button className={subTab === "generate" ? "active" : ""} onClick={() => setSubTab("generate")}>
          Generate
        </button>
        <button className={subTab === "saved" ? "active" : ""} onClick={() => setSubTab("saved")}>
          Saved
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
          <div className="nifi-config" style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "flex-end" }}>
            <label style={{ flex: 1, minWidth: 200 }}>
              Classification Name:
              <input type="text" value={classificationName} onChange={(e) => setClassificationName(e.target.value)} />
            </label>
            <label style={{ width: 160 }}>
              Confidence Threshold:
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <input
                  type="range"
                  min={0.3}
                  max={0.95}
                  step={0.05}
                  value={confidenceThreshold}
                  onChange={(e) => setConfidenceThreshold(parseFloat(e.target.value))}
                  style={{ flex: 1 }}
                />
                <span style={{ fontSize: 13, fontWeight: 600 }}>{(confidenceThreshold * 100).toFixed(0)}%</span>
              </div>
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
              <input
                type="checkbox"
                checked={useLlm}
                onChange={(e) => setUseLlm(e.target.checked)}
              />
              Use LLM
            </label>
          </div>

          <div className="nifi-actions">
            <button
              className="btn btn-primary"
              onClick={handleRunClassification}
              disabled={isRunning}
            >
              {isRunning ? "Classifying..." : "Run Classification"}
            </button>
          </div>

          {progress && (
            <div className={`classification-progress ${isRunning ? "running" : ""}`}>
              {isRunning && <span className="classification-spinner" />}
              {progress}
            </div>
          )}

          {classResult && (
            <div className="nifi-output">
              <div className="nifi-output-header">
                <h3>Classification Results — {classResult.total_columns} columns</h3>
                <div style={{ display: "flex", gap: 8 }}>
                  <select
                    className="structured-input"
                    value={filterSensitivity}
                    onChange={(e) => setFilterSensitivity(e.target.value)}
                    style={{ width: 120 }}
                  >
                    <option value="all">All</option>
                    <option value="PHI">PHI</option>
                    <option value="PII">PII</option>
                    <option value="internal">Internal</option>
                    <option value="public">Public</option>
                  </select>
                  <button className="btn btn-primary" onClick={handleSaveClassification}>Save</button>
                  <button className="btn btn-secondary" onClick={handleDownloadJson}>Download JSON</button>
                </div>
              </div>
              {saveSuccess && <div className="save-success">{saveSuccess}</div>}

              {renderSummaryCards(classResult)}
              {renderResultsTable(classResult.columns)}
            </div>
          )}
        </div>
      )}

      {/* ===== SAVED TAB ===== */}
      {subTab === "saved" && (
        <div className="nifi-saved-tab">
          <div className="nifi-issues-header">
            <h3>Saved Classifications</h3>
            <button className="btn btn-sm" onClick={refreshSavedFiles} disabled={savedLoading}>
              {savedLoading ? "Loading..." : "Refresh"}
            </button>
          </div>

          {savedLoading && !savedFiles.length && <div className="loading">Loading saved classifications...</div>}
          {savedError && <div className="pipeline-error">{savedError}</div>}
          {!savedLoading && !savedError && savedFiles.length === 0 && (
            <div className="loading">No saved classifications yet. Run a classification and save it.</div>
          )}

          {savedFiles.map((file) => (
            <div key={file.id} className="saved-flow-card">
              <div className="saved-flow-header">
                <h4>{file.name}</h4>
                <span className="text-dim">v{file.current_version} · {file.total_columns} columns</span>
              </div>
              <div className="saved-flow-meta">
                <span className="text-dim">Created: {new Date(file.created_at).toLocaleDateString()}</span>
                <span className="text-dim">Updated: {new Date(file.updated_at).toLocaleDateString()}</span>
                <span className="text-dim">{file.llm_used ? "LLM Enhanced" : "ML Only"}</span>
                <span className="text-dim">{file.versions.length} version{file.versions.length !== 1 ? "s" : ""}</span>
              </div>
              {file.sensitivity_summary && (
                <div className="saved-flow-tags">
                  {Object.entries(file.sensitivity_summary).map(([label, count]) => (
                    <span key={label} className="issue-tag">{label}: {count}</span>
                  ))}
                </div>
              )}
              <div className="saved-flow-actions">
                <button className="btn btn-primary btn-sm" onClick={() => openEditor(file.id)}>
                  View / Edit
                </button>
                <button className="btn btn-secondary btn-sm" onClick={() => handleCloneFromList(file.id)}>
                  Clone
                </button>
                <button className="btn btn-danger btn-sm" onClick={() => handleDeleteFromList(file.id)}>
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
              Classification Name:
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
              {renderResultsTable(editColumns, true)}
            </div>
          </div>

          <div className="editor-actions">
            <button className="btn btn-primary" onClick={handleEditorSave} disabled={editSaving}>
              {editSaving ? "Saving..." : "Save Changes"}
            </button>
            <button className="btn btn-primary" onClick={handleDownloadJson}>
              Download JSON
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
