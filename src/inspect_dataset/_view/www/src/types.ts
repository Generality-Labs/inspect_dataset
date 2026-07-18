export interface DatasetInfo {
  slug: string;
  dataset_name: string;
  split: string | null;
  total_samples: number;
  total_findings: number;
  by_severity: Record<string, number>;
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
