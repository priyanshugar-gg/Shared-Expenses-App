const API_URL = import.meta.env.VITE_API_URL;

function getTokens() {
  const raw = localStorage.getItem("tokens");
  return raw ? JSON.parse(raw) : null;
}
function setTokens(tokens: { access: string; refresh: string }) {
  localStorage.setItem("tokens", JSON.stringify(tokens));
}
export function clearTokens() {
  localStorage.removeItem("tokens");
}

async function refreshAccessToken(): Promise<string | null> {
  const tokens = getTokens();
  if (!tokens?.refresh) return null;
  const res = await fetch(`${API_URL}/auth/refresh/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh: tokens.refresh }),
  });
  if (!res.ok) return null;
  const data = await res.json();
  setTokens({ access: data.access, refresh: tokens.refresh });
  return data.access;
}

export async function apiRequest(path: string, options: RequestInit = {}, isFormData = false): Promise<any> {
  const tokens = getTokens();
  const headers: Record<string, string> = { ...(options.headers as any) };
  if (!isFormData) headers["Content-Type"] = "application/json";
  if (tokens?.access) headers["Authorization"] = `Bearer ${tokens.access}`;

  let res = await fetch(`${API_URL}${path}`, { ...options, headers });

  if (res.status === 401 && tokens?.refresh) {
    const newAccess = await refreshAccessToken();
    if (newAccess) {
      headers["Authorization"] = `Bearer ${newAccess}`;
      res = await fetch(`${API_URL}${path}`, { ...options, headers });
    }
  }

  if (!res.ok) {
    let body;
    try { body = await res.json(); } catch { body = { detail: res.statusText }; }
    throw new Error(JSON.stringify(body));
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  login: (username: string, password: string) =>
    apiRequest("/auth/login/", { method: "POST", body: JSON.stringify({ username, password }) })
      .then((data) => { setTokens(data); return data; }),
  register: (username: string, email: string, password: string) =>
    apiRequest("/auth/register/", { method: "POST", body: JSON.stringify({ username, email, password }) }),

  getGroups: () => apiRequest("/groups/"),
  getGroup: (id: number) => apiRequest(`/groups/${id}/`),
  createGroup: (name: string) => apiRequest("/groups/", { method: "POST", body: JSON.stringify({ name }) }),
  addMember: (groupId: number, user_id: number, joined_at: string) =>
    apiRequest(`/groups/${groupId}/members/`, { method: "POST", body: JSON.stringify({ user_id, joined_at }) }),
  updateMember: (groupId: number, membershipId: number, left_at: string) =>
    apiRequest(`/groups/${groupId}/members/${membershipId}/`, { method: "PATCH", body: JSON.stringify({ left_at }) }),
  getBalances: (groupId: number): Promise<import("../types").BalancesResponse> =>
    apiRequest(`/groups/${groupId}/balances/`),
  getBalanceTrace: (groupId: number, membershipId: number): Promise<import("../types").BalanceTrace> =>
    apiRequest(`/groups/${groupId}/balances/${membershipId}/trace/`),

  getExpenses: (groupId: number) => apiRequest(`/expenses/?group=${groupId}`),
  createExpense: (payload: any) => apiRequest("/expenses/", { method: "POST", body: JSON.stringify(payload) }),

  getSettlements: (groupId: number) => apiRequest(`/settlements/?group=${groupId}`),
  createSettlement: (payload: any) => apiRequest("/settlements/", { method: "POST", body: JSON.stringify(payload) }),

  uploadImport: (groupId: number, file: File) => {
    const form = new FormData();
    form.append("group", String(groupId));
    form.append("file", file);
    return apiRequest("/imports/", { method: "POST", body: form }, true);
  },
  getImportBatch: (id: number) => apiRequest(`/imports/${id}/`),
  updateImportRow: (batchId: number, rowId: number, payload: any) =>
    apiRequest(`/imports/${batchId}/rows/${rowId}/`, { method: "PATCH", body: JSON.stringify(payload) }),
  commitImport: (batchId: number) => apiRequest(`/imports/${batchId}/commit/`, { method: "POST" }),
  getImportReport: (batchId: number) => apiRequest(`/imports/${batchId}/report/`),
};