import { useState, useEffect } from "react";
import {
  configureLLM,
  testConnection,
  getLLMConfig,
  loadPreloaded,
  uploadFiles,
  getDataStatus,
} from "../api/client";
import type { DataStatus } from "../types";
import { LOGO_PRESETS } from "../hooks/useSettings";

interface SidebarProps {
  dataStatus: DataStatus;
  setDataStatus: (s: DataStatus) => void;
  onDataLoaded: (s: DataStatus) => void;
  onQuickAction: (action: string) => void;
  pipelineRunning: boolean;
  pipelineRuleCount: number;
  onRerunPipeline: () => void;
  logoUrl: string;
  onLogoChange: (url: string) => void;
}

export default function Sidebar({
  dataStatus,
  setDataStatus,
  onDataLoaded,
  onQuickAction,
  pipelineRunning,
  pipelineRuleCount,
  onRerunPipeline,
  logoUrl,
  onLogoChange,
}: SidebarProps) {
  const [endpointType, setEndpointType] = useState("ollama");
  const [baseUrl, setBaseUrl] = useState("http://localhost:11434/v1");
  const [model, setModel] = useState("qwen2.5:14b");
  const [apiKey, setApiKey] = useState("");
  const [connStatus, setConnStatus] = useState<string>("");
  const [connOk, setConnOk] = useState<boolean | null>(null);
  const [saving, setSaving] = useState(false);
  const [keySource, setKeySource] = useState<string>("");

  const [dataSource, setDataSource] = useState<"preloaded" | "upload">("preloaded");
  const [dataFile, setDataFile] = useState<File | null>(null);
  const [metaFile, setMetaFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState("");

  const [llmOpen, setLlmOpen] = useState(true);
  const [dataOpen, setDataOpen] = useState(true);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [customLogoUrl, setCustomLogoUrl] = useState("");
  const [logoSearch, setLogoSearch] = useState("");
  const [logoSearchResults, setLogoSearchResults] = useState<string[]>([]);
  const [logoSearching] = useState(false);
  const [failedLogos, setFailedLogos] = useState<Set<string>>(new Set());

  useEffect(() => {
    getLLMConfig().then((cfg) => {
      setEndpointType(cfg.endpoint_type);
      setBaseUrl(cfg.base_url);
      setModel(cfg.model);
      setKeySource(cfg.key_source);
    }).catch(() => {});

    getDataStatus().then((s) => {
      if (s.loaded) {
        // Just update status without triggering pipeline on page refresh
        setDataStatus(s);
      }
    }).catch(() => {});
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      await configureLLM({
        endpoint_type: endpointType,
        base_url: baseUrl,
        model: model,
        api_key: apiKey || undefined,
      });
      setConnStatus("Settings saved");
      setConnOk(null);
    } catch (e) {
      setConnStatus(String(e));
      setConnOk(false);
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setConnStatus("Testing...");
    setConnOk(null);
    try {
      await handleSave();
      const result = await testConnection();
      setConnStatus(result.message);
      setConnOk(result.ok);
    } catch (e) {
      setConnStatus(String(e));
      setConnOk(false);
    }
  };

  const handleLoadData = async () => {
    setLoading(true);
    setLoadError("");
    try {
      if (dataSource === "preloaded") {
        const result = await loadPreloaded();
        onDataLoaded({ loaded: true, row_count: result.row_count, column_count: result.column_count });
      } else if (dataFile && metaFile) {
        const result = await uploadFiles(dataFile, metaFile);
        onDataLoaded({ loaded: true, row_count: result.row_count, column_count: result.column_count });
      } else {
        setLoadError("Please select both data and metadata files");
      }
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <h2>Data Quality Tool</h2>
      </div>

      <div className="sidebar-section">
        <button className="section-toggle" onClick={() => setLlmOpen(!llmOpen)}>
          {llmOpen ? "\u25BE" : "\u25B8"} LLM Configuration
        </button>
        {llmOpen && (
          <div className="section-content">
            <label>
              Endpoint Type
              <select value={endpointType} onChange={(e) => {
                setEndpointType(e.target.value);
                if (e.target.value === "ollama") {
                  setBaseUrl("http://localhost:11434/v1");
                } else if (e.target.value === "openai") {
                  setBaseUrl("https://api.openai.com/v1");
                  setModel("gpt-4o-mini");
                }
              }}>
                <option value="ollama">Ollama</option>
                <option value="openai">OpenAI Compatible</option>
                <option value="openai-compatible">Cloudera Inferencing</option>
              </select>
            </label>
            <label>
              Base URL
              <input type="text" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} />
            </label>
            <label>
              Model
              <input type="text" value={model} onChange={(e) => setModel(e.target.value)} />
            </label>
            {endpointType !== "ollama" && (
              <label>
                {endpointType === "openai" ? "API Key" : "API Key / CDP Token"}
                <input type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder={endpointType === "openai" ? "sk-..." : "Leave blank to use auto-detected token"} />
              </label>
            )}
            {keySource && (
              <div className="status-msg ok" style={{ fontSize: "0.8em", padding: "0.3rem 0.5rem" }}>
                API Key: {keySource === "user" ? "Manually entered" : keySource === "cdpcli" ? "CDP CLI (auto-refreshed)" : keySource === "jwt" ? "Auto-detected (/tmp/jwt)" : keySource === "env" ? "Environment variable (LLM_API_KEY / CDP_TOKEN)" : "Default (ollama)"}
              </div>
            )}
            <div style={{ display: "flex", gap: "0.5rem" }}>
              <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
                {saving ? "Saving..." : "Save"}
              </button>
              <button className="btn btn-secondary" onClick={handleTest}>
                Test Connection
              </button>
            </div>
            {connStatus && (
              <div className={`status-msg ${connOk === true ? "ok" : connOk === false ? "err" : ""}`}>
                {connStatus}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="sidebar-section">
        <button className="section-toggle" onClick={() => setDataOpen(!dataOpen)}>
          {dataOpen ? "\u25BE" : "\u25B8"} Data Source
        </button>
        {dataOpen && (
          <div className="section-content">
            <div className="radio-group">
              <label>
                <input type="radio" value="preloaded" checked={dataSource === "preloaded"} onChange={() => setDataSource("preloaded")} />
                Pre-loaded AGT
              </label>
              <label>
                <input type="radio" value="upload" checked={dataSource === "upload"} onChange={() => setDataSource("upload")} />
                Upload Files
              </label>
            </div>
            {dataSource === "upload" && (
              <>
                <label>
                  Data File (.txt)
                  <input type="file" accept=".txt,.csv" onChange={(e) => setDataFile(e.target.files?.[0] || null)} />
                </label>
                <label>
                  Metadata (.json)
                  <input type="file" accept=".json" onChange={(e) => setMetaFile(e.target.files?.[0] || null)} />
                </label>
              </>
            )}
            <button className="btn btn-primary" onClick={handleLoadData} disabled={loading}>
              {loading ? "Loading..." : "Load Data"}
            </button>
            {dataStatus.loaded && (
              <div className="status-msg ok">
                Loaded: {dataStatus.row_count?.toLocaleString()} rows, {dataStatus.column_count} columns
              </div>
            )}
            {loadError && <div className="status-msg err">{loadError}</div>}
          </div>
        )}
      </div>

      {dataStatus.loaded && (
        <div className="sidebar-section">
          <div className="section-label">Pipeline</div>
          <div className="quick-actions">
            <button
              className="btn btn-primary"
              onClick={onRerunPipeline}
              disabled={pipelineRunning}
            >
              {pipelineRunning ? "Running..." : "Re-run Pipeline"}
            </button>
            {pipelineRunning && (
              <div className="pipeline-sidebar-status">Running...</div>
            )}
            {!pipelineRunning && pipelineRuleCount > 0 && (
              <div className="pipeline-sidebar-status complete">
                Complete — {pipelineRuleCount} rule{pipelineRuleCount !== 1 ? "s" : ""}
              </div>
            )}
          </div>
        </div>
      )}

      {dataStatus.loaded && (
        <div className="sidebar-section">
          <div className="section-label">Quick Actions</div>
          <div className="quick-actions">
            <button className="btn btn-secondary" onClick={() => onQuickAction("What are the top data quality issues in this dataset?")}>
              Detect Issues
            </button>
            <button className="btn btn-secondary" onClick={() => onQuickAction("Generate a NiFi flow to fix all detected quality issues")}>
              Generate Flow
            </button>
          </div>
        </div>
      )}

      <div className="sidebar-section" style={{ marginTop: "auto" }}>
        <button className="section-toggle" onClick={() => setSettingsOpen(!settingsOpen)}>
          {settingsOpen ? "\u25BE" : "\u25B8"} Settings
        </button>
        {settingsOpen && (
          <div className="section-content">
            <label>Company Logo</label>
            <div className="logo-presets">
              {LOGO_PRESETS.map((p) => (
                <button
                  key={p.label}
                  className={`logo-preset-btn${logoUrl === p.url ? " selected" : ""}`}
                  onClick={() => { onLogoChange(p.url); setCustomLogoUrl(""); setLogoSearchResults([]); setLogoSearch(""); }}
                  title={p.label}
                >
                  <img src={p.url} alt={p.label} />
                  <span>{p.label}</span>
                </button>
              ))}
            </div>
            <label>
              Search Company Logo
              <div style={{ display: "flex", gap: "0.5rem" }}>
                <input
                  type="text"
                  value={logoSearch}
                  onChange={(e) => setLogoSearch(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && logoSearch.trim()) {
                      const q = logoSearch.trim().toLowerCase().replace(/\s+/g, "");
                      const hyphen = logoSearch.trim().toLowerCase().replace(/\s+/g, "-");
                      const domains = [`${q}.com`];
                      if (hyphen !== q) domains.push(`${hyphen}.com`);
                      domains.push(`${q}.co`, `${q}.io`, `${q}.org`);
                      const urls: string[] = [];
                      for (const d of domains) {
                        urls.push(`https://icon.horse/icon/${d}`);
                        urls.push(`https://www.google.com/s2/favicons?domain=${d}&sz=128`);
                      }
                      setFailedLogos(new Set());
                      setLogoSearchResults([...new Set(urls)]);
                    }
                  }}
                  placeholder="e.g. Apple, Ford, Verizon"
                  style={{ flex: 1 }}
                />
                <button
                  className="btn btn-primary"
                  disabled={!logoSearch.trim() || logoSearching}
                  onClick={() => {
                    const q = logoSearch.trim().toLowerCase().replace(/\s+/g, "");
                    const hyphen = logoSearch.trim().toLowerCase().replace(/\s+/g, "-");
                    const domains = [`${q}.com`];
                    if (hyphen !== q) domains.push(`${hyphen}.com`);
                    domains.push(`${q}.co`, `${q}.io`, `${q}.org`);
                    const urls: string[] = [];
                    for (const d of domains) {
                      urls.push(`https://logo.clearbit.com/${d}`);
                      urls.push(`https://icon.horse/icon/${d}`);
                      urls.push(`https://www.google.com/s2/favicons?domain=${d}&sz=128`);
                    }
                    setFailedLogos(new Set());
                    setLogoSearchResults([...new Set(urls)]);
                  }}
                  style={{ whiteSpace: "nowrap" }}
                >
                  Search
                </button>
              </div>
            </label>
            {logoSearchResults.length > 0 && (
              <div className="logo-search-results">
                {logoSearchResults.filter((url) => !failedLogos.has(url)).map((url) => (
                  <button
                    key={url}
                    className={`logo-search-result${logoUrl === url ? " selected" : ""}`}
                    onClick={() => { onLogoChange(url); }}
                    title="Click to use this logo"
                  >
                    <img
                      src={url}
                      alt="logo"
                      onError={() => { setFailedLogos((prev) => new Set(prev).add(url)); }}
                    />
                  </button>
                ))}
                {logoSearchResults.every((url) => failedLogos.has(url)) && (
                  <div className="status-msg" style={{ fontSize: "0.8em" }}>No logos found. Try a custom URL instead.</div>
                )}
              </div>
            )}
            <label>
              Custom Logo URL
              <div style={{ display: "flex", gap: "0.5rem" }}>
                <input
                  type="text"
                  value={customLogoUrl}
                  onChange={(e) => setCustomLogoUrl(e.target.value)}
                  placeholder="https://..."
                  style={{ flex: 1 }}
                />
                <button
                  className="btn btn-primary"
                  disabled={!customLogoUrl.trim()}
                  onClick={() => onLogoChange(customLogoUrl.trim())}
                  style={{ whiteSpace: "nowrap" }}
                >
                  Apply
                </button>
              </div>
            </label>
          </div>
        )}
      </div>
    </aside>
  );
}
