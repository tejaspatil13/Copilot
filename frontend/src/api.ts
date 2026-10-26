export type ContactStatus =
  | "verified" | "probable" | "needs_review" | "no_contact" | "lookup_failed" | "not_searched";

export type PhoneFilter = "" | "with" | "without";

export type JobState = "queued" | "running" | "completed" | "completed_partial" | "no_results" | "failed";

export interface SearchRequest {
  town: string;
  postcode: string;
  description_code: string;
  rv_from: number | null;
  rv_to: number | null;
}

export interface JobSummary {
  source_records: number;
  unique_premises: number;
  phones_found: number;
  verified: number;
  probable: number;
  needs_review: number;
  no_contact: number;
  lookup_failed: number;
}

export interface Job {
  id: string;
  state: JobState;
  stage: string;
  progress: number;
  message: string;
  request: SearchRequest;
  summary: JobSummary;
  created_at: string;
  finished_at: string | null;
  duration_seconds: number | null;
  download_ready: boolean;
  errors: string[];
  employee: string;
  label: string;
}

export interface ResultRecord {
  uarn: string;
  address: string;
  postcode: string;
  description: string;
  rv: number;
  business_name: string;
  phone: string;
  contact_status: ContactStatus;
  other_numbers: string[];
  business_address: string;
  match_note: string;
  source_url: string;
  google_maps_url: string;
}

export interface SheetRecord extends ResultRecord {
  search: string;
  added: string;
}

export interface Meta {
  voa_dataset: Record<string, string> | null;
  contact_providers: string[];
  max_results_per_search: number;
  export_retention_hours: number;
  description_codes: { code: string; label: string }[];
}

export class ApiError extends Error {
  constructor(public messages: string[], public status: number) {
    super(messages.join("\n"));
  }
}

async function send(path: string, init?: RequestInit): Promise<Response> {
  let res: Response;
  try {
    res = await fetch(path, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError(["Can't reach the server. Check your connection and try again."], 0);
  }
  if (!res.ok) {
    let messages = [`Request failed (${res.status}).`];
    try {
      const body = await res.json();
      if (Array.isArray(body.detail)) messages = body.detail;
      else if (typeof body.detail === "string") messages = [body.detail];
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(messages, res.status);
  }
  return res;
}

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  return (await send(path, init)).json() as Promise<T>;
}

const q_ = (params: Record<string, string>) => new URLSearchParams(params).toString();

const q = (params: Record<string, string | number | undefined>) =>
  new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== "") as [string, string][],
  ).toString();

/** Save a downloaded file under the name the user chose. */
function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export const api = {
  meta: () => json<Meta>("/api/meta"),
  suggestTowns: (q: string) => json<{ value: string; count: number }[]>(`/api/suggest/towns?${q_({ q })}`),
  suggestPostcodes: (town: string, q: string) =>
    json<{ value: string; count: number }[]>(`/api/suggest/postcodes?${q_({ town, q })}`),
  jobs: (employee: string) => json<Job[]>(`/api/jobs?${q({ employee })}`),
  job: (id: string) => json<Job>(`/api/jobs/${id}`),
  create: (req: SearchRequest, employee: string) =>
    json<Job>(`/api/jobs?${q({ employee })}`, { method: "POST", body: JSON.stringify(req) }),
  retry: (id: string) => json<Job>(`/api/jobs/${id}/retry`, { method: "POST" }),
  deleteJob: (id: string) => send(`/api/jobs/${id}`, { method: "DELETE" }),
  records: (id: string, phone: PhoneFilter, offset: number, limit: number) =>
    json<{ total: number; items: ResultRecord[] }>(
      `/api/jobs/${id}/records?${q({ offset, limit, has_phone: phone ? String(phone === "with") : undefined })}`,
    ),
  downloadJob: async (id: string, filename: string) => {
    const res = await send(`/api/jobs/${id}/download?${q({ filename })}`);
    saveBlob(await res.blob(), `${filename}.xlsx`);
  },

  sheet: (employee: string) => json<{ total: number; items: SheetRecord[] }>(`/api/sheet?${q({ employee })}`),
  sheetAdd: (employee: string, jobId: string) =>
    json<{ added: number; already_in_sheet: number; total: number }>("/api/sheet/add", {
      method: "POST",
      body: JSON.stringify({ employee, job_id: jobId }),
    }),
  sheetRemove: (employee: string, uarns: string[]) =>
    json<{ removed: number; total: number }>("/api/sheet/remove", {
      method: "POST",
      body: JSON.stringify({ employee, uarns }),
    }),
  sheetClear: (employee: string) => json<{ removed: number }>(`/api/sheet?${q({ employee })}`, { method: "DELETE" }),
  sheetDownload: async (employee: string, filename: string, uarns: string[] | null) => {
    const res = await send("/api/sheet/download", {
      method: "POST",
      body: JSON.stringify({ employee, filename, uarns }),
    });
    saveBlob(await res.blob(), `${filename}.xlsx`);
  },
};
