export interface DatasetInfo {
  slug: string;
  dataset_name: string;
  split: string | null;
  total_samples: number;
  total_findings: number;
  by_severity: Record<string, number>;
}

export interface CachedDataset {
  repo_id: string;
  size_on_disk: number;
  splits: string[];
  configs: string[];
  last_modified: number;
}

export interface InstalledTask {
  name: string;
  package: string;
}

export interface ExplorerSession {
  session_id: string;
  source: string;
  source_type: "hf" | "inspect_task";
  split: string;
  config: string | null;
  total: number;
  columns: string[];
}

export interface SchemaField {
  name: string;
  type: "str" | "int" | "float" | "bool" | "image" | "list" | "dict" | "null";
  hf_type?: string;
  null_count: number;
  total: number;
  unique_count?: number;
  min_length?: number;
  max_length?: number;
  avg_length?: number;
  min?: number;
  max?: number;
  mean?: number;
}

export interface SchemaInfo {
  session_id: string;
  source: string;
  total: number;
  schema: SchemaField[];
}

export type CellValue =
  | string
  | number
  | boolean
  | null
  | { __type: "image"; path: string }
  | { __type: "bytes"; size: number }
  | Record<string, unknown>
  | unknown[];

export interface ExploreRow {
  __index: number;
  [key: string]: CellValue;
}

export interface RecordsPage {
  session_id: string;
  offset: number;
  limit: number;
  total: number;
  rows: ExploreRow[];
}

export interface ExploreRecordDetail {
  index: number;
  record: Record<string, CellValue>;
  images: { field: string; data_url: string }[];
  files: { name: string; data_url: string }[];
}

export interface ScannerStats {
  total: number;
  high: number;
  medium: number;
  low: number;
}

export interface Summary {
  dataset_name: string;
  split: string | null;
  total_samples: number;
  total_findings: number;
  by_scanner: Record<string, ScannerStats>;
  by_severity: Record<string, number>;
}

export interface Sample {
  index: number;
  question: string;
  answer: string;
  id?: string | number;
}

export type TriageStatus = "pending" | "confirmed" | "dismissed";

export interface ScannerInfo {
  name: string;
  description: string;
  kind: "static" | "llm";
}

export interface ExploreFinding {
  id: number;
  scanner: string;
  severity: "high" | "medium" | "low";
  category: string;
  explanation: string;
  sample_index: number;
  sample_id: string | number | null;
  line?: number | null;
  metadata: Record<string, unknown>;
}

export interface ScanResult {
  session_id: string;
  total_findings: number;
  findings: ExploreFinding[];
}

export interface SampleImage {
  field: string;
  data_url: string;
}

export interface SampleFile {
  name: string;
  data_url: string;
}

export interface ToolOutput {
  name: string;
  text: string;
}

export interface SampleDetail {
  index: number;
  question: string;
  answer: string;
  id?: string | number | null;
  images: SampleImage[];
  files: SampleFile[];
  tool_outputs?: ToolOutput[];
  line_offset?: number;
}

export interface Finding {
  id: number;
  scanner: string;
  severity: "high" | "medium" | "low";
  category: string;
  explanation: string;
  sample_index: number;
  sample_id: string | number | null;
  line?: number | null;
  metadata: Record<string, unknown>;
  triage_status: TriageStatus;
}
