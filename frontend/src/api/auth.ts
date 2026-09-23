import { API_URL } from "../config"

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: string;
  status?: string;
  created_at?: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface CreateUserBody {
  email: string;
  password?: string;
  full_name: string;
  role: string;
}

export interface RegisterPocBody {
  full_name: string;
  email: string;
  password: string;
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    try {
      const json = JSON.parse(text);
      if (json.detail) throw new Error(json.detail);
    } catch (e: any) {
      if (e.message && e.message !== text) throw e;
    }
    throw new Error(text || res.statusText)
  }
  if (res.status === 204) return undefined as unknown as T
  return res.json()
}

export function getToken(): string | null {
  return localStorage.getItem('token');
}

export function authHeaders(): Record<string, string> {
  const token = getToken();
  return {
    'Authorization': token ? `Bearer ${token}` : '',
    'Content-Type': 'application/json'
  };
}

export function logout(): void {
  localStorage.removeItem('token');
}

export async function login(email: string, password: string): Promise<LoginResponse> {
  const res = await fetch(`${API_URL}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password })
  });
  const data = await handleResponse<LoginResponse>(res);
  localStorage.setItem('token', data.access_token);
  return data;
}

export async function registerPoc(body: RegisterPocBody): Promise<{ status: string; message: string; user: User }> {
  const res = await fetch(`${API_URL}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  return handleResponse<{ status: string; message: string; user: User }>(res);
}

export async function getPendingRegistrations(): Promise<User[]> {
  const res = await fetch(`${API_URL}/api/auth/pending-registrations`, {
    headers: authHeaders()
  });
  return handleResponse<User[]>(res);
}

export async function approveUser(userId: number, microUnitId?: number): Promise<{ status: string; message: string; user: User; assigned_unit?: string }> {
  const res = await fetch(`${API_URL}/api/auth/approve-user/${userId}`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ micro_unit_id: microUnitId || null })
  });
  return handleResponse<{ status: string; message: string; user: User; assigned_unit?: string }>(res);
}

export async function rejectUser(userId: number): Promise<{ status: string; message: string }> {
  const res = await fetch(`${API_URL}/api/auth/reject-user/${userId}`, {
    method: 'POST',
    headers: authHeaders()
  });
  return handleResponse<{ status: string; message: string }>(res);
}

export async function getMe(): Promise<User> {
  const res = await fetch(`${API_URL}/api/auth/me`, {
    headers: authHeaders()
  });
  return handleResponse<User>(res);
}

export async function createUser(body: CreateUserBody): Promise<User> {
  const res = await fetch(`${API_URL}/api/auth/users`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(body)
  });
  return handleResponse<User>(res);
}

export async function getUsers(): Promise<User[]> {
  const res = await fetch(`${API_URL}/api/auth/users`, {
    headers: authHeaders()
  });
  return handleResponse<User[]>(res);
}

export async function resetPassword(email: string, new_password: string): Promise<{ status: string; email: string }> {
  const res = await fetch(`${API_URL}/api/auth/reset-password`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, new_password })
  });
  return handleResponse<{ status: string; email: string }>(res);
}
