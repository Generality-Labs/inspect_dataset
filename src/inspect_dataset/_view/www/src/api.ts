import type {
  CachedDataset,
  DatasetInfo,
  ExploreRecordDetail,
  ExplorerSession,
  Finding,
  InstalledTask,
  RecordsPage,
  Sample,
  SampleDetail,
  SchemaInfo,
  Summary,
  TriageStatus,
} from "./types";

const BASE = "/api";

export async function fetchDatasets(): Promise<DatasetInfo[]> {
  const res = await fetch(`${BASE}/datasets`);
  return res.json();
}

export async function fetchSummary(slug: string): Promise<Summary> {
  const res = await fetch(`${BASE}/${slug}/summary`);
  return res.json();
}

export async function fetchFindings(slug: string): Promise<Finding[]> {
  const res = await fetch(`${BASE}/${slug}/findings`);
  return res.json();
}

export async function fetchSamples(slug: string): Promise<Sample[]> {
  const res = await fetch(`${BASE}/${slug}/samples`);
  if (!res.ok) return [];
  return res.json();
}

export async function postTriage(
  slug: string,
  findingId: number,
  status: TriageStatus,
): Promise<void> {
  await fetch(`${BASE}/${slug}/triage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ finding_id: findingId, status }),
  });
}

export function exportUrl(slug: string): string {
  return `${BASE}/${slug}/export`;
}

export async function fetchSampleDetail(
  slug: string,
  idx: number,
): Promise<SampleDetail | null> {
  try {
    const res = await fetch(`${BASE}/${slug}/sample/${idx}`);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

// ── Explorer / discovery API ───────────────────────────────────────────────

export async function fetchHfSchema(
  repoId: string,
  config?: string,
): Promise<SchemaInfo | null> {
  const params = new URLSearchParams({ dataset: repoId });
  if (config) params.set("config", config);
  try {
    const res = await fetch(`${BASE}/discover/hf-schema?${params}`);
    if (!res.ok) return null;
    const data = await res.json();
    return {
      session_id: "",
      source: repoId,
      total: 0,
      schema: data.schema ?? [],
    };
  } catch {
    return null;
  }
}

export async function fetchCachedDatasets(): Promise<CachedDataset[]> {
  const res = await fetch(`${BASE}/discover/cached`);
  if (!res.ok) return [];
  return res.json();
}

export async function fetchInstalledTasks(): Promise<InstalledTask[]> {
  const res = await fetch(`${BASE}/discover/tasks`);
  if (!res.ok) return [];
  return res.json();
}

export async function loadExplorerSession(
  source: string,
  sourceType: "hf" | "inspect_task",
  split: string,
  limit?: number,
  config?: string,
): Promise<ExplorerSession> {
  const res = await fetch(`${BASE}/explore/load`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      source,
      source_type: sourceType,
      split,
      limit: limit ?? null,
      config: config || null,
    }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error ?? `Failed to load dataset: ${res.status}`);
  }
  return res.json();
}

export async function fetchExplorerSchema(
  sessionId: string,
): Promise<SchemaInfo> {
  const res = await fetch(`${BASE}/explore/${sessionId}/schema`);
  if (!res.ok) throw new Error(`Schema fetch failed: ${res.status}`);
  return res.json();
}

export async function fetchExplorerRecords(
  sessionId: string,
  offset: number,
  limit: number,
): Promise<RecordsPage> {
  const res = await fetch(
    `${BASE}/explore/${sessionId}/records?offset=${offset}&limit=${limit}`,
  );
  if (!res.ok) throw new Error(`Records fetch failed: ${res.status}`);
  return res.json();
}

export async function fetchExplorerRecord(
  sessionId: string,
  idx: number,
): Promise<ExploreRecordDetail | null> {
  try {
    const res = await fetch(`${BASE}/explore/${sessionId}/record/${idx}`);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}
