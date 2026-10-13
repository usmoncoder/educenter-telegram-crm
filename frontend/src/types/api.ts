// Types mirroring the backend schemas (app/schemas/api.py).

export type Role = "super_admin" | "admin" | "operator";

export interface Admin {
  id: number;
  username: string;
  full_name: string;
  role: Role;
  is_active: boolean;
  last_login_at: string | null;
  created_at: string;
}

export interface Me {
  admin: Admin;
  permissions: string[];
  csrf_token: string;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export type WelcomeStatus = "not_applicable" | "pending" | "sending" | "sent" | "failed" | "existing" | "unknown";

export interface Customer {
  id: number;
  telegram_user_id: number;
  username: string | null;
  first_name: string | null;
  last_name: string | null;
  display_name: string;
  first_seen_at: string;
  is_excluded: boolean;
  welcome_status: WelcomeStatus;
  welcome_sent_at: string | null;
  welcome_error: string | null;
}

export type SlaState = "ok" | "waiting" | "overdue";

export interface Conversation {
  id: number;
  customer: Customer;
  assigned_admin_id: number | null;
  assigned_admin_name: string | null;
  last_message_at: string | null;
  last_incoming_at: string | null;
  last_outgoing_at: string | null;
  last_human_reply_at: string | null;
  last_message_preview: string | null;
  last_message_direction: "in" | "out" | null;
  sla_state: SlaState;
  open_incident_id: number | null;
  waiting_since: string | null;
  deadline_at: string | null;
}

export interface Message {
  id: number;
  telegram_message_id: number;
  direction: "in" | "out";
  sender_type: "customer" | "operator" | "automation";
  source: "telegram" | "welcome" | "panel";
  counts_as_reply: boolean;
  is_forwarded: boolean;
  has_media: boolean;
  text_preview: string | null;
  sent_at: string;
  edited_at: string | null;
  deleted_at: string | null;
  sent_by_admin_id: number | null;
}

export type AlertStatus = "none" | "pending" | "sending" | "sent" | "failed" | "skipped";

export interface Incident {
  id: number;
  conversation_id: number;
  customer: Customer;
  status: "open" | "resolved" | "dismissed";
  started_at: string;
  last_customer_message_at: string;
  customer_message_count: number;
  deadline_at: string;
  breached_at: string | null;
  alert_status: AlertStatus;
  alerted_at: string | null;
  alert_error: string | null;
  resolved_at: string | null;
  resolution: "human_reply" | "panel_reply" | "dismissed" | null;
  response_seconds: number | null;
  first_message_preview: string | null;
  overdue: boolean;
}

export interface CustomerDetail {
  customer: Customer;
  conversation: Conversation | null;
  incidents: Incident[];
  message_count: number;
}

export type OutboxStatus = "queued" | "sending" | "sent" | "failed" | "unknown";

export interface Outgoing {
  id: number;
  conversation_id: number;
  text: string;
  status: OutboxStatus;
  attempts: number;
  error: string | null;
  created_at: string;
  sent_at: string | null;
  requested_by_admin_id: number | null;
}

export interface Entity {
  type: "bold" | "italic" | "underline" | "strike" | "code" | "pre" | "link" | "blockquote";
  offset: number;
  length: number;
  url?: string;
}

export interface Preview {
  text: string;
  entities: Entity[];
  length: number;
  limit: number;
  errors: string[];
}

export interface AutoReply {
  welcome_enabled: boolean;
  welcome_text: string;
  welcome_delay_seconds: number;
  welcome_only_new_chats: boolean;
  welcome_link_preview: boolean;
  welcome_excluded_user_ids: number[];
  stats: Record<WelcomeStatus, number>;
}

export interface RuntimeSettings {
  welcome_enabled: boolean;
  welcome_text: string;
  welcome_delay_seconds: number;
  welcome_only_new_chats: boolean;
  welcome_link_preview: boolean;
  welcome_excluded_user_ids: number[];
  monitor_excluded_user_ids: number[];
  ignore_contacts: boolean;
  sla_enabled: boolean;
  sla_timeout_minutes: number;
  count_forwarded_as_reply: boolean;
  alerts_enabled: boolean;
  alert_channel: "userbot" | "bot";
  alert_chat: string;
  alert_include_preview: boolean;
  store_message_text: boolean;
  store_operator_text: boolean;
  preview_length: number;
  retention_days: number;
  announcement_min_interval_seconds: number;
  announcement_max_attempts: number;
  misfire_grace_minutes: number;
  operators_see_unassigned: boolean;
}

export interface Group {
  id: number;
  telegram_id: number;
  title: string;
  username: string | null;
  kind: "group" | "supergroup" | "channel";
  source: "discovered" | "manual";
  participants_count: number | null;
  is_member: boolean;
  can_send: boolean;
  permission_note: string | null;
  is_enabled: boolean;
  last_synced_at: string | null;
}

export interface Command {
  id: number;
  command: "sync_groups" | "resolve_group" | "reconnect" | "test_alert";
  status: "pending" | "running" | "done" | "failed";
  result: Record<string, unknown> | null;
  error: string | null;
  created_at: string;
  finished_at: string | null;
}

export type CampaignStatus = "draft" | "scheduled" | "paused" | "completed" | "cancelled";
export type ScheduleType = "once" | "daily" | "weekly";
export type RunStatus = "pending" | "running" | "completed" | "partial" | "failed" | "missed" | "cancelled";
export type DeliveryStatus =
  | "pending"
  | "sending"
  | "sent"
  | "failed"
  | "skipped"
  | "dry_run"
  | "unknown"
  | "cancelled";

export interface CampaignTarget {
  group_id: number;
  group_title: string;
  group_can_send: boolean;
  group_enabled: boolean;
  custom_text: string | null;
}

export interface Campaign {
  id: number;
  title: string;
  default_text: string;
  status: CampaignStatus;
  schedule_type: ScheduleType;
  run_at: string | null;
  time_of_day: string | null;
  weekdays: number[];
  start_date: string | null;
  end_date: string | null;
  dry_run: boolean;
  next_run_at: string | null;
  last_run_at: string | null;
  created_at: string;
  updated_at: string;
  targets: CampaignTarget[];
  last_run_status: RunStatus | null;
}

export interface CampaignInput {
  title: string;
  default_text: string;
  schedule_type: ScheduleType;
  run_at: string | null;
  time_of_day: string | null;
  weekdays: number[];
  start_date: string | null;
  end_date: string | null;
  dry_run: boolean;
  targets: { group_id: number; custom_text: string | null }[];
}

export interface Run {
  id: number;
  scheduled_for: string;
  status: RunStatus;
  is_manual: boolean;
  started_at: string | null;
  finished_at: string | null;
  counts: Partial<Record<DeliveryStatus, number>>;
}

export interface Delivery {
  id: number;
  run_id: number;
  campaign_id: number;
  campaign_title: string;
  group_id: number;
  group_title: string;
  status: DeliveryStatus;
  attempts: number;
  error_code: string | null;
  error_message: string | null;
  sent_at: string | null;
  scheduled_for: string;
  created_at: string;
  text: string;
}

export interface SystemHistoryItem {
  id: number;
  customer_id: number;
  customer: string;
  telegram_user_id: number;
  status: string;
  at: string | null;
  error: string | null;
  attempts: number;
  admin?: string | null;
  incident_status?: string;
  conversation_id?: number;
}

export type WorkerStatusValue =
  | "starting"
  | "connected"
  | "disconnected"
  | "unauthorized"
  | "not_configured"
  | "standby"
  | "error"
  | "stopped"
  | "unknown"
  | "offline";

export interface WorkerStatus {
  status: WorkerStatusValue;
  status_detail: string | null;
  worker_alive: boolean;
  account_user_id: number | null;
  account_username: string | null;
  account_name: string | null;
  connected_at: string | null;
  last_heartbeat_at: string | null;
  last_error: string | null;
  last_error_at: string | null;
  telegram_configured: boolean | null;
}

export interface ConnectionEvent {
  id: number;
  event: string;
  detail: string | null;
  created_at: string;
}

export interface Dashboard {
  metrics: {
    total_customers: number;
    new_customers_today: number;
    unanswered: number;
    overdue: number;
    avg_response_seconds_30d: number | null;
    avg_response_seconds_today: number | null;
    breached_30d: number;
    resolved_alerts_30d: number;
    alerts_sent_today: number;
    alert_failures_30d: number;
    auto_responses_total: number;
    auto_responses_today: number;
    resolved_30d: number;
    within_sla_30d: number;
  };
  distribution_30d: { label: string; count: number }[];
  telegram: WorkerStatus;
  upcoming_announcements: { campaign_id: number; title: string; next_run_at: string; dry_run: boolean }[];
  recent_errors: { kind: string; title: string; message: string | null; at: string | null }[];
  latest_activity: Conversation[];
  waiting_incidents: Incident[];
}

export interface ReportDay {
  date: string;
  new_customers: number;
  incidents: number;
  breaches: number;
  avg_response_seconds: number | null;
  welcome_sent: number;
  announcements_sent: number;
  announcements_failed: number;
}

export interface Report {
  date_from: string;
  date_to: string;
  days: ReportDay[];
  totals: {
    incidents: number;
    breaches: number;
    answered: number;
    avg_response_seconds: number | null;
    median_response_seconds: number | null;
    max_response_seconds: number | null;
    new_customers: number;
    welcome_sent: number;
    announcements_sent: number;
    announcements_failed: number;
    runs: Record<string, number>;
  };
  distribution: { label: string; count: number }[];
}

export interface AuditEvent {
  id: number;
  actor_admin_id: number | null;
  actor_username: string | null;
  action: string;
  entity_type: string | null;
  entity_id: string | null;
  details: Record<string, unknown>;
  ip: string | null;
  created_at: string;
}

export interface Staff {
  id: number;
  username: string;
  full_name: string;
  role: Role;
}
