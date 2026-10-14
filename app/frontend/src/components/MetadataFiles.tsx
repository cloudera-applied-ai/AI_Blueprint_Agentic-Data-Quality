import { useState, useEffect, useCallback } from "react";
import {
  detectMetadataIssues,
  generateMetadataYaml,
  listSavedMetadata,
  saveNewMetadata,
  getSavedMetadata,
  getSavedMetadataVersion,
  updateSavedMetadata,
  deleteSavedMetadata,
  cloneSavedMetadata,
} from "../api/client";
import type { QualityIssue, MetadataYamlResult, SavedMetadataEntry, SavedMetadataDetail, MetadataValidation } from "../types";

type SubTab = "generate" | "saved" | "editor";
type ViewMode = "yaml" | "json" | "structured";

export default function MetadataFiles({ focusId }: { focusId?: string | null }) {
  const [subTab, setSubTab] = useState<SubTab>(focusId ? "saved" : "generate");

  // ----- Generate tab state -----
  const [rules, setRules] = useState<QualityIssue[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [yamlResult, setYamlResult] = useState<MetadataYamlResult | null>(null);
  const [specName, setSpecName] = useState("AGT Data Ingestion Specification");
  const [loading, setLoading] = useState("");
  const [issuesLoaded, setIssuesLoaded] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState("");
  const [genView, setGenView] = useState<ViewMode>("json");

  // ----- Saved tab state -----
  const [savedFiles, setSavedFiles] = useState<SavedMetadataEntry[]>([]);
  const [savedLoading, setSavedLoading] = useState(false);
  const [savedError, setSavedError] = useState("");

  // ----- Editor tab state -----
  const [editDetail, setEditDetail] = useState<SavedMetadataDetail | null>(null);
  const [editName, setEditName] = useState("");
  const [editYaml, setEditYaml] = useState("");
  const [editNote, setEditNote] = useState("");
  const [editSaving, setEditSaving] = useState(false);
  const [editSuccess, setEditSuccess] = useState("");
  const [activeVersion, setActiveVersion] = useState<number>(0);
  const [editJson, setEditJson] = useState("");
  const [editDict, setEditDict] = useState<Record<string, unknown>>({});
  const [editorView, setEditorView] = useState<ViewMode>("json");

  // Auto-detect issues on mount
  useEffect(() => {
    if (!issuesLoaded) {
      setLoading("detecting");
      detectMetadataIssues()
        .then((issues) => {
          setRules(issues.map((i) => ({ ...i })));
          setSelected(new Set(issues.map((_, idx) => idx)));
          setIssuesLoaded(true);
        })
        .catch((e) => console.error("Issue detection failed:", e))
        .finally(() => setLoading(""));
    }
  }, [issuesLoaded]);

  // Load saved files when switching to saved tab
  const refreshSavedFiles = useCallback(() => {
    setSavedLoading(true);
    setSavedError("");
    listSavedMetadata()
      .then(setSavedFiles)
      .catch((e) => {
        console.error("Failed to load saved files:", e);
        setSavedError("Failed to load saved files. Is data loaded?");
      })
      .finally(() => setSavedLoading(false));
  }, []);

  // Load saved files on mount and when switching to saved tab
  useEffect(() => {
    refreshSavedFiles();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (subTab === "saved") refreshSavedFiles();
  }, [subTab, refreshSavedFiles]);

  // Auto-open editor when focusId is provided and files are loaded
  useEffect(() => {
    if (focusId && savedFiles.length > 0 && !editDetail) {
      const match = savedFiles.find((f) => f.id === focusId);
      if (match) openEditor(match.id);
    }
  }, [focusId, savedFiles]); // eslint-disable-line react-hooks/exhaustive-deps

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

  const selectedRules = (): QualityIssue[] => {
    return rules.filter((_, i) => selected.has(i));
  };

  // ----- Generate tab handlers -----
  const handleGenerate = async () => {
    setLoading("generating");
    try {
      const result = await generateMetadataYaml(specName, selectedRules());
      setYamlResult(result);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading("");
    }
  };

  const handleDownload = (format: "yaml" | "json" = "yaml") => {
    if (!yamlResult) return;
    let content: string;
    let mimeType: string;
    let ext: string;
    if (format === "json") {
      content = JSON.stringify(yamlResult.yaml_dict || {}, null, 2);
      mimeType = "application/json";
      ext = "json";
    } else {
      content = yamlResult.yaml_content || "";
      mimeType = "text/yaml";
      ext = "yaml";
    }
    if (!content) return;
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${specName.replace(/\s+/g, "_")}.${ext}`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleSaveMetadata = async () => {
    if (!yamlResult) return;
    setSaveSuccess("");
    try {
      const issuesPayload = (yamlResult.issues || []).map((iss) => ({ ...iss }));
      await saveNewMetadata(
        specName,
        yamlResult.yaml_content,
        yamlResult.yaml_dict,
        issuesPayload,
      );
      setSaveSuccess("Saved! Switching to Saved Files...");
      refreshSavedFiles();
      setTimeout(() => {
        setSaveSuccess("");
        setSubTab("saved");
      }, 1000);
    } catch (e) {
      console.error(e);
      setSaveSuccess("Failed to save metadata file.");
    }
  };

  // ----- Saved tab handlers -----
  const openEditor = async (id: string) => {
    try {
      const detail = await getSavedMetadata(id);
      const dict = detail.file_data.yaml_dict || {};
      setEditDetail(detail);
      setEditName(detail.metadata.name);
      setEditYaml(detail.file_data.yaml_content || "");
      setEditJson(JSON.stringify(dict, null, 2));
      setEditDict(JSON.parse(JSON.stringify(dict)));
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
      await cloneSavedMetadata(id);
      refreshSavedFiles();
    } catch (e) {
      console.error(e);
    }
  };

  const handleDeleteFromList = async (id: string) => {
    if (!confirm("Delete this metadata file and all its versions?")) return;
    try {
      await deleteSavedMetadata(id);
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
      const updatePayload: { name?: string; yaml_content?: string; yaml_dict?: Record<string, unknown>; note?: string } = {
        name: editName,
        note: editNote || "Updated",
      };

      if (editorView === "json") {
        // Parse JSON and send as yaml_dict; backend regenerates yaml_content
        try {
          updatePayload.yaml_dict = JSON.parse(editJson);
        } catch {
          setEditSuccess("Invalid JSON. Please fix syntax errors before saving.");
          setEditSaving(false);
          return;
        }
      } else if (editorView === "structured") {
        updatePayload.yaml_dict = editDict;
      } else {
        updatePayload.yaml_content = editYaml;
      }

      const updated = await updateSavedMetadata(editDetail.metadata.id, updatePayload);
      const detail = await getSavedMetadata(updated.id);
      const newDict = detail.file_data.yaml_dict || {};
      setEditDetail(detail);
      setActiveVersion(detail.metadata.current_version);
      setEditYaml(detail.file_data.yaml_content || "");
      setEditJson(JSON.stringify(newDict, null, 2));
      setEditDict(JSON.parse(JSON.stringify(newDict)));
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

  const handleEditorDownload = (format: "yaml" | "json" = "yaml") => {
    if (!editDetail) return;
    let content: string;
    let mimeType: string;
    let ext: string;
    if (format === "json") {
      content = editJson || JSON.stringify(editDetail.file_data.yaml_dict || {}, null, 2);
      mimeType = "application/json";
      ext = "json";
    } else {
      content = editYaml;
      mimeType = "text/yaml";
      ext = "yaml";
    }
    if (!content) return;
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${editName.replace(/\s+/g, "_")}.${ext}`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleEditorClone = async () => {
    if (!editDetail) return;
    try {
      const cloned = await cloneSavedMetadata(editDetail.metadata.id);
      const detail = await getSavedMetadata(cloned.id);
      setEditDetail(detail);
      setEditName(detail.metadata.name);
      setEditYaml(detail.file_data.yaml_content || "");
      setActiveVersion(detail.metadata.current_version);
      setEditSuccess("Metadata file cloned!");
      setTimeout(() => setEditSuccess(""), 3000);
    } catch (e) {
      console.error(e);
    }
  };

  const handleEditorDelete = async () => {
    if (!editDetail) return;
    if (!confirm("Delete this metadata file and all its versions?")) return;
    try {
      await deleteSavedMetadata(editDetail.metadata.id);
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
      const detail = await getSavedMetadataVersion(editDetail.metadata.id, version);
      const dict = detail.file_data.yaml_dict || {};
      setEditYaml(detail.file_data.yaml_content || "");
      setEditJson(JSON.stringify(dict, null, 2));
      setEditDict(JSON.parse(JSON.stringify(dict)));
      setActiveVersion(version);
    } catch (e) {
      console.error(e);
    }
  };

  // ----- Structured view helpers -----
  const addColumn = () => {
    setEditDict((prev) => {
      const next = { ...prev };
      const cols = [...((next.columns as Record<string, unknown>[]) || [])];
      const nextPos = cols.length > 0
        ? Math.max(...cols.map((c) => (c.position as number) || 0)) + 1
        : 1;
      cols.unshift({
        name: "",
        position: nextPos,
        business_name: null,
        data_type: "string",
        max_length: 50,
        constraints: [{ type: "max_length", value: 50 }],
      });
      next.columns = cols;
      return next;
    });
  };

  const updateColumn = (idx: number, key: string, value: unknown) => {
    setEditDict((prev) => {
      const next = { ...prev };
      const cols = [...((next.columns as Record<string, unknown>[]) || [])];
      cols[idx] = { ...cols[idx], [key]: value };
      next.columns = cols;
      return next;
    });
  };

  const rejectColumn = (idx: number) => {
    setEditDict((prev) => {
      const next = { ...prev };
      const cols = [...((next.columns as Record<string, unknown>[]) || [])];
      cols.splice(idx, 1);
      next.columns = cols;
      return next;
    });
  };

  const [newVvField, setNewVvField] = useState("");

  const addValidValueSet = () => {
    const name = newVvField.trim().toUpperCase();
    if (!name) return;
    setEditDict((prev) => {
      const next = { ...prev };
      const existing = (next.valid_value_sets as Record<string, string[]>) || {};
      next.valid_value_sets = { [name]: existing[name] ?? [], ...existing };
      return next;
    });
    setNewVvField("");
  };

  const updateValidValues = (field: string, values: string) => {
    setEditDict((prev) => {
      const next = { ...prev };
      const sets = { ...((next.valid_value_sets as Record<string, string[]>) || {}) };
      sets[field] = values.split(",").map((v) => v.trim()).filter(Boolean);
      next.valid_value_sets = sets;
      return next;
    });
  };

  const rejectValidValueField = (field: string) => {
    setEditDict((prev) => {
      const next = { ...prev };
      const sets = { ...((next.valid_value_sets as Record<string, string[]>) || {}) };
      delete sets[field];
      next.valid_value_sets = sets;
      return next;
    });
  };

  const updateIssue = (idx: number, key: string, value: unknown) => {
    setEditDict((prev) => {
      const next = { ...prev };
      const qs = { ...((next.quality_summary as Record<string, unknown>) || {}) };
      const issues = [...((qs.issues as Record<string, unknown>[]) || [])];
      issues[idx] = { ...issues[idx], [key]: value };
      qs.issues = issues;
      next.quality_summary = qs;
      return next;
    });
  };

  const rejectIssue = (idx: number) => {
    setEditDict((prev) => {
      const next = { ...prev };
      const qs = { ...((next.quality_summary as Record<string, unknown>) || {}) };
      const issues = [...((qs.issues as Record<string, unknown>[]) || [])];
      issues.splice(idx, 1);
      qs.issues = issues;
      qs.total_issues = issues.length;
      next.quality_summary = qs;
      return next;
    });
  };

  const addIssue = () => {
    setEditDict((prev) => {
      const next = { ...prev };
      const qs = { ...((next.quality_summary as Record<string, unknown>) || {}) };
      const issues = [...((qs.issues as Record<string, unknown>[]) || [])];
      issues.unshift({
        field: "",
        issue_type: "custom",
        severity: "medium",
        affected_pct: 0,
        description: "",
        suggested_fix: "",
      });
      qs.issues = issues;
      qs.total_issues = issues.length;
      next.quality_summary = qs;
      return next;
    });
  };

  // ----- Validation render -----
  const renderValidation = (v: MetadataValidation) => {
    const scoreColor = v.score >= 95 ? "var(--success)" : v.score >= 70 ? "var(--warning)" : "var(--error)";
    const mismatches = v.column_checks.filter((c) => !c.match);

    return (
      <div className="validation-report">
        <div className="validation-header">
          <span className="validation-score" style={{ color: scoreColor }}>{v.score}%</span>
          <span className="validation-label">
            Metadata Validation: {v.fully_correct}/{v.total_source_fields} columns match source spec
          </span>
        </div>

        {v.missing_fields.length > 0 && (
          <div className="validation-row">
            <span className="text-dim">Missing from generated:</span>
            {v.missing_fields.map((f) => (
              <span key={f} className="issue-tag" style={{ background: "var(--error)", color: "white", fontSize: 10 }}>{f}</span>
            ))}
          </div>
        )}

        {mismatches.length > 0 && (
          <div className="validation-mismatches">
            <span className="text-dim" style={{ fontSize: 12 }}>Mismatches ({mismatches.length}):</span>
            {mismatches.map((col) => (
              <div key={col.column} className="validation-mismatch-item">
                <span className="issue-field">{col.column}</span>
                {!col.position.match && (
                  <span className="text-dim" style={{ fontSize: 11 }}>
                    pos: {String(col.position.generated)} (expected {String(col.position.source)})
                  </span>
                )}
                {!col.max_length.match && (
                  <span className="text-dim" style={{ fontSize: 11 }}>
                    maxLen: {String(col.max_length.generated)} (expected {String(col.max_length.source)})
                  </span>
                )}
                {!col.business_name.match && (
                  <span className="text-dim" style={{ fontSize: 11 }}>
                    name: &quot;{String(col.business_name.generated)}&quot; (expected &quot;{String(col.business_name.source)}&quot;)
                  </span>
                )}
              </div>
            ))}
          </div>
        )}

        {mismatches.length === 0 && v.missing_fields.length === 0 && (
          <div className="validation-row" style={{ color: "var(--success)" }}>
            All generated columns match the source metadata specification.
          </div>
        )}
      </div>
    );
  };

  // ----- Render helpers -----
  const renderStructuredView = (yamlDict: Record<string, unknown>, editable = false) => {
    const meta = yamlDict.metadata as Record<string, unknown> | undefined;
    const columns = (yamlDict.columns as Record<string, unknown>[]) || [];
    const validSets = (yamlDict.valid_value_sets as Record<string, string[]>) || {};
    const qualitySummary = yamlDict.quality_summary as Record<string, unknown> | undefined;
    const qualityIssues = (qualitySummary?.issues as Record<string, unknown>[]) || [];

    const dataTypes = ["string", "identifier", "text", "date", "phone", "code", "flag", "amount", "integer", "reserved"];
    const severities = ["critical", "high", "medium", "low"];

    return (
      <div className="flow-summary">
        {/* Source / Dataset Info */}
        {meta && (
          <div className="flow-summary-section">
            <h4>Data Source</h4>
            <div className="processor-list">
              <div className="processor-item">
                <span className="processor-type-badge">Name</span>
                <span className="processor-name">{String(meta.name || "")}</span>
              </div>
              {meta.source != null && (() => {
                const src = meta.source as Record<string, unknown>;
                return (
                  <>
                    <div className="processor-item">
                      <span className="processor-type-badge">Format</span>
                      <span className="processor-name">
                        {String(src.format || "delimited")} (delimiter: {String(src.delimiter || "|")})
                      </span>
                    </div>
                    <div className="processor-item">
                      <span className="processor-type-badge">Rows</span>
                      <span className="processor-name">{String(src.row_count || "?")}</span>
                    </div>
                    <div className="processor-item">
                      <span className="processor-type-badge">Columns</span>
                      <span className="processor-name">{String(src.column_count || "?")}</span>
                    </div>
                    <div className="processor-item">
                      <span className="processor-type-badge">Encoding</span>
                      <span className="processor-name">{String(src.encoding || "UTF-8")}</span>
                    </div>
                  </>
                );
              })()}
            </div>
          </div>
        )}

        {/* Column Definitions */}
        {(columns.length > 0 || editable) && (
          <div className="flow-summary-section">
            <h4 style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <span>Column Definitions ({columns.length})</span>
              {editable && (
                <button className="btn btn-sm btn-primary" onClick={addColumn} style={{ fontSize: 12 }}>
                  + Add Column
                </button>
              )}
            </h4>
            <div className="flow-issues-list">
              {columns.map((col, i) => {
                const flags = col.flags as Record<string, boolean> | undefined;
                const flagTags = flags ? Object.keys(flags).filter(k => flags[k]) : [];
                return (
                  <div key={i} className="flow-issue-item" style={{ alignItems: "flex-start", flexWrap: "wrap", gap: 6 }}>
                    {editable ? (
                      <input
                        className="structured-input"
                        type="number"
                        value={col.position as number || i + 1}
                        onChange={(e) => updateColumn(i, "position", parseInt(e.target.value) || 0)}
                        style={{ width: 48 }}
                        title="Position"
                      />
                    ) : (
                      <span className="processor-type-badge" style={{ minWidth: 24, textAlign: "center" }}>
                        {String(col.position || i + 1)}
                      </span>
                    )}
                    {editable ? (
                      <input
                        className="structured-input"
                        type="text"
                        value={String(col.name || "")}
                        onChange={(e) => updateColumn(i, "name", e.target.value)}
                        placeholder="Column name"
                        style={{ width: 140, fontWeight: 600 }}
                      />
                    ) : (
                      <span className="issue-field" style={{ fontWeight: 600 }}>{String(col.name || "")}</span>
                    )}
                    {editable ? (
                      <select
                        className="structured-input"
                        value={String(col.data_type || "string")}
                        onChange={(e) => updateColumn(i, "data_type", e.target.value)}
                        style={{ width: 100 }}
                      >
                        {dataTypes.map((t) => <option key={t} value={t}>{t}</option>)}
                      </select>
                    ) : (
                      <span className="issue-type" style={{ opacity: 0.7 }}>{String(col.data_type || "string")}</span>
                    )}
                    {editable ? (
                      <input
                        className="structured-input"
                        type="number"
                        value={col.max_length as number || 0}
                        onChange={(e) => updateColumn(i, "max_length", parseInt(e.target.value) || 0)}
                        style={{ width: 60 }}
                        title="Max length"
                      />
                    ) : (
                      <span className="text-dim" style={{ fontSize: 11 }}>max:{String(col.max_length || "?")}</span>
                    )}
                    {editable ? (
                      <input
                        className="structured-input"
                        type="text"
                        value={String(col.business_name || "")}
                        onChange={(e) => updateColumn(i, "business_name", e.target.value || null)}
                        placeholder="Business name"
                        style={{ flex: 1, minWidth: 120 }}
                      />
                    ) : (
                      col.business_name != null && String(col.business_name) !== "" && (
                        <span className="text-dim" style={{ fontSize: 11, fontStyle: "italic" }}>
                          {String(col.business_name)}
                        </span>
                      )
                    )}
                    {flagTags.map(tag => (
                      <span key={tag} className="issue-tag" style={{ fontSize: 10 }}>{tag}</span>
                    ))}
                    {editable && (
                      <button className="btn btn-danger btn-sm" onClick={() => rejectColumn(i)} style={{ padding: "2px 8px", fontSize: 11 }}>
                        Reject
                      </button>
                    )}
                  </div>
                );
              })}
              {editable && columns.length === 0 && (
                <div className="text-dim" style={{ padding: 12 }}>No columns defined. Click "+ Add Column" to add one.</div>
              )}
            </div>
          </div>
        )}

        {/* Valid Value Sets */}
        {(Object.keys(validSets).length > 0 || editable) && (
          <div className="flow-summary-section">
            <h4 style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <span>Valid Value Sets ({Object.keys(validSets).length})</span>
              {editable && (
                <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                  <input
                    className="structured-input"
                    type="text"
                    value={newVvField}
                    onChange={(e) => setNewVvField(e.target.value)}
                    placeholder="Field name"
                    style={{ width: 130, fontSize: 12 }}
                    onKeyDown={(e) => { if (e.key === "Enter") addValidValueSet(); }}
                  />
                  <button className="btn btn-sm btn-primary" onClick={addValidValueSet} style={{ fontSize: 12 }}>
                    + Add Set
                  </button>
                </div>
              )}
            </h4>
            <div className="processor-list">
              {Object.entries(validSets).map(([field, values]) => (
                <div key={field} className="processor-item" style={{ flexWrap: "wrap" }}>
                  <span className="processor-type-badge">{field}</span>
                  {editable ? (
                    <>
                      <input
                        className="structured-input"
                        type="text"
                        value={(values || []).join(", ")}
                        onChange={(e) => updateValidValues(field, e.target.value)}
                        style={{ flex: 1, minWidth: 200 }}
                        title="Comma-separated valid values"
                      />
                      <button className="btn btn-danger btn-sm" onClick={() => rejectValidValueField(field)} style={{ padding: "2px 8px", fontSize: 11 }}>
                        Reject
                      </button>
                    </>
                  ) : (
                    <span className="processor-name">{(values || []).join(", ")}</span>
                  )}
                </div>
              ))}
              {editable && Object.keys(validSets).length === 0 && (
                <div className="text-dim" style={{ padding: 12 }}>No valid value sets defined. Enter a field name above and click "+ Add Set".</div>
              )}
            </div>
          </div>
        )}

        {/* Quality Rules / Summary */}
        {(qualityIssues.length > 0 || editable) && (
          <div className="flow-summary-section">
            <h4 style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <span>Quality Rules ({qualityIssues.length})</span>
              {editable && (
                <button className="btn btn-sm btn-primary" onClick={addIssue} style={{ fontSize: 12 }}>
                  + Add Rule
                </button>
              )}
            </h4>
            <div className="flow-issues-list">
              {qualityIssues.map((issue, i) => (
                <div key={i} className="flow-issue-item" style={editable ? { flexWrap: "wrap", gap: 6, padding: "8px 10px" } : undefined}>
                  {editable ? (
                    <>
                      <select
                        className="structured-input"
                        value={String(issue.severity || "low")}
                        onChange={(e) => updateIssue(i, "severity", e.target.value)}
                        style={{ width: 90 }}
                      >
                        {severities.map((s) => <option key={s} value={s}>{s}</option>)}
                      </select>
                      <input
                        className="structured-input"
                        type="text"
                        value={String(issue.field || "")}
                        onChange={(e) => updateIssue(i, "field", e.target.value)}
                        placeholder="Field name"
                        style={{ width: 130 }}
                      />
                      <input
                        className="structured-input"
                        type="text"
                        value={String(issue.issue_type || "")}
                        onChange={(e) => updateIssue(i, "issue_type", e.target.value)}
                        placeholder="Issue type"
                        style={{ width: 140 }}
                      />
                      <input
                        className="structured-input"
                        type="number"
                        value={issue.affected_pct as number || 0}
                        onChange={(e) => updateIssue(i, "affected_pct", parseFloat(e.target.value) || 0)}
                        style={{ width: 60 }}
                        title="Affected %"
                        step="0.01"
                      />
                      <span className="text-dim" style={{ fontSize: 11 }}>%</span>
                      <input
                        className="structured-input"
                        type="text"
                        value={String(issue.description || "")}
                        onChange={(e) => updateIssue(i, "description", e.target.value)}
                        placeholder="Description"
                        style={{ flex: 1, minWidth: 200 }}
                      />
                      <input
                        className="structured-input"
                        type="text"
                        value={String(issue.suggested_fix || "")}
                        onChange={(e) => updateIssue(i, "suggested_fix", e.target.value)}
                        placeholder="Suggested fix"
                        style={{ flex: 1, minWidth: 200 }}
                      />
                      <button className="btn btn-danger btn-sm" onClick={() => rejectIssue(i)} style={{ padding: "2px 8px", fontSize: 11 }}>
                        Reject
                      </button>
                    </>
                  ) : (
                    <>
                      <span className={`severity-badge ${String(issue.severity || "low")}`}>
                        {String(issue.severity || "low")}
                      </span>
                      <span className="issue-field">{String(issue.field || "")}</span>
                      <span className={`issue-type ${String(issue.issue_type || "")}`}>
                        {String(issue.issue_type || "").replace(/_/g, " ")}
                      </span>
                      <span className="issue-pct">{String(issue.affected_pct || 0)}%</span>
                    </>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
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
          Saved Files
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
              Dataset Name:
              <input type="text" value={specName} onChange={(e) => setSpecName(e.target.value)} />
            </label>
          </div>

          <div className="nifi-issues">
            <div className="nifi-issues-header">
              <h3>Rules ({rules.length})</h3>
              <div className="nifi-issues-header-actions">
                <button className="btn btn-sm" onClick={toggleAll}>
                  {selected.size === rules.length ? "Deselect All" : "Select All"}
                </button>
              </div>
            </div>

            {loading === "detecting" && <div className="loading">Detecting issues...</div>}

            {rules.map((rule, idx) => (
              <div key={idx} className="rule-card">
                <div className="rule-row">
                  <input
                    type="checkbox"
                    checked={selected.has(idx)}
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
                </div>
              </div>
            ))}

            {!loading && rules.length === 0 && (
              <div className="text-dim" style={{ padding: 12 }}>
                No rules detected. Load data first.
              </div>
            )}
          </div>

          <div className="nifi-actions">
            <button
              className="btn btn-primary"
              onClick={handleGenerate}
              disabled={selected.size === 0 || loading === "generating"}
            >
              {loading === "generating" ? "Generating..." : `Generate Metadata (${selected.size} rules)`}
            </button>
          </div>

          {yamlResult && (
            <div className="nifi-output">
              <div className="nifi-output-header">
                <h3>Generated Metadata</h3>
                <div style={{ display: "flex", gap: 8 }}>
                  <div className="view-toggle">
                    <button className={`btn btn-sm ${genView === "json" ? "btn-primary" : "btn-secondary"}`} onClick={() => setGenView("json")}>
                      JSON
                    </button>
                    <button className={`btn btn-sm ${genView === "yaml" ? "btn-primary" : "btn-secondary"}`} onClick={() => setGenView("yaml")}>
                      YAML
                    </button>
                    <button className={`btn btn-sm ${genView === "structured" ? "btn-primary" : "btn-secondary"}`} onClick={() => setGenView("structured")}>
                      Structured
                    </button>
                  </div>
                  <button className="btn btn-primary" onClick={handleSaveMetadata}>
                    Save
                  </button>
                  <button className="btn btn-primary" onClick={() => handleDownload("json")}>
                    Download JSON
                  </button>
                  <button className="btn btn-secondary" onClick={() => handleDownload("yaml")}>
                    Download YAML
                  </button>
                </div>
              </div>
              {saveSuccess && <div className="save-success">{saveSuccess}</div>}
              {yamlResult.validation && renderValidation(yamlResult.validation)}
              {genView === "json" ? (
                <pre className="yaml-content">{JSON.stringify(yamlResult.yaml_dict, null, 2)}</pre>
              ) : genView === "yaml" ? (
                <pre className="yaml-content">{yamlResult.yaml_content}</pre>
              ) : (
                renderStructuredView(yamlResult.yaml_dict)
              )}
            </div>
          )}
        </div>
      )}

      {/* ===== SAVED FILES TAB ===== */}
      {subTab === "saved" && (
        <div className="nifi-saved-tab">
          <div className="nifi-issues-header">
            <h3>Saved Metadata Files</h3>
            <button className="btn btn-sm" onClick={refreshSavedFiles} disabled={savedLoading}>
              {savedLoading ? "Loading..." : "Refresh"}
            </button>
          </div>

          {savedLoading && !savedFiles.length && <div className="loading">Loading saved files...</div>}

          {savedError && <div className="pipeline-error">{savedError}</div>}

          {!savedLoading && !savedError && savedFiles.length === 0 && (
            <div className="loading">No saved metadata files yet. Generate and save one, or run the pipeline.</div>
          )}

          {savedFiles.map((file) => (
            <div key={file.id} className="saved-flow-card">
              <div className="saved-flow-header">
                <h4>{file.name}</h4>
                <span className="text-dim">v{file.current_version} &middot; {file.issues_addressed} issues</span>
              </div>
              <div className="saved-flow-meta">
                <span className="text-dim">Created: {new Date(file.created_at).toLocaleDateString()}</span>
                <span className="text-dim">Updated: {new Date(file.updated_at).toLocaleDateString()}</span>
                <span className="text-dim">{file.versions.length} version{file.versions.length !== 1 ? "s" : ""}</span>
              </div>
              {file.issues_summary.length > 0 && (
                <div className="saved-flow-tags">
                  {file.issues_summary.slice(0, 5).map((tag, i) => (
                    <span key={i} className="issue-tag">{tag}</span>
                  ))}
                  {file.issues_summary.length > 5 && (
                    <span className="issue-tag">+{file.issues_summary.length - 5} more</span>
                  )}
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
              File Name:
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
            <button className={`btn btn-sm ${editorView === "json" ? "btn-primary" : "btn-secondary"}`} onClick={() => setEditorView("json")}>
              JSON
            </button>
            <button className={`btn btn-sm ${editorView === "yaml" ? "btn-primary" : "btn-secondary"}`} onClick={() => setEditorView("yaml")}>
              YAML
            </button>
            <button className={`btn btn-sm ${editorView === "structured" ? "btn-primary" : "btn-secondary"}`} onClick={() => setEditorView("structured")}>
              Structured
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
              {editorView === "json" ? (
                <textarea
                  className="json-editor"
                  value={editJson}
                  onChange={(e) => setEditJson(e.target.value)}
                  spellCheck={false}
                />
              ) : editorView === "yaml" ? (
                <textarea
                  className="json-editor"
                  value={editYaml}
                  onChange={(e) => setEditYaml(e.target.value)}
                  spellCheck={false}
                />
              ) : (
                renderStructuredView(editDict, true)
              )}
            </div>
          </div>

          <div className="editor-actions">
            <button className="btn btn-primary" onClick={handleEditorSave} disabled={editSaving}>
              {editSaving ? "Saving..." : "Save Changes"}
            </button>
            <button className="btn btn-primary" onClick={() => handleEditorDownload("json")}>
              Download JSON
            </button>
            <button className="btn btn-secondary" onClick={() => handleEditorDownload("yaml")}>
              Download YAML
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
