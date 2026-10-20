export type Tier = "alert" | "watch" | "high" | null;

export interface Clock { minute: number; now: string; speed: number; paused: boolean; start: string; end: string }

export interface Ack { id: string; pid: string; kind: string; by: string; minute: number; until: number; note: string; t?: string; until_t?: string }
export interface EventA {
  glucose: number; trend30: number | null; peak: number; peak_minute: number; tier: Tier;
  low: "now" | "forecast" | null; cross_minute?: number; low_minute?: number; low_value?: number; low_p?: number;
  ack?: Ack | null; low_ack?: Ack | null; artefact?: boolean; reason?: string; low_reason?: string; calibrating?: number;
}
export interface EventB {
  risk: number | null; flag: boolean; post_event: boolean; day: number; flag_since?: number | null;
  event_minute?: number; event?: string; ack?: Ack | null; reason?: string; paused?: boolean;
}
export interface WardRow {
  id: string; name: string; age: number; sex: string; problems: string[]; hba1c: number;
  glucose: number | null; trend30: number | null; sparkline: (number | null)[];
  event_a: EventA | null; event_b: EventB; last_sync: string | null; priority: number; hero: boolean; split: string;
  group: Group | null; seen: boolean; sharing_paused: string[]; calibrating: number | null; twin_fit?: string;
}
export type Group = "low" | "high" | "heart" | "watch";
export interface Ward { clock: Clock; patients: WardRow[]; alert_level: number; cardio_threshold: number }

export interface Coding { system: string; code: string; display: string }
export interface Obs { code: Coding; value: number | null; unit: string | null; text: string | null;
  effectiveDateTime: string; previous: number | null; previousDate: string | null }
export interface PatientDetail {
  patient: { id: string; name: string; gender: string; birthDate: string; age: number; city: string; occupation: string; nightShift: boolean };
  conditions: { code: Coding; onsetDateTime: string | null }[];
  medications: { medication: Coding; dosage: string; effectiveStart: string; drugClass: string }[];
  labs: Obs[]; vitals: Obs[];
  genetics: { gene: string; rsid: string; genotype: string; riskAlleles: number }[];
  familyHistory: string[]; socialHistory: string[]; consent: string;
  twin: { insulin_sensitivity_pct_typical: number; glucose_effectiveness: number; basal_glucose: number;
    absorption_half_time_min: number; secretion_pct_typical: number; calibration_rmse_prior: number; calibration_rmse_fit: number };
  device: string; context: string[]; split: string; abha: string; records_withheld: boolean; calibrating: number | null;
}
export interface Agp {
  days: number; coverage: number;
  profile: { minute: number; p5: number; p25: number; p50: number; p75: number; p95: number }[];
  metrics: { mean: number; gmi: number; cv: number; tir: number; tar: number; tar250: number; tbr: number; tbr54: number };
}

export interface TPoint { t: string; v: number | null }
export interface Timeline {
  start: string; now: string; cgm: TPoint[]; hr: TPoint[]; steps: TPoint[];
  meals: { t: string; carbs: number; description: string; kind: string }[];
  doses: { t: string; drug: string; dose: string; taken: boolean }[];
  sleep: { start: string; end: string; stage: string }[];
}
export interface Driver { category: string; mgdl: number; twin: number; learned: number; text: string }
export interface AlertCard { kind: string; tier: string; title: string; detail: string; reason: string; ack?: Ack | null }
export interface MealEntryRec { id: string; pid: string; minute: number; carbs: number; kind: string; label: string; by: string;
  entered_minute: number; type: "planned" | "logged"; t: string; source?: string }
export interface ActionRec { id: string; pid: string; kind: "call" | "review" | "check"; by: string; minute: number; note: string; outcome: string }
export interface Episode { kind: "spike" | "low"; start: string; end: string; said: string; result: "happened" | "did not happen" | "pending";
  what_happened: string; done: string[]; steps_after: number; lead_min: number | null }
export interface History { days: number; episodes: Episode[];
  summary: { alerts: number; decided: number; happened: number; rate: number | null; median_lead: number | null; missed: number; lows: number; lows_happened: number } }
export interface PlanCheck { days: number; due: string; complete: boolean; before: { tir: number; mean: number } | null;
  after: { tir: number; mean: number } | null; adherence: string | null; adherence_how: string; verdict?: string }
export interface PlanRec { id: string; pid: string; label: string; request: Partial<WhatIfReq>; by: string; minute: number; t: string;
  predicted: { tir_pct?: number; mean?: number }; seeded: boolean; check: PlanCheck }
export interface ConsentRow { source: "cgm" | "wearable" | "abdm"; name: string; what: string; granted: boolean; since: string; by: string;
  purpose: string; valid_until: string }
export interface HandoverRow { t: string; pid: string; name: string; who: string; what: string; note: string }
export interface HandoverItem { pid: string; name: string; group: Group; glucose: number | null; reason: string }
export interface Handover { from: string; to: string; hours: number; done: HandoverRow[]; open: HandoverItem[]; seen_still_active: HandoverItem[] }
export interface RefCheck { available: boolean; reason?: string; window_min: number; origin: string; times: string[];
  reference: { baseline: number[]; scenario: number[]; delta: { peak: number; tar_min: number; mean: number; tir_pct: number } };
  twin: { peak: number; tar_min: number }; agree: boolean; assumed_meal: { time: string; carbs: number } | null;
  actual_meal: { time: string; carbs: number } | null; note: string }
export interface Sharpen { items: { kind: string; action: string; gain: number; text: string; detail: string }[];
  range?: { lo: number; hi: number; time: string } }
export type InsideSeries = Record<"G" | "stomach_g" | "gut_g" | "into_blood" | "insulin" | "action" | "activity" | "out_of_blood", number[]>;
export interface Inside { available: boolean; times: string[]; usual: InsideSeries; change: InsideSeries; meal_step: number | null }
export interface Backtest { available: boolean; reason?: string; fit_on: [string, string]; tested_on: [string, string]; n: number;
  rmse_old: number; rmse_new: number; helps: boolean; text: string }
export interface TwinHealth { status: "good" | "drifting" | "too early"; text: string; rmse_then?: number; rmse_now?: number; bias_now?: number;
  weeks?: { from: string; to: string; rmse: number; bias: number }[];
  refit: { t: string; by: string; rmse_before: number; rmse_after: number; id: string; backtest: Partial<Backtest> | null } | null }
export interface Parsed { request: Partial<WhatIfReq>; understood: string[]; parser: string; unclear?: string }
export interface WardWhatIf { include_watch: boolean; hours_above_total: number;
  levers: { label: string; hours_saved: number; mean_peak_drop: number }[]; own_best: { hours_saved: number; mean_peak_drop: number };
  patients: { pid: string; name: string; group: string; peak: number; hours_above: number; best: string; best_hours_saved: number; best_peak_drop: number;
    by_lever: Record<string, { peak_after: number; hours_after: number }> }[] }
export interface FestivalRow { pid: string; name: string; usual_peak: number; festival_peak: number; extra_hours_above: number;
  saved_hours: Record<string, number>; best: string; best_saved_hours: number; festival_local: string; dish: string; festival?: string; date?: string }
export interface Festival { key: string; name: string; date: string; about: string; patients: number; total_extra_hours: number;
  total_saved_hours: number; tips: Record<string, string>; tip_keys: string[]; most_affected: FestivalRow[] }
export interface ActivityRec { id: string; pid: string; kind: "walk"; start: number; minutes: number; by: string; source: string;
  start_t: string; done: boolean }
export interface MessageRec { id: string; pid: string; from: "patient" | "care team"; key: string; text: string; t: string; by: string;
  params: { peak?: number; after?: number; lever?: string; festival?: string; local_name?: string; dish?: string; date?: string;
    extra_min?: number; tip?: string; saved_min?: number } }
export interface WalkResult { available: boolean; pending?: boolean; start?: string; minutes?: number; peak_with?: number; peak_without?: number;
  minutes_above_with?: number; minutes_above_without?: number }
export interface Digest { date: string; patients: number; alerts: number; lows: number; alerts_happened: number; alerts_total: number;
  alerts_per_patient: number; tir: number; heart_flags: { pid: string; name: string }[];
  most_alerts: { pid: string; name: string; alerts: number; lows: number }[]; actions: { seen: number; actions: number; meals: number } }
export interface AuditRow { action: string; wall_time: string; pid: string; by?: string; kind?: string; minute?: number;
  label?: string; carbs?: number; note?: string; until?: number; removed_by?: string }
export interface Lever { label: string; request: Partial<WhatIfReq>; peak: number; tar_min: number; auc_above_180: number; mean: number;
  tir_pct: number; combined: boolean }
export interface Forecast {
  available: boolean; reason?: string; paused?: boolean; origin: string;
  points: { t: string; mid: number; lo: number; hi: number; lo_alert: number; twin: number }[];
  horizons: { h: number; mid: number; lo: number; hi: number; lo_alert: number }[];
  status: EventA; alert_level: number; interval: number;
  explanation?: { drivers: Driver[]; sentence: string; unit: string; twin_peak: number; twin_baseline_peak: number };
  alerts: AlertCard[];
  entries?: MealEntryRec[];
}
export interface LogEntry { t: string; glucose: number; tier: Tier; low: string | null; peak: number; peak_time: string;
  low_value: number | null; cross_time: string | null }

export interface WhatIfReq { walk_minutes: number; swap: string; shift_hours: number; missed_dose: boolean;
  sleep_hours: number | null; night_shift: boolean; scope: "next" | "all"; horizon_h: Horizon;
  insulin_bolus_units: number; insulin_basal_units: number; metformin_shift_hours: number }
export type Horizon = 6 | 24 | 168;
export interface WhatIfSummary { peak: number; peak_time: string; tar_min: number; tbr_min: number; mean: number; tir_pct: number; auc_above_180: number }
export interface WhatIf {
  available: boolean; origin: string; times: string[]; baseline: number[]; scenario: number[];
  baseline_summary: WhatIfSummary; scenario_summary: WhatIfSummary;
  delta: { peak: number; tar_min: number; mean: number; auc_above_180: number; tir_pct: number };
  target_meal: { time: string; carbs: number; new_time: string } | null; note: string; solver: string;
  horizon_h: number; scope: string; meals_changed: number;
  days: { day: number; tir_change: number; mean_change: number; lowest: number }[]; insulin_steps: number[];
}

export interface CardioView {
  pid: string; end_day: number; dates: string[];
  metrics: { metric: string; values: (number | null)[]; adverse_z: (number | null)[]; baseline: number | null }[];
  trajectory: { day: number; date: string; risk: number | null; flag: boolean; post_event: boolean }[];
  threshold: number; risk: number | null; flag: boolean;
  factors: { factor: string; shap: number; text: string }[];
  event: { minute: number; time: string; day: number; description: string } | null;
  summary: EventB;
}

export interface Note {
  patient: PatientDetail["patient"]; generated: string; problems: string[]; medications: string[];
  S: string[]; O: string[]; A: string[]; P: string[]; disclaimer: string;
}

// Who is signed in. The demo has no passwords; the role and name travel in two headers and the API checks
// what each role may do. A deployment would take both from the clinic's single sign on.
export type Role = "doctor" | "nurse" | "patient";
export interface Session { role: Role; name: string; pid?: string }
export const session: { current: Session | null } = { current: null };
export const ROLE_NAMES: Record<Role, string> = { doctor: "Doctor", nurse: "Nurse or health educator", patient: "Patient" };

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function j<T>(url: string, init?: RequestInit, as?: Session): Promise<T> {
  const who = as ?? session.current;
  const headers: Record<string, string> = { ...(init?.headers as Record<string, string> ?? {}) };
  if (who) { headers["X-Prativimb-Role"] = who.role; headers["X-Prativimb-User"] = encodeURIComponent(who.name); }
  const r = await fetch(url, { ...init, headers });
  if (!r.ok) {
    let msg = `${r.status} ${url}`;
    try { const b = await r.json(); if (b.detail) msg = typeof b.detail === "string" ? b.detail : JSON.stringify(b.detail); } catch { /* not json */ }
    throw new ApiError(r.status, msg);
  }
  return r.json() as Promise<T>;
}
const post = (body: unknown) => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const api = {
  clock: () => j<Clock>("/api/clock"),
  setClock: (body: Partial<{ minute: number; at: string; speed: number; paused: boolean }>) => j<Clock>("/api/clock", post(body)),
  ward: () => j<Ward>("/api/ward"),
  patient: (id: string) => j<PatientDetail>(`/api/patients/${id}`),
  timeline: (id: string, hours = 12) => j<Timeline>(`/api/patients/${id}/timeline?hours=${hours}`),
  forecast: (id: string) => j<Forecast>(`/api/patients/${id}/forecast`),
  agp: (id: string) => j<Agp>(`/api/patients/${id}/agp?days=14`),
  alertLog: (id: string) => j<LogEntry[]>(`/api/patients/${id}/alert-log?hours=6`),
  whatif: (id: string, req: WhatIfReq) => j<WhatIf>(`/api/patients/${id}/whatif`, post(req)),
  cardio: (id: string, endDay?: number) => j<CardioView>(`/api/patients/${id}/cardio${endDay !== undefined ? `?end_day=${endDay}` : ""}`),
  note: (id: string) => j<Note>(`/api/patients/${id}/note`),
  levers: (id: string, horizon = 6, scope = "next") => j<{ available: boolean; levers: Lever[]; target_meal: WhatIf["target_meal"] }>(
    `/api/patients/${id}/levers?horizon_h=${horizon}&scope=${scope}`),
  mealTypes: () => j<{ kind: string; label: string; speed: number }[]>("/api/meal-types"),
  addMeal: (id: string, body: { minutes_from_now: number; carbs: number; kind: string; label: string }, as?: Session) =>
    j<MealEntryRec>(`/api/patients/${id}/meals`, post(body), as),
  removeMeal: (id: string, mealId: string, as?: Session) =>
    j<{ removed: string }>(`/api/patients/${id}/meals/${mealId}`, { method: "DELETE" }, as),
  ack: (id: string, body: { kind: string; snooze_minutes: number; note?: string }) => j<Ack>(`/api/patients/${id}/ack`, post(body)),
  unack: (id: string, ackId: string) => j<{ removed: string }>(`/api/patients/${id}/ack/${ackId}`, { method: "DELETE" }),
  action: (id: string, body: { kind: "call" | "review" | "check"; note?: string; outcome?: string; alert?: string }) =>
    j<ActionRec>(`/api/patients/${id}/actions`, post(body)),
  undoAction: (id: string, actionId: string) => j<{ removed: string }>(`/api/patients/${id}/actions/${actionId}`, { method: "DELETE" }),
  history: (id: string, days = 7) => j<History>(`/api/patients/${id}/history?days=${days}`),
  plans: (id: string) => j<PlanRec[]>(`/api/patients/${id}/plans`),
  addPlan: (id: string, body: { label: string; request: Partial<WhatIfReq>; predicted: { tir_pct?: number; mean?: number } }) =>
    j<PlanRec>(`/api/patients/${id}/plans`, post(body)),
  removePlan: (id: string, planId: string) => j<{ removed: string }>(`/api/patients/${id}/plans/${planId}`, { method: "DELETE" }),
  consent: (id: string) => j<ConsentRow[]>(`/api/patients/${id}/consent`),
  setConsent: (id: string, body: { source: string; granted: boolean }, as?: Session) =>
    j<unknown>(`/api/patients/${id}/consent`, post(body), as),
  reference: (id: string, req: WhatIfReq) => j<RefCheck>(`/api/patients/${id}/reference`, post(req)),
  sharpen: (id: string) => j<Sharpen>(`/api/patients/${id}/sharpen`),
  inside: (id: string, req: WhatIfReq) => j<Inside>(`/api/patients/${id}/inside`, post(req)),
  twinHealth: (id: string) => j<TwinHealth>(`/api/patients/${id}/twin-health`),
  refit: (id: string) => j<{ id: string; rmse_before: number; rmse_after: number }>(`/api/patients/${id}/refit`, { method: "POST" }),
  undoRefit: (id: string, rid: string) => j<unknown>(`/api/patients/${id}/refit/${rid}`, { method: "DELETE" }),
  ask: (text: string) => j<Parsed>("/api/ask", post({ text })),
  wardWhatIf: (includeWatch = false) => j<WardWhatIf>(`/api/ward/whatif?include_watch=${includeWatch}`),
  wardNudge: (lever: string, includeWatch = false) =>
    j<{ sent: { pid: string; name: string; change: string; id: string }[]; skipped: string[] }>("/api/ward/nudge", post({ lever, include_watch: includeWatch })),
  festivals: () => j<{ festivals: Festival[] }>("/api/festivals"),
  patientFestivals: (id: string) => j<FestivalRow[]>(`/api/patients/${id}/festivals`),
  festivalNudge: (festival: string, pids: string[] = []) =>
    j<{ sent: { pid: string; name: string; id: string }[]; skipped: string[] }>("/api/festivals/nudge", post({ festival, pids })),
  refitBacktest: (id: string) => j<Backtest>(`/api/patients/${id}/refit-backtest`),
  activities: (id: string) => j<ActivityRec[]>(`/api/patients/${id}/activities`),
  addActivity: (id: string, body: { minutes: number; when: "after_next_meal" | "now" | "done"; minutes_ago?: number }, as?: Session) =>
    j<ActivityRec>(`/api/patients/${id}/activities`, post({ kind: "walk", ...body }), as),
  removeActivity: (id: string, aid: string, as?: Session) => j<unknown>(`/api/patients/${id}/activities/${aid}`, { method: "DELETE" }, as),
  messages: (id: string) => j<MessageRec[]>(`/api/patients/${id}/messages`),
  addMessage: (id: string, body: { key: string; text?: string; params?: Record<string, unknown> }, as?: Session) =>
    j<MessageRec>(`/api/patients/${id}/messages`, post(body), as),
  removeMessage: (id: string, mid: string, as?: Session) => j<unknown>(`/api/patients/${id}/messages/${mid}`, { method: "DELETE" }, as),
  walkResult: (id: string) => j<WalkResult>(`/api/patients/${id}/walk-result`),
  handover: (hours = 12) => j<Handover>(`/api/handover?hours=${hours}`),
  digest: () => j<Digest>("/api/digest"),
  audit: (id?: string) => j<AuditRow[]>(`/api/audit${id ? `?pid=${id}` : ""}`),
  modelCard: () => j<{ metrics: any; alert_level: number; cardio_threshold: number; figures: string[]; followup: any; counterfactual: any }>("/api/model-card"),
};

// Display preferences, set from Settings. The service always works in mg/dL and India time.
export const IST = "Asia/Kolkata";
export const prefs: { units: "mgdl" | "mmol"; tz: "ist" | "local" } = { units: "mgdl", tz: "ist" };
const zone = () => (prefs.tz === "ist" ? IST : undefined);
export const zoneName = () => (prefs.tz === "ist" ? "IST" :
  new Intl.DateTimeFormat("en-GB", { timeZoneName: "short" }).formatToParts(new Date()).find(p => p.type === "timeZoneName")?.value ?? "local time");
export const hhmm = (iso: string | number | Date) =>
  new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: zone(), hour12: false });
export const dayMonth = (iso: string | Date) =>
  new Date(iso).toLocaleDateString("en-GB", { day: "2-digit", month: "short", timeZone: zone() });
export const fullTime = (iso: string) =>
  new Date(iso).toLocaleString("en-GB", { weekday: "short", day: "2-digit", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit", timeZone: zone(), hour12: false }).replace(",", "");

const MMOL = 18.0182;
export const gluUnit = () => (prefs.units === "mmol" ? "mmol/L" : "mg/dL");
/** A glucose value in the chosen unit. */
export const glu = (v: number | null | undefined) =>
  v === null || v === undefined || !isFinite(v) ? "n/a" : prefs.units === "mmol" ? (v / MMOL).toFixed(1) : v.toFixed(0);
/** A glucose difference, without sign. */
export const gluAbs = (v: number) => glu(Math.abs(v));
export const gluTick = (v: number) => (prefs.units === "mmol" ? (v / MMOL).toFixed(1) : String(v));

/** Rewrites glucose values and clock times inside text that comes from the service (alerts, reasons, notes). */
export function T(s: string): string {
  if (!s) return s;
  let out = s;
  if (prefs.units === "mmol") {
    const c = (n: string) => (Number(n) / MMOL).toFixed(1);
    out = out.replace(/\b(\d{2,3}) (to|and) (\d{2,3})\b(?![:.,]\d|\s*(?:min|g\b|h\b|%|bpm|ms|steps|years|days|nights))/g,
      (m, x, w, y) => (Number(x) >= 40 && Number(y) >= 40 && Number(x) <= 450 && Number(y) <= 450 ? `${c(x)} ${w} ${c(y)}` : m));
    out = out.replace(/(\d+(?:\.\d+)?) mg\/dL/g, (_, n) => `${(Number(n) / MMOL).toFixed(1)} mmol/L`)
      .replace(/\b(peak|highest|lowest|reading|above|below|crossing|exceeding|over|under|to|between|now|minimum)( about)? (\d{2,3})\b(?![:.,]\d|\s*(?:min|g\b|h\b|%|bpm|ms|steps|years|days|nights))/gi,
        (m, w, a, n) => (Number(n) >= 40 && Number(n) <= 450 ? `${w}${a ?? ""} ${(Number(n) / MMOL).toFixed(1)}` : m));
  }
  if (prefs.tz === "local") {
    const shift = -new Date().getTimezoneOffset() - 330;
    if (shift) out = out.replace(/\b([01]\d|2[0-3]):([0-5]\d)\b/g, (_, h, m) => {
      const t = (((Number(h) * 60 + Number(m) + shift) % 1440) + 1440) % 1440;
      return `${String(Math.floor(t / 60)).padStart(2, "0")}:${String(t % 60).padStart(2, "0")}`;
    });
  }
  return out;
}
export const START = new Date("2026-02-14T00:00:00+05:30");
export const minuteToDate = (m: number) => new Date(START.getTime() + m * 60000);
export const dayToDate = (d: number) => new Date(START.getTime() + d * 86400000);
export const fmt = (v: number | null | undefined, digits = 0) => (v === null || v === undefined || !isFinite(v) ? "n/a" : v.toFixed(digits));
export const signed = (v: number | null | undefined, digits = 0) =>
  v === null || v === undefined || !isFinite(v) ? "n/a" : `${v > 0 ? "+" : v < 0 ? "-" : ""}${Math.abs(v).toFixed(digits)}`;
