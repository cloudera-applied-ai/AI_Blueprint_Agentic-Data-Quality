import { useState, useEffect } from "react";
import { getPreview, getColumns } from "../api/client";
import type { ColumnMeta, ColumnProfile, QueryResult } from "../types";

interface DataViewProps {
  profiles: ColumnProfile[];
}

export default function DataView({ profiles }: DataViewProps) {
  const [activeTab, setActiveTab] = useState<"preview" | "stats">("preview");
  const [preview, setPreview] = useState<QueryResult | null>(null);
  const [columns, setColumns] = useState<ColumnMeta[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [previewLimit, setPreviewLimit] = useState(100);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([getPreview(previewLimit), getColumns()])
      .then(([prev, cols]) => {
        if (!cancelled) {
          setPreview(prev);
          setColumns(cols);
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [previewLimit]);

  if (loading) {
    return <div className="loading">Loading data...</div>;
  }

  if (error) {
    return <div className="pipeline-error">{error}</div>;
  }

  return (
    <div className="dataview-container">
      <div className="dataview-tabs">
        <button
          className={activeTab === "preview" ? "active" : ""}
          onClick={() => setActiveTab("preview")}
        >
          Data Preview
        </button>
        <button
          className={activeTab === "stats" ? "active" : ""}
          onClick={() => setActiveTab("stats")}
        >
          Column Stats ({profiles.length || columns.length})
        </button>
      </div>

      {activeTab === "preview" && preview && (
        <div className="dataview-preview">
          <div className="dataview-preview-header">
            <span className="text-dim">
              Showing {preview.rows.length} of {preview.row_count} rows
            </span>
            <div className="dataview-limit-controls">
              <label>
                Rows:
                <select value={previewLimit} onChange={(e) => setPreviewLimit(Number(e.target.value))}>
                  <option value={50}>50</option>
                  <option value={100}>100</option>
                  <option value={500}>500</option>
                  <option value={1000}>1000</option>
                </select>
              </label>
            </div>
          </div>
          <div className="data-table-container">
            <table className="data-table">
              <thead>
                <tr>
                  {preview.columns.map((col) => (
                    <th key={col}>{col}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {preview.rows.map((row, ri) => (
                  <tr key={ri}>
                    {row.map((cell, ci) => (
                      <td key={ci}>{cell ?? <span className="text-dim">NULL</span>}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {activeTab === "stats" && (
        <div className="dataview-stats">
          {profiles.length > 0 ? (
            <>
              <div className="dataview-stats-header">
                <span className="text-dim">{profiles.length} columns profiled</span>
              </div>
              <div className="dataview-stats-grid">
                {profiles.map((p) => (
                  <div key={p.field_name} className="dataview-stat-card">
                    <div className="stat-card-header">
                      <span className="stat-card-name">{p.field_name}</span>
                    </div>
                    <div className="stat-card-body">
                      <div className="stat-card-row">
                        <span className="stat-card-label">Total</span>
                        <span>{p.total_count.toLocaleString()}</span>
                      </div>
                      <div className="stat-card-row">
                        <span className="stat-card-label">Distinct</span>
                        <span>{p.distinct_count.toLocaleString()}</span>
                      </div>
                      <div className="stat-card-row">
                        <span className="stat-card-label">Nulls</span>
                        <span className={p.null_pct > 50 ? "stat-value bad" : ""}>
                          {p.null_count.toLocaleString()} ({p.null_pct}%)
                        </span>
                      </div>
                      <div className="stat-card-row">
                        <span className="stat-card-label">Length</span>
                        <span>{p.min_length}–{p.max_length} (avg {p.avg_length})</span>
                      </div>
                      <div className="stat-card-row">
                        <span className="stat-card-label">Max Allowed</span>
                        <span>{p.max_allowed_length}</span>
                      </div>
                      {p.length_violation_count > 0 && (
                        <div className="stat-card-row">
                          <span className="stat-card-label">Length Violations</span>
                          <span className="stat-value bad">{p.length_violation_count.toLocaleString()}</span>
                        </div>
                      )}
                    </div>
                    {p.top_values.length > 0 && (
                      <div className="stat-card-top-values">
                        <span className="stat-card-label">Top Values</span>
                        {p.top_values.slice(0, 5).map((tv, i) => (
                          <div key={i} className="stat-card-tv">
                            <span className="tv-val">{tv.value || "(empty)"}</span>
                            <span className="tv-cnt">{tv.count.toLocaleString()}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="dataview-stats-empty">
              <h4>Column Metadata</h4>
              <p className="text-dim">Run the pipeline to see detailed column statistics. Showing basic metadata below.</p>
              <div className="dataview-meta-grid">
                {columns.map((col) => (
                  <div key={col.field_name} className="dataview-meta-card">
                    <div className="stat-card-header">
                      <span className="stat-card-name">{col.field_name}</span>
                    </div>
                    <div className="stat-card-body">
                      <div className="stat-card-row">
                        <span className="stat-card-label">Position</span>
                        <span>{col.position}</span>
                      </div>
                      <div className="stat-card-row">
                        <span className="stat-card-label">Max Length</span>
                        <span>{col.max_length}</span>
                      </div>
                      <div className="stat-card-row">
                        <span className="stat-card-label">Business Name</span>
                        <span>{col.business_name || "—"}</span>
                      </div>
                      <div className="stat-card-flags">
                        {col.is_code_field && <span className="field-flag code">CODE</span>}
                        {col.is_date_field && <span className="field-flag date">DATE</span>}
                        {col.is_phone_field && <span className="field-flag phone">PHONE</span>}
                        {col.is_blank_field && <span className="field-flag blank">BLANK</span>}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
