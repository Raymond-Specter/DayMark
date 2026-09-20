export interface Goal {
  id: string;
  name: string;
  description: string;
  start_date: string | null;
  target_date: string | null;
  status: string;
  priority: number;
  color: string;
}
export interface Project {
  id: string;
  name: string;
  goal_id: string | null;
  start_date: string | null;
  end_date: string | null;
  status: string;
  description: string;
}
export interface Milestone {
  id: string;
  name: string;
  project_id: string;
  start_date: string | null;
  deadline: string | null;
  status: string;
  description: string;
}
export interface Task {
  id: string;
  title: string;
  description: string;
  project_id: string | null;
  milestone_id: string | null;
  date: string | null;
  start_time: string | null;
  end_time: string | null;
  deadline: string | null;
  estimated_duration: number;
  priority: number;
  status: string;
  completed_at: string | null;
  created_at: string;
  source: string;
  routine_id: string | null;
  depends_on_task_id: string | null;
  depends_on_routine_id: string | null;
  offset_days: number;
  reminder: number | null;
  version: number;
  blocked: boolean;
  blocked_reason: string | null;
  dependency_title: string | null;
}
export interface Routine {
  id: string;
  name: string;
  description: string;
  project_id: string | null;
  milestone_id: string | null;
  frequency: string;
  interval: number;
  interval_unit: string;
  weekdays: number[];
  start_date: string;
  end_date: string | null;
  preferred_time: string | null;
  estimated_duration: number;
  priority: number;
  reminder: number | null;
  active: boolean;
  depends_on_routine_id: string | null;
  offset_days: number;
  version: number;
}
export interface AppNotification {
  id: string;
  task_id: string;
  title: string;
  due_at: string;
  read_at: string | null;
}
export interface Settings {
  timezone: string;
  day_start: string;
}
export interface Bootstrap {
  settings: Settings;
  today: string;
  goals: Goal[];
  projects: Project[];
  milestones: Milestone[];
  tasks: Task[];
  routines: Routine[];
  notifications: AppNotification[];
}
export interface TodayData {
  date: string;
  tasks: Task[];
  unfinished_yesterday: Task[];
  overdue: Task[];
  completed_count: number;
  remaining_count: number;
  upcoming_deadlines: Task[];
}
export interface Statistics {
  start: string;
  end: string;
  completed_today: number;
  completed_week: number;
  completion_rate: number;
  planned_minutes: number;
  actual_minutes: number;
  total_tasks: number;
  completed_tasks: number;
  project_distribution: {
    project_id: string | null;
    name: string;
    color: string;
    planned_minutes: number;
    actual_minutes: number;
  }[];
  daily: {
    date: string;
    planned_minutes: number;
    actual_minutes: number;
    completed: number;
    total: number;
  }[];
  upcoming_deadlines: Task[];
}
export interface MilestoneProgress {
  id: string;
  name: string;
  status: string;
  total: number;
  completed: number;
  percent: number;
  deadline: string | null;
}
export interface ProjectProgress {
  id: string;
  name: string;
  status: string;
  total: number;
  completed: number;
  percent: number;
  current_milestone: string | { id?: string; name: string } | null;
  milestones: MilestoneProgress[];
}
export interface GoalProgress {
  id: string;
  name: string;
  color: string;
  status: string;
  total: number;
  completed: number;
  percent: number;
  projects: ProjectProgress[];
}
export interface Progress {
  goals: GoalProgress[];
  standalone_projects: ProjectProgress[];
  unassigned_tasks: number;
}
export interface Review {
  date: string;
  actual_minutes: number;
  energy_level: number;
  notes: string;
  project_minutes: Record<string, number>;
  completed_tasks: { id: string; title: string }[];
  unfinished_tasks: { id: string; title: string }[];
  saved: boolean;
}
export interface CalendarEventRecord {
  id: string;
  title: string;
  start: string;
  end: string;
  all_day: boolean;
  color: string;
  description: string;
}
export type EntityKind =
  "task" | "goal" | "project" | "milestone" | "routine" | "event";
export type Entity =
  Task | Goal | Project | Milestone | Routine | CalendarEventRecord;
export interface EditorState {
  kind: EntityKind;
  item?: Entity;
  defaults?: Record<string, unknown>;
}
