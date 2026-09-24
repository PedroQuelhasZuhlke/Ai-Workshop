// Thin fetch wrapper. Every project-scoped call requires an API key set via
// `setApiKey` -- the backend checks project membership on every read, so a missing
// or wrong key surfaces as a real 401/404 from the server, never hidden here.

import type {
  Approval,
  DevUser,
  ExportRecord,
  Issue,
  MappingProposal,
  NormalizedRequirement,
  PartCandidate,
  Project,
  PurchasePlan,
  Run,
} from "./types";

const BASE = "/api";

let apiKey: string | null = localStorage.getItem("pcbpick_api_key");

export function setApiKey(key: string | null): void {
  apiKey = key;
  if (key) localStorage.setItem("pcbpick_api_key", key);
  else localStorage.removeItem("pcbpick_api_key");
}

export function getApiKey(): string | null {
  return apiKey;
}

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  isForm = false,
): Promise<T> {
  const headers: Record<string, string> = {};
  if (apiKey) headers["x-api-key"] = apiKey;
  let requestBody: BodyInit | undefined;
  if (isForm) {
    requestBody = body as FormData;
  } else if (body !== undefined) {
    headers["content-type"] = "application/json";
    requestBody = JSON.stringify(body);
  }
  const response = await fetch(`${BASE}${path}`, { method, headers, body: requestBody });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = await response.json();
      detail = typeof payload.detail === "string" ? payload.detail : JSON.stringify(payload.detail);
    } catch {
      // response had no JSON body
    }
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) return undefined as T;
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) return (await response.json()) as T;
  return undefined as T;
}

export { ApiError };

export const api = {
  registerUser: (displayName: string) =>
    request<DevUser>("POST", "/users", { display_name: displayName }),

  listProjects: () => request<Project[]>("GET", "/projects"),
  createProject: (name: string) => request<Project>("POST", "/projects", { name }),
  getProject: (projectId: string) => request<Project>("GET", `/projects/${projectId}`),
  addMember: (projectId: string, userId: string, role: string) =>
    request<void>("POST", `/projects/${projectId}/members`, { user_id: userId, role }),

  listRuns: (projectId: string) => request<Run[]>("GET", `/projects/${projectId}/runs`),
  uploadRun: (projectId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<Run>("POST", `/projects/${projectId}/runs`, form, true);
  },
  getRun: (projectId: string, runId: string) =>
    request<Run>("GET", `/projects/${projectId}/runs/${runId}`),

  getMapping: (projectId: string, runId: string) =>
    request<{ mapping_proposal: MappingProposal; line_count: number; issues: Issue[] }>(
      "GET",
      `/projects/${projectId}/runs/${runId}/mapping`,
    ),
  confirmMapping: (projectId: string, runId: string, mappings: Record<string, string | null>) =>
    request<Run>("POST", `/projects/${projectId}/runs/${runId}/mapping/confirm`, { mappings }),

  getRequirements: (projectId: string, runId: string) =>
    request<{ requirements: NormalizedRequirement[]; issues: Issue[] }>(
      "GET",
      `/projects/${projectId}/runs/${runId}/requirements`,
    ),
  resolveRequirement: (
    projectId: string,
    runId: string,
    requirementId: string,
    body: {
      category?: string;
      parameters?: Record<
        string,
        { value?: string; unit?: string; tolerance_pct?: string; min?: string; max?: string; raw_text: string }
      >;
      footprint?: Record<string, unknown>;
      compliance_required?: string[];
    },
  ) =>
    request<{ requirement: NormalizedRequirement }>(
      "POST",
      `/projects/${projectId}/runs/${runId}/requirements/${requirementId}/resolve`,
      body,
    ),

  sourceCandidates: (projectId: string, runId: string) =>
    request<{
      candidates: PartCandidate[];
      issues: Issue[];
      excluded_requirement_ids: string[];
    }>("POST", `/projects/${projectId}/runs/${runId}/source`, {}),
  getCandidates: (projectId: string, runId: string) =>
    request<{ candidates: PartCandidate[]; issues: Issue[] }>(
      "GET",
      `/projects/${projectId}/runs/${runId}/candidates`,
    ),

  createPlans: (projectId: string, runId: string, boardQuantity: number) =>
    request<{ plans: PurchasePlan[]; issues: Issue[] }>(
      "POST",
      `/projects/${projectId}/runs/${runId}/plans`,
      { board_quantity: boardQuantity },
    ),
  getPlans: (projectId: string, runId: string) =>
    request<{ plans: PurchasePlan[]; board_quantity: number; issues: Issue[] }>(
      "GET",
      `/projects/${projectId}/runs/${runId}/plans`,
    ),
  revalidatePlans: (projectId: string, runId: string, mode: string) =>
    request<{ plans: PurchasePlan[]; issues: Issue[] }>(
      "POST",
      `/projects/${projectId}/runs/${runId}/plans/${mode}/revalidate`,
      {},
    ),

  approvePlan: (
    projectId: string,
    runId: string,
    mode: string,
    body: {
      reviewed_high_tier_requirement_ids: string[];
      acknowledged_stale_offer_snapshot_ids: string[];
      note: string | null;
    },
  ) =>
    request<Approval>(
      "POST",
      `/projects/${projectId}/runs/${runId}/plans/${mode}/approve`,
      body,
    ),
  listApprovals: (projectId: string, runId: string) =>
    request<Approval[]>("GET", `/projects/${projectId}/runs/${runId}/approvals`),

  exportPlan: (projectId: string, runId: string, mode: string, supplier: string, format: string) =>
    request<ExportRecord>(
      "POST",
      `/projects/${projectId}/runs/${runId}/plans/${mode}/export`,
      { supplier, format },
    ),
  listExports: (projectId: string, runId: string) =>
    request<ExportRecord[]>("GET", `/projects/${projectId}/runs/${runId}/exports`),
};
