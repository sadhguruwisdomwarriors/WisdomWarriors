import { API_URL } from "../config"

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: string;
  created_at: string;
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

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
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
