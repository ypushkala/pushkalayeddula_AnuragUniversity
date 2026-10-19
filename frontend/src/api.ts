export type Tier = "alert" | "watch" | "high" | null;

export interface Clock { minute: number; now: string; speed: number; paused: boolean; start: string; end: string }

export interface Ack { id: string; pid: string; kind: string; by: string; minute: number; until: number; note: string; t?: string; until_t?: string }
export interface EventA {
  glucose: number; trend30: number | null; peak: number; peak_minute: number; tier: Tier;
  low: "now" | "forecast" | null; cross_minute?: number; low_minute?: number; low_value?: number; low_p?: number;
  ack?: Ack | null; low_ack?: Ack | null; artefact?: boolean;
}
export interface EventB {
  risk: number | null; flag: boolean; post_event: boolean; day: number; flag_since?: number | null;
  event_minute?: number; event?: string; ack?: Ack | null;
}
export interface WardRow {
  id: string; name: string; age: number; sex: string; problems: string[]; hba1c: number;
  glucose: number | null; trend30: number | null; sparkline: (number | null)[];
  event_a: EventA | null; event_b: EventB; last_sync: string | null; priority: number; hero: boolean; split: string;
}
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
  device: string; context: string[]; split: string;
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
  entered_minute: number; type: "planned" | "logged"; t: string }
export interface AuditRow { action: string; wall_time: string; pid: string; by?: string; kind?: string; minute?: number;
  label?: string; carbs?: number; note?: string; until?: number; removed_by?: string }
export interface Lever { label: string; request: Partial<WhatIfReq>; peak: number; tar_min: number; auc_above_180: number; mean: number; combined: boolean }
export interface Forecast {
  available: boolean; reason?: string; origin: string;
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
  sleep_hours: number | null; night_shift: boolean; scope: "next" | "all"; horizon_h: 6 | 24 }
export interface WhatIfSummary { peak: number; peak_time: string; tar_min: number; tbr_min: number; mean: number; tir_pct: number; auc_above_180: number }
export interface WhatIf {
  available: boolean; origin: string; times: string[]; baseline: number[]; scenario: number[];
  baseline_summary: WhatIfSummary; scenario_summary: WhatIfSummary;
  delta: { peak: number; tar_min: number; mean: number; auc_above_180: number; tir_pct: number };
  target_meal: { time: string; carbs: number; new_time: string } | null; note: string; solver: string;
  horizon_h: number; scope: string; meals_changed: number;
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

async function j<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init);
  if (!r.ok) throw new Error(`${r.status} ${url}`);
  return r.json() as Promise<T>;
}

export const api = {
  clock: () => j<Clock>("/api/clock"),
  setClock: (body: Partial<{ minute: number; at: string; speed: number; paused: boolean }>) =>
    j<Clock>("/api/clock", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  ward: () => j<Ward>("/api/ward"),
  patient: (id: string) => j<PatientDetail>(`/api/patients/${id}`),
  timeline: (id: string, hours = 12) => j<Timeline>(`/api/patients/${id}/timeline?hours=${hours}`),
  forecast: (id: string) => j<Forecast>(`/api/patients/${id}/forecast`),
  agp: (id: string) => j<Agp>(`/api/patients/${id}/agp?days=14`),
  alertLog: (id: string) => j<LogEntry[]>(`/api/patients/${id}/alert-log?hours=6`),
  whatif: (id: string, req: WhatIfReq) =>
    j<WhatIf>(`/api/patients/${id}/whatif`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(req) }),
  cardio: (id: string, endDay?: number) => j<CardioView>(`/api/patients/${id}/cardio${endDay !== undefined ? `?end_day=${endDay}` : ""}`),
  note: (id: string) => j<Note>(`/api/patients/${id}/note`),
  levers: (id: string, horizon = 6, scope = "next") => j<{ available: boolean; levers: Lever[]; target_meal: WhatIf["target_meal"] }>(
    `/api/patients/${id}/levers?horizon_h=${horizon}&scope=${scope}`),
  mealTypes: () => j<{ kind: string; label: string; speed: number }[]>("/api/meal-types"),
  addMeal: (id: string, body: { minutes_from_now: number; carbs: number; kind: string; label: string; by: string }) =>
    j<MealEntryRec>(`/api/patients/${id}/meals`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  removeMeal: (id: string, mealId: string, by: string) =>
    j<{ removed: string }>(`/api/patients/${id}/meals/${mealId}?by=${encodeURIComponent(by)}`, { method: "DELETE" }),
  ack: (id: string, body: { kind: string; by: string; snooze_minutes: number; note?: string }) =>
    j<Ack>(`/api/patients/${id}/ack`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  audit: (id?: string) => j<AuditRow[]>(`/api/audit${id ? `?pid=${id}` : ""}`),
  modelCard: () => j<{ metrics: any; alert_level: number; cardio_threshold: number; figures: string[] }>("/api/model-card"),
};

const IST = "Asia/Kolkata";
export const hhmm = (iso: string | number | Date) =>
  new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: IST, hour12: false });
export const dayMonth = (iso: string | Date) =>
  new Date(iso).toLocaleDateString("en-GB", { day: "2-digit", month: "short", timeZone: IST });
export const fullTime = (iso: string) =>
  new Date(iso).toLocaleString("en-GB", { weekday: "short", day: "2-digit", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit", timeZone: IST, hour12: false }).replace(",", "");
export const START = new Date("2026-02-14T00:00:00+05:30");
export const minuteToDate = (m: number) => new Date(START.getTime() + m * 60000);
export const dayToDate = (d: number) => new Date(START.getTime() + d * 86400000);
export const fmt = (v: number | null | undefined, digits = 0) => (v === null || v === undefined || !isFinite(v) ? "n/a" : v.toFixed(digits));
export const signed = (v: number | null | undefined, digits = 0) =>
  v === null || v === undefined || !isFinite(v) ? "n/a" : `${v > 0 ? "+" : v < 0 ? "-" : ""}${Math.abs(v).toFixed(digits)}`;
