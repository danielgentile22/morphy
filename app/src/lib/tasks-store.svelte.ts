// Runes store for the Tasks workspace (UI overhaul P2 / #107, filtering #110).
// Loads the tenant's tasks + roster; filtering is client-side over the loaded
// list via the shared task-filter predicate (the Lead/tower pages fetch their
// linked tasks server-side via the same registry's query string).

import {
  createTask,
  deleteTask,
  fetchTasks,
  fetchUsers,
  updateTask,
  type Task,
  type TaskPatch,
  type TaskStatus,
  type TaskUser,
} from './tasks-api';
import { ApiError } from './leads-api';
import { auth } from './auth-store.svelte';
import { emptyTaskFilter, matchesTask, type TaskFilter } from './task-filter';

type Loadable = 'idle' | 'loading' | 'ready' | 'error';

function handle(e: unknown): string {
  if (e instanceof ApiError && e.status === 401) auth.signOut();
  return e instanceof Error ? e.message : String(e);
}

/** Today as ISO yyyy-mm-dd — the due-window reference for the filter. */
function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

class TasksStore {
  tasks = $state<Task[]>([]);
  status = $state<Loadable>('idle');
  error = $state<string | null>(null);
  saving = $state(false);

  users = $state<TaskUser[]>([]);

  filter = $state<TaskFilter>(emptyTaskFilter());
  today = todayIso();

  /** The loaded tasks narrowed by the active filter (client-side predicate). */
  visible = $derived(this.tasks.filter((t) => matchesTask(t, this.filter, this.today)));

  /** Display name for an assignee id (falls back to email / —). */
  userName(id: number | null): string {
    if (id == null) return 'Unassigned';
    const u = this.users.find((x) => x.id === id);
    return u ? u.name : `user ${id}`;
  }

  async load(): Promise<void> {
    this.status = 'loading';
    this.error = null;
    try {
      this.tasks = (await fetchTasks()).tasks;
      this.status = 'ready';
    } catch (e) {
      this.error = handle(e);
      this.status = 'error';
    }
  }

  async loadUsers(): Promise<void> {
    try {
      this.users = (await fetchUsers()).users;
    } catch (e) {
      handle(e); // still signs out on 401; roster is best-effort otherwise
    }
  }

  async create(body: TaskPatch & { title: string }): Promise<boolean> {
    if (!body.title.trim()) return false;
    this.saving = true;
    this.error = null;
    try {
      const t = await createTask({ ...body, title: body.title.trim() });
      this.tasks = [t, ...this.tasks];
      return true;
    } catch (e) {
      this.error = handle(e);
      return false;
    } finally {
      this.saving = false;
    }
  }

  async patch(id: number, patch: TaskPatch): Promise<boolean> {
    this.saving = true;
    this.error = null;
    try {
      const updated = await updateTask(id, patch);
      this.tasks = this.tasks.map((t) => (t.id === id ? updated : t));
      return true;
    } catch (e) {
      this.error = handle(e);
      return false;
    } finally {
      this.saving = false;
    }
  }

  setStatus(id: number, status: TaskStatus): Promise<boolean> {
    return this.patch(id, { status });
  }

  async remove(id: number): Promise<boolean> {
    this.saving = true;
    this.error = null;
    try {
      await deleteTask(id);
      this.tasks = this.tasks.filter((t) => t.id !== id);
      return true;
    } catch (e) {
      this.error = handle(e);
      return false;
    } finally {
      this.saving = false;
    }
  }

  setFilter(patch: Partial<TaskFilter>): void {
    this.filter = { ...this.filter, ...patch };
  }
  resetFilter(): void {
    this.filter = emptyTaskFilter();
  }
}

export const tasks = new TasksStore();
