// Thin client for the Task write-layer (backend/app/main.py /api/tasks).
// UI overhaul P2 / #107 — the thin tracer (title/description/status). Links,
// assignee, due/priority/labels, and filtering arrive in #110.

import { request } from './leads-api';
import type { components } from './api-types';

// Shapes derive from the generated OpenAPI types (api-types.ts, PRD #133;
// regenerate with `npm run generate:api`). Status/priority/source are
// narrowed from the schema's plain strings; `Required<…>` restores the
// presence of fields the schema marks optional-with-default but the server
// always serializes.
type Schemas = components['schemas'];

export type TaskStatus = 'open' | 'in_progress' | 'done';
export type TaskPriority = 'none' | 'low' | 'med' | 'high';

export type Task = Omit<Required<Schemas['TaskOut']>, 'status' | 'priority' | 'source'> & {
  status: TaskStatus;
  priority: TaskPriority;
  source: 'manual' | 'auto';
};

export type TasksResponse = Omit<Schemas['TasksResponse'], 'tasks'> & {
  tasks: Task[];
};

/** A teammate for the assignment UI (#110). `name` is the display name,
 *  falling back to the email. */
export type TaskUser = Schemas['UserOut'];

export type UsersResponse = Schemas['UsersResponse'];

/** The fields a task create/patch may set (omit to leave unchanged on PUT;
 *  send null on a nullable field to clear it). */
export type TaskPatch = Omit<Schemas['TaskUpdate'], 'status' | 'priority'> & {
  status?: TaskStatus | null;
  priority?: TaskPriority | null;
};

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

export function fetchUsers(): Promise<UsersResponse> {
  return request<UsersResponse>('/users');
}
