import { API_URL } from "../config";
import { authHeaders } from "./auth";

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(text || res.statusText);
  }
  if (res.status === 204) return undefined as unknown as T;
  return res.json();
}

export interface MicroUnitChannel {
  id: number;
  micro_unit_id: number;
  instagram_id: string;
  username: string;
  creator_name: string;
}

export interface MicroUnit {
  id: number;
  unit_number: number;
  name: string;
  poc_user_id: number | null;
  poc_name: string | null;
  poc?: { id: number; full_name: string; email: string } | null;
  status: string;
  channels: MicroUnitChannel[];
}

export interface MonthEntry {
  month: number;
  snapshot1_run_id: number;
  snapshot2_run_id: number;
}

export interface CalculateBody {
  year: number;
  months: MonthEntry[];
}

export interface ChannelMonthData {
  views: number;
  post_count: number;
}

export interface DashboardChannel {
  instagram_id: string;
  username: string;
  creator_name: string;
  months: Record<string, ChannelMonthData>;
}

export interface DashboardData {
  unit: { id: number; name: string; poc: string };
  available_months: string[];
  channels: DashboardChannel[];
}

export interface ScrapeRunOption {
  id: number;
  started_at: string;
  status: string;
}

export async function fetchMicroUnits(): Promise<MicroUnit[]> {
  const res = await fetch(`${API_URL}/api/micro-units`, {
    headers: authHeaders(),
  });
  return handleResponse<MicroUnit[]>(res);
}

export async function createMicroUnit(body: { unit_number: number; name: string }): Promise<MicroUnit> {
  const res = await fetch(`${API_URL}/api/micro-units`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(body),
  });
  return handleResponse<MicroUnit>(res);
}

export async function updateMicroUnit(id: number, body: Partial<MicroUnit>): Promise<MicroUnit> {
  const res = await fetch(`${API_URL}/api/micro-units/${id}`, {
    method: "PUT",
    headers: authHeaders(),
    body: JSON.stringify(body),
  });
  return handleResponse<MicroUnit>(res);
}

export async function deleteMicroUnit(id: number): Promise<void> {
  const res = await fetch(`${API_URL}/api/micro-units/${id}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  return handleResponse<void>(res);
}

export async function addChannel(unitId: number, body: { username: string; instagram_id?: string; creator_name?: string }): Promise<MicroUnitChannel> {
  const res = await fetch(`${API_URL}/api/micro-units/${unitId}/channels`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(body),
  });
  return handleResponse<MicroUnitChannel>(res);
}

export async function removeChannel(unitId: number, channelId: number): Promise<void> {
  const res = await fetch(`${API_URL}/api/micro-units/${unitId}/channels/${channelId}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  return handleResponse<void>(res);
}

export async function fetchAvailableProfiles(): Promise<{ id: string; username: string; creator_name: string }[]> {
  const res = await fetch(`${API_URL}/api/micro-units/profiles`, {
    headers: authHeaders(),
  });
  return handleResponse<{ id: string; username: string; creator_name: string }[]>(res);
}

export async function calculateMonthlyMetrics(body: CalculateBody): Promise<any> {
  const res = await fetch(`${API_URL}/api/micro-units/calculate`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(body),
  });
  return handleResponse<any>(res);
}

export async function fetchDashboard(unitId: number, year: number): Promise<DashboardData> {
  const res = await fetch(`${API_URL}/api/micro-units/${unitId}/dashboard?year=${year}`, {
    headers: authHeaders(),
  });
  return handleResponse<DashboardData>(res);
}

export async function fetchMyUnit(): Promise<{ id: number; name: string }> {
  const res = await fetch(`${API_URL}/api/micro-units/my-unit`, {
    headers: authHeaders(),
  });
  return handleResponse<{ id: number; name: string }>(res);
}

export async function fetchScrapeRuns(): Promise<ScrapeRunOption[]> {
  const res = await fetch(`${API_URL}/api/micro-units/scrape-runs`, {
    headers: authHeaders(),
  });
  return handleResponse<ScrapeRunOption[]>(res);
}
