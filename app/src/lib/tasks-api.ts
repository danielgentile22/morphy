// Thin client for the Task write-layer (backend/app/main.py /api/tasks).
// UI overhaul P2 / #107 — the thin tracer (title/description/status). Links,
// assignee, due/priority/labels, and filtering arrive in #110.

import { request } from './leads-api';

export type TaskStatus = 'open' | 'in_progress' | 'done';
export type TaskPriority = 'none' | 'low' | 'med' | 'high';

export interface Task {
  id: number;
  title: string;
  description: string;
  status: TaskStatus;
  priority: TaskPriority;
  due_date: string | null;
  assignee_user_id: number | null;
  lead_cluster_id: string | null;
  tower_asr: string | null;
  labels: string[];
  source: 'manual' | 'auto';
  created_by_user_id: number | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface TasksResponse {
  count: number;
  tasks: Task[];
}

/** A teammate for the assignment UI (#110). */
export interface TaskUser {
  id: number;
  email: string;
  display_name: string;
  name: string;
}

/** The fields a task create/patch may set (omit to leave unchanged on PUT;
 *  send null on a nullable field to clear it). */
export interface TaskPatch {
  title?: string;
  description?: string;
  status?: TaskStatus;
  priority?: TaskPriority;
  due_date?: string | null;
  assignee_user_id?: number | null;
  lead_cluster_id?: string | null;
  tower_asr?: string | null;
  labels?: string[];
}

/** Fetch tasks, optionally narrowed by a pre-built query string (#110). */
export function fetchTasks(queryString = ''): Promise<TasksResponse> {
  return request<TasksResponse>(`/tasks${queryString ? `?${queryString}` : ''}`);
}

export function createTask(body: TaskPatch & { title: string }): Promise<Task> {
  return request<Task>('/tasks', { method: 'POST', body: JSON.stringify(body) });
}

export function updateTask(id: number, patch: TaskPatch): Promise<Task> {
  return request<Task>(`/tasks/${id}`, { method: 'PUT', body: JSON.stringify(patch) });
}

export function deleteTask(id: number): Promise<void> {
  return request<void>(`/tasks/${id}`, { method: 'DELETE' });
}

export function fetchUsers(): Promise<{ count: number; users: TaskUser[] }> {
  return request<{ count: number; users: TaskUser[] }>('/users');
}
