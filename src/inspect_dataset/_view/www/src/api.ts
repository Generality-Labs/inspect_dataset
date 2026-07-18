import type {
  DatasetInfo,
  Finding,
  Sample,
  SampleDetail,
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
