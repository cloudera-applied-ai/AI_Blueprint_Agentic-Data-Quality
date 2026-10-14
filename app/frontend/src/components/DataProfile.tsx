import { useState, useEffect } from "react";
import {
  getColumns,
  getPreview,
  profileColumn,
  detectIssues,
  streamIssuesAnalysis,
  streamProfileAnalysis,
} from "../api/client";
import { useAnalysisStream } from "../hooks/useAnalysisStream";
import type { ColumnMeta, ColumnProfile, QualityIssue, QueryResult } from "../types";

export default function DataProfile() {
  const [columns, setColumns] = useState<ColumnMeta[]>([]);
  const [selectedCol, setSelectedCol] = useState("");
  const [profile, setProfile] = useState<ColumnProfile | null>(null);
  const [issues, setIssues] = useState<QualityIssue[]>([]);
  const [preview, setPreview] = useState<QueryResult | null>(null);
  const [loading, setLoading] = useState("");
  const [activeTab, setActiveTab] = useState<"preview" | "profile" | "issues">("preview");

  // LLM analysis hooks
  const issuesAnalysis = useAnalysisStream<QualityIssue[]>("issues_data");
  const profileAnalysis = useAnalysisStream<ColumnProfile>("profile_data");

  useEffect(() => {
    getColumns().then(setColumns).catch(() => {});
    getPreview(50).then(setPreview).catch(() => {});
  }, []);

  const handleProfile = async (col: string) => {
    setSelectedCol(col);
    setLoading("profiling");
    try {
      const p = await profileColumn(col);
      setProfile(p);
      setActiveTab("profile");
    } catch (e) {
      console.error(e);
    } finally {
      setLoading("");
    }
  };

  const handleDetectIssues = async () => {
    setLoading("detecting");
    try {
      const i = await detectIssues();
      setIssues(i);
      setActiveTab("issues");
    } catch (e) {
      console.error(e);
    } finally {
      setLoading("");
    }
  };

  const handleAnalyzeIssues = () => {
    issuesAnalysis.runAnalysis(streamIssuesAnalysis());
  };

  const handleAnalyzeProfile = () => {
    if (!selectedCol) return;
    profileAnalysis.runAnalysis(streamProfileAnalysis(selectedCol));
  };

  return (
    <div className="data-profile">
      <div className="profile-tabs">
        <button className={activeTab === "preview" ? "active" : ""} onClick={() => setActiveTab("preview")}>
          Data Preview
        </button>
        <button className={activeTab === "profile" ? "active" : ""} onClick={() => setActiveTab("profile")}>
          Column Profile
        </button>
        <button
          className={activeTab === "issues" ? "active" : ""}
          onClick={() => { setActiveTab("issues"); if (issues.length === 0) handleDetectIssues(); }}
        >
          Quality Issues
        </button>
      </div>

      {activeTab === "preview" && preview && (
        <div className="data-table-container">
          <table className="data-table">
            <thead>
              <tr>
                {preview.columns.map((col) => (
                  <th key={col} onClick={() => handleProfile(col)} title="Click to profile">
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {preview.rows.slice(0, 50).map((row, i) => (
                <tr key={i}>
                  {row.map((cell, j) => (
                    <td key={j}>{cell ?? ""}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {activeTab === "profile" && (
        <div className="profile-view">
          <div className="column-selector">
            <label>
              Select Column:
              <select value={selectedCol} onChange={(e) => handleProfile(e.target.value)}>
                <option value="">-- Choose --</option>
                {columns.map((c) => (
                  <option key={c.field_name} value={c.field_name}>
                    {c.field_name} {c.business_name ? `(${c.business_name})` : ""}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {loading === "profiling" && <div className="loading">Profiling...</div>}

          {profile && !loading && (
            <div className="profile-card">
              <h3>{profile.field_name}</h3>
              <div className="profile-stats">
                <div className="stat">
                  <span className="stat-label">Total Rows</span>
                  <span className="stat-value">{profile.total_count.toLocaleString()}</span>
                </div>
                <div className="stat">
                  <span className="stat-label">Null/Empty</span>
                  <span className="stat-value">{profile.null_count.toLocaleString()} ({profile.null_pct}%)</span>
                </div>
                <div className="stat">
                  <span className="stat-label">Distinct</span>
                  <span className="stat-value">{profile.distinct_count.toLocaleString()}</span>
                </div>
                <div className="stat">
                  <span className="stat-label">Length (min/avg/max)</span>
                  <span className="stat-value">{profile.min_length} / {profile.avg_length} / {profile.max_length}</span>
                </div>
                <div className="stat">
                  <span className="stat-label">Max Allowed</span>
                  <span className="stat-value">{profile.max_allowed_length}</span>
                </div>
                <div className="stat">
                  <span className="stat-label">Length Violations</span>
                  <span className={`stat-value ${profile.length_violation_count > 0 ? "bad" : "good"}`}>
                    {profile.length_violation_count.toLocaleString()}
                  </span>
                </div>
              </div>

              <h4>Top Values</h4>
              <div className="top-values">
                {profile.top_values.map((tv, i) => (
                  <div key={i} className="top-value-row">
                    <span className="tv-value">{tv.value || "(empty)"}</span>
                    <div className="tv-bar-container">
                      <div
                        className="tv-bar"
                        style={{ width: `${(tv.count / profile.total_count) * 100}%` }}
                      />
                    </div>
                    <span className="tv-count">{tv.count.toLocaleString()}</span>
                  </div>
                ))}
              </div>

              {/* AI Analysis button */}
              <div className="ai-analysis-actions">
                <button
                  className="btn btn-primary btn-ai"
                  onClick={handleAnalyzeProfile}
                  disabled={profileAnalysis.isStreaming}
                >
                  {profileAnalysis.isStreaming ? "Analyzing..." : "Analyze with AI"}
                </button>
              </div>

              {/* AI Analysis panel */}
              {(profileAnalysis.analysisText || profileAnalysis.isStreaming || profileAnalysis.error) && (
                <div className="ai-analysis-panel">
                  <h4>AI Analysis</h4>
                  {profileAnalysis.error && (
                    <p className="analysis-error">{profileAnalysis.error}</p>
                  )}
                  {profileAnalysis.analysisText && (
                    <div className="analysis-content">{profileAnalysis.analysisText}</div>
                  )}
                  {profileAnalysis.isStreaming && !profileAnalysis.analysisText && (
                    <div className="loading">Waiting for LLM response...</div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {activeTab === "issues" && (
        <div className="issues-view">
          <div className="issues-header">
            <h3>Quality Issues</h3>
            <div className="issues-header-actions">
              <button className="btn btn-secondary" onClick={handleDetectIssues} disabled={loading === "detecting"}>
                {loading === "detecting" ? "Scanning..." : "Refresh"}
              </button>
              {issues.length > 0 && (
                <button
                  className="btn btn-primary btn-ai"
                  onClick={handleAnalyzeIssues}
                  disabled={issuesAnalysis.isStreaming}
                >
                  {issuesAnalysis.isStreaming ? "Analyzing..." : "Analyze with AI"}
                </button>
              )}
            </div>
          </div>

          {issues.length === 0 && !loading && <p className="no-issues">No issues detected yet. Click Refresh to scan.</p>}

          {issues.map((issue, i) => (
            <div key={i} className="issue-card">
              <div className="issue-header">
                <span className={`issue-type ${issue.issue_type}`}>{issue.issue_type.replace(/_/g, " ")}</span>
                <span className="issue-field">{issue.field_name}</span>
                <span className="issue-pct">{issue.affected_pct}%</span>
              </div>
              <p className="issue-desc">{issue.description}</p>
              <div className="issue-details">
                <span>Affected: {issue.affected_count.toLocaleString()} rows</span>
                <span>Samples: {issue.sample_bad_values.slice(0, 3).join(", ")}</span>
              </div>
              <p className="issue-fix">{issue.suggested_fix}</p>
            </div>
          ))}

          {/* AI Analysis panel */}
          {(issuesAnalysis.analysisText || issuesAnalysis.isStreaming || issuesAnalysis.error) && (
            <div className="ai-analysis-panel">
              <h4>AI Analysis</h4>
              {issuesAnalysis.error && (
                <p className="analysis-error">{issuesAnalysis.error}</p>
              )}
              {issuesAnalysis.analysisText && (
                <div className="analysis-content">{issuesAnalysis.analysisText}</div>
              )}
              {issuesAnalysis.isStreaming && !issuesAnalysis.analysisText && (
                <div className="loading">Waiting for LLM response...</div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
