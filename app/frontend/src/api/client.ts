import type {
  LLMConfig,
  DataStatus,
  ColumnMeta,
  ColumnProfile,
  QualityIssue,
  QueryResult,
  NiFiFlowResult,
  SavedFlowEntry,
  SavedFlowDetail,
  SparkJobResult,
  SavedJobEntry,
  SavedJobDetail,
  MetadataYamlResult,
  SavedMetadataEntry,
  SavedMetadataDetail,
  ClassificationResult,
  SavedClassificationEntry,
  SavedClassificationDetail,
} from "../types";
import { streamSSE } from "./streaming";

const BASE = "/api";

async function fetchJSON<T>(url: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(url, opts);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json();
}

function post<T>(url: string, body: unknown): Promise<T> {
  return fetchJSON<T>(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

// Data endpoints
export const loadPreloaded = () => post<{ status: string; row_count: number; column_count: number; columns: string[] }>(`${BASE}/data/load`, {});

export const uploadFiles = async (dataFile: File, metadataFile: File) => {
  const form = new FormData();
  form.append("data_file", dataFile);
  form.append("metadata_file", metadataFile);
  return fetchJSON<{ status: string; row_count: number; column_count: number }>(`${BASE}/data/upload`, {
    method: "POST",
    body: form,
  });
};

export const getDataStatus = () => fetchJSON<DataStatus>(`${BASE}/data/status`);
export const getColumns = () => fetchJSON<ColumnMeta[]>(`${BASE}/data/columns`);
export const getPreview = (limit = 100) => fetchJSON<QueryResult>(`${BASE}/data/preview?limit=${limit}`);
export const runQuery = (sql: string) => post<QueryResult>(`${BASE}/data/query`, { sql });
export const profileColumn = (field_name: string) => post<ColumnProfile>(`${BASE}/data/profile`, { field_name });
export const detectIssues = (field_names: string[] = []) => post<QualityIssue[]>(`${BASE}/data/detect-issues`, { field_names });

// Chat endpoints
export const configureLLM = (config: LLMConfig) => post<{ status: string }>(`${BASE}/chat/configure`, config);
export const testConnection = () => post<{ ok: boolean; message: string }>(`${BASE}/chat/test-connection`, {});
export const getLLMConfig = () => fetchJSON<{ endpoint_type: string; base_url: string; model: string; has_key: boolean; key_source: string }>(`${BASE}/chat/config`);

export function streamChat(messages: { role: string; content: string }[]) {
  return streamSSE(`${BASE}/chat/message`, { messages });
}

function put<T>(url: string, body: unknown): Promise<T> {
  return fetchJSON<T>(url, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

function del<T>(url: string, body?: unknown): Promise<T> {
  return fetchJSON<T>(url, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  });
}

// NiFi endpoints
export const detectNiFiIssues = () => post<QualityIssue[]>(`${BASE}/nifi/detect-issues`, {});
export const generateNiFiFlow = (flow_name: string, rules: QualityIssue[]) =>
  post<NiFiFlowResult>(`${BASE}/nifi/generate`, { rules, flow_name });

// Saved flows CRUD
export const listSavedFlows = () => fetchJSON<SavedFlowEntry[]>(`${BASE}/nifi/flows`);
export const saveNewFlow = (name: string, flow: Record<string, unknown>, issues: Record<string, unknown>[] = [], design_rationale?: string | null, note = "Initial generation") =>
  post<SavedFlowEntry>(`${BASE}/nifi/flows`, { name, flow, issues, design_rationale: design_rationale ?? null, note });
export const getSavedFlow = (id: string) => fetchJSON<SavedFlowDetail>(`${BASE}/nifi/flows/${id}`);
export const getSavedFlowVersion = (id: string, version: number) => fetchJSON<SavedFlowDetail>(`${BASE}/nifi/flows/${id}/versions/${version}`);
export const updateSavedFlow = (id: string, data: { name?: string; flow?: Record<string, unknown>; note?: string }) =>
  put<SavedFlowEntry>(`${BASE}/nifi/flows/${id}`, data);
export const deleteSavedFlow = (id: string) => del<{ status: string }>(`${BASE}/nifi/flows/${id}`);
export const cloneSavedFlow = (id: string, new_name?: string) => post<SavedFlowEntry>(`${BASE}/nifi/flows/${id}/clone`, { new_name: new_name ?? null });

// Schema generation
export const generateSchema = (table_name?: string) =>
  post<{ json_schema: Record<string, unknown>; columns: Record<string, unknown>[] }>(
    `${BASE}/data/generate-schema`, { table_name }
  );

// Pipeline endpoint
export function streamPipeline() {
  return streamSSE(`${BASE}/data/pipeline`, {});
}

// LLM-enhanced analysis streaming endpoints
export function streamIssuesAnalysis(field_names: string[] = []) {
  return streamSSE(`${BASE}/data/detect-issues/analyze`, { field_names });
}

export function streamProfileAnalysis(field_name: string) {
  return streamSSE(`${BASE}/data/profile/analyze`, { field_name });
}

export function streamNiFiDesign(flow_name: string, rules: QualityIssue[]) {
  return streamSSE(`${BASE}/nifi/generate/design`, { rules, flow_name });
}

// Spark endpoints
export const detectSparkIssues = () => post<QualityIssue[]>(`${BASE}/spark/detect-issues`, {});
export const generateSparkJob = (job_name: string, rules: QualityIssue[], output_format = "parquet") =>
  post<SparkJobResult>(`${BASE}/spark/generate`, { rules, job_name, output_format });

export function streamSparkDesign(job_name: string, rules: QualityIssue[], output_format = "parquet") {
  return streamSSE(`${BASE}/spark/generate/design`, { rules, job_name, output_format });
}

// Saved spark jobs CRUD
export const listSavedJobs = () => fetchJSON<SavedJobEntry[]>(`${BASE}/spark/jobs`);
export const saveNewJob = (
  name: string,
  job: Record<string, unknown>,
  pyspark_script: string,
  script_name: string,
  issues: Record<string, unknown>[] = [],
  design_rationale?: string | null,
  note = "Initial generation",
) => post<SavedJobEntry>(`${BASE}/spark/jobs`, { name, job, pyspark_script, script_name, issues, design_rationale: design_rationale ?? null, note });
export const getSavedJob = (id: string) => fetchJSON<SavedJobDetail>(`${BASE}/spark/jobs/${id}`);
export const getSavedJobVersion = (id: string, version: number) => fetchJSON<SavedJobDetail>(`${BASE}/spark/jobs/${id}/versions/${version}`);
export const updateSavedJob = (id: string, data: { name?: string; job?: Record<string, unknown>; pyspark_script?: string; note?: string }) =>
  put<SavedJobEntry>(`${BASE}/spark/jobs/${id}`, data);
export const deleteSavedJob = (id: string) => del<{ status: string }>(`${BASE}/spark/jobs/${id}`);
export const cloneSavedJob = (id: string, new_name?: string) => post<SavedJobEntry>(`${BASE}/spark/jobs/${id}/clone`, { new_name: new_name ?? null });

// Metadata endpoints
export const detectMetadataIssues = () => post<QualityIssue[]>(`${BASE}/metadata/detect-issues`, {});
export const generateMetadataYaml = (spec_name: string, rules: QualityIssue[]) =>
  post<MetadataYamlResult>(`${BASE}/metadata/generate`, { rules, spec_name });

// Saved metadata CRUD
export const listSavedMetadata = () => fetchJSON<SavedMetadataEntry[]>(`${BASE}/metadata/files`);
export const saveNewMetadata = (
  name: string,
  yaml_content: string,
  yaml_dict: Record<string, unknown>,
  issues: Record<string, unknown>[] = [],
  design_rationale?: string | null,
  note = "Initial generation",
) => post<SavedMetadataEntry>(`${BASE}/metadata/files`, { name, yaml_content, yaml_dict, issues, design_rationale: design_rationale ?? null, note });
export const getSavedMetadata = (id: string) => fetchJSON<SavedMetadataDetail>(`${BASE}/metadata/files/${id}`);
export const getSavedMetadataVersion = (id: string, version: number) => fetchJSON<SavedMetadataDetail>(`${BASE}/metadata/files/${id}/versions/${version}`);
export const updateSavedMetadata = (id: string, data: { name?: string; yaml_content?: string; yaml_dict?: Record<string, unknown>; note?: string }) =>
  put<SavedMetadataEntry>(`${BASE}/metadata/files/${id}`, data);
export const deleteSavedMetadata = (id: string) => del<{ status: string }>(`${BASE}/metadata/files/${id}`);
export const cloneSavedMetadata = (id: string, new_name?: string) => post<SavedMetadataEntry>(`${BASE}/metadata/files/${id}/clone`, { new_name: new_name ?? null });

// Classification endpoints
export const runClassification = (name = "AGT Classification", confidence_threshold = 0.7, use_llm = true) =>
  post<ClassificationResult>(`${BASE}/classification/classify`, { name, confidence_threshold, use_llm });

export function streamClassification(name = "AGT Classification", confidence_threshold = 0.7, use_llm = true) {
  return streamSSE(`${BASE}/classification/classify/stream`, { name, confidence_threshold, use_llm });
}

// Saved classification CRUD
export const listSavedClassifications = () => fetchJSON<SavedClassificationEntry[]>(`${BASE}/classification/files`);
export const saveNewClassification = (name: string, classification_data: Record<string, unknown>, note = "Initial classification") =>
  post<SavedClassificationEntry>(`${BASE}/classification/files`, { name, classification_data, note });
export const getSavedClassification = (id: string) => fetchJSON<SavedClassificationDetail>(`${BASE}/classification/files/${id}`);
export const getSavedClassificationVersion = (id: string, version: number) => fetchJSON<SavedClassificationDetail>(`${BASE}/classification/files/${id}/versions/${version}`);
export const updateSavedClassification = (id: string, data: { name?: string; classification_data?: Record<string, unknown>; note?: string }) =>
  put<SavedClassificationEntry>(`${BASE}/classification/files/${id}`, data);
export const deleteSavedClassification = (id: string) => del<{ status: string }>(`${BASE}/classification/files/${id}`);
export const cloneSavedClassification = (id: string, new_name?: string) => post<SavedClassificationEntry>(`${BASE}/classification/files/${id}/clone`, { new_name: new_name ?? null });
