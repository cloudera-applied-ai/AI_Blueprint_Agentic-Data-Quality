export interface LLMConfig {
  endpoint_type: string;
  base_url: string;
  model: string;
  api_key?: string;
}

export interface DataStatus {
  loaded: boolean;
  row_count?: number;
  column_count?: number;
}

export interface ColumnMeta {
  position: number;
  field_name: string;
  max_length: number;
  business_name: string;
  is_code_field: boolean;
  is_date_field: boolean;
  is_phone_field: boolean;
  is_blank_field: boolean;
}

export interface ColumnProfile {
  field_name: string;
  total_count: number;
  null_count: number;
  null_pct: number;
  distinct_count: number;
  min_length: number;
  max_length: number;
  avg_length: number;
  max_allowed_length: number;
  length_violation_count: number;
  top_values: { value: string; count: number }[];
}

export interface QualityIssue {
  field_name: string;
  issue_type: string;
  description: string;
  affected_count: number;
  affected_pct: number;
  sample_bad_values: string[];
  suggested_fix: string;
  params?: Record<string, unknown>;
}

export interface PipelineStage {
  stage: "profiling" | "detecting" | "schema" | "rules" | "nifi_generation" | "spark_generation" | "metadata_generation" | "classification";
  status: "started" | "progress" | "completed" | "skipped";
  total?: number;
  completed?: number;
  count?: number;
  reason?: string;
}

export interface DataQualityRule {
  id: number;
  field_name: string;
  issue_type: string;
  description: string;
  affected_count: number;
  affected_pct: number;
  sample_bad_values: string[];
  suggested_fix: string;
  params?: Record<string, unknown>;
  severity: "critical" | "high" | "medium" | "low";
  enabled: boolean;
}

export interface QueryResult {
  columns: string[];
  rows: (string | null)[][];
  row_count: number;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  tool_calls?: ToolCallEntry[];
}

export interface ToolCallEntry {
  name: string;
  arguments: Record<string, unknown>;
  result: string;
}

export interface SSEEvent {
  event: "tool_call" | "tool_result" | "content" | "done" | "error";
  data: Record<string, unknown>;
}

export interface NiFiFlowResult {
  flow_name: string;
  issues_addressed: number;
  issues: QualityIssue[];
  flow: Record<string, unknown>;
}

export interface FlowVersionMeta {
  version: number;
  created_at: string;
  note: string;
}

export interface SavedFlowEntry {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  issues_addressed: number;
  issues_summary: string[];
  versions: FlowVersionMeta[];
  current_version: number;
}

export interface SavedFlowDetail {
  metadata: SavedFlowEntry;
  flow_data: {
    flow: Record<string, unknown>;
    issues: QualityIssue[];
    design_rationale: string | null;
    saved_at: string;
    note: string;
  };
}

export interface SparkJobResult {
  job_name: string;
  issues_addressed: number;
  issues: QualityIssue[];
  job: Record<string, unknown>;
  pyspark_script: string;
  script_name: string;
}

export interface SavedJobEntry {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  issues_addressed: number;
  issues_summary: string[];
  versions: FlowVersionMeta[];
  current_version: number;
}

export interface SavedJobDetail {
  metadata: SavedJobEntry;
  job_data: {
    job: Record<string, unknown>;
    pyspark_script: string;
    script_name: string;
    issues: QualityIssue[];
    design_rationale: string | null;
    saved_at: string;
    note: string;
  };
}

export interface MetadataYamlResult {
  spec_name: string;
  issues_addressed: number;
  issues: QualityIssue[];
  yaml_content: string;
  yaml_dict: Record<string, unknown>;
  validation?: MetadataValidation;
}

export interface SavedMetadataEntry {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  issues_addressed: number;
  issues_summary: string[];
  versions: FlowVersionMeta[];
  current_version: number;
}

export interface SavedMetadataDetail {
  metadata: SavedMetadataEntry;
  file_data: {
    yaml_content: string;
    yaml_dict: Record<string, unknown>;
    issues: QualityIssue[];
    design_rationale: string | null;
    saved_at: string;
    note: string;
  };
}

export interface MetadataValidationFieldCheck {
  match: boolean;
  source: unknown;
  generated: unknown;
}

export interface MetadataValidationColumn {
  column: string;
  match: boolean;
  position: MetadataValidationFieldCheck;
  max_length: MetadataValidationFieldCheck;
  business_name: MetadataValidationFieldCheck;
}

export interface MetadataValidation {
  score: number;
  total_source_fields: number;
  total_generated_fields: number;
  matched: number;
  fully_correct: number;
  missing_fields: string[];
  extra_fields: string[];
  column_checks: MetadataValidationColumn[];
}

// Classification types
export interface ColumnClassificationResult {
  field_name: string;
  sensitivity_label: string;
  sensitivity_confidence: number;
  semantic_type: string;
  semantic_confidence: number;
  format_label: string;
  format_confidence: number;
  business_term: string;
  business_term_confidence: number;
  hl7_fhir_mapping: string;
  regulatory_tags: string[];
  classified_by: string;
}

export interface ClassificationResult {
  name: string;
  columns: ColumnClassificationResult[];
  confidence_threshold: number;
  llm_used: boolean;
  total_columns: number;
  classifier_only_count: number;
  llm_enhanced_count: number;
  created_at: string;
  summary: {
    sensitivity_counts: Record<string, number>;
    avg_sensitivity_confidence: number;
    avg_semantic_confidence: number;
    avg_format_confidence: number;
  };
}

export interface SavedClassificationEntry {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  total_columns: number;
  llm_used: boolean;
  sensitivity_summary: Record<string, number>;
  versions: FlowVersionMeta[];
  current_version: number;
}

export interface SavedClassificationDetail {
  metadata: SavedClassificationEntry;
  classification_data: {
    classification_data: ClassificationResult;
    saved_at: string;
    note: string;
  };
}
