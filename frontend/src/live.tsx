import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api, prefs, session as sessionRef, type Clock, type Role, type Session } from "./api";

export interface Palette { paper: string; paper2: string; rule: string; ruleStrong: string; ink: string; ink2: string; ink3: string;
  accent: string; accentWash: string; grey: string; alert: string; band: string }

export interface Prefs { units: "mgdl" | "mmol"; tz: "ist" | "local"; size: "normal" | "large"; notify: boolean; hints: boolean }

export interface Toast { id: number; text: string; undo?: () => Promise<unknown> | void; error?: boolean }

interface Live {
  clock: Clock | null; tick: number; connected: boolean; theme: "light" | "dark";
  setTheme: (t: "light" | "dark") => void; palette: Palette; refreshClock: () => void;
  /** The signed in person's name, used on acknowledgements and actions. */
  clinician: string; user: Session | null; signIn: (s: Session) => void; signOut: () => void;
  can: (what: Permission) => boolean;
  refresh: () => void;
  prefs: Prefs; setPrefs: (p: Partial<Prefs>) => void;
  toast: (t: Omit<Toast, "id">) => void; toasts: Toast[]; dismiss: (id: number) => void;
  hintSeen: (key: string) => boolean; seeHint: (key: string) => void; resetHints: () => void;
}

/** What each role may do. The API checks the same rules. */
export type Permission = "ack" | "ack-heart" | "act" | "plan" | "consent" | "meal";
const RULES: Record<Permission, Role[]> = {
  ack: ["doctor", "nurse"], "ack-heart": ["doctor"], act: ["doctor", "nurse"], plan: ["doctor"],
  consent: ["doctor", "patient"], meal: ["doctor", "nurse", "patient"],
};

export function stored(key: string, fallback: string): string {
  try { return localStorage.getItem(key) ?? fallback; } catch { return fallback; }
}
export function store(key: string, value: string): void {
  try { localStorage.setItem(key, value); } catch { /* storage may be unavailable */ }
}
function storedJson<T>(key: string, fallback: T): T {
  try { const v = localStorage.getItem(key); return v ? { ...fallback, ...JSON.parse(v) } : fallback; } catch { return fallback; }
}

const Ctx = createContext<Live | null>(null);

function readPalette(): Palette {
  const s = getComputedStyle(document.documentElement);
  const v = (n: string) => s.getPropertyValue(n).trim();
  return { paper: v("--paper"), paper2: v("--paper-2"), rule: v("--rule"), ruleStrong: v("--rule-strong"), ink: v("--ink"),
    ink2: v("--ink-2"), ink3: v("--ink-3"), accent: v("--accent"), accentWash: v("--accent-wash"), grey: v("--series-grey"),
    alert: v("--alert"), band: v("--band") };
}

function initialTheme(): "light" | "dark" {
  try {
    const t = localStorage.getItem("prativimb-theme");
    if (t === "light" || t === "dark") return t;
  } catch { /* storage may be unavailable */ }
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

const DEFAULT_PREFS: Prefs = { units: "mgdl", tz: "ist", size: "normal", notify: false, hints: true };

function readSession(): Session | null {
  try {
    const s = JSON.parse(localStorage.getItem("prativimb-session") ?? "null");
    return s && (s.role === "doctor" || s.role === "nurse" || s.role === "patient") ? s : null;
  } catch { return null; }
}

export function LiveProvider({ children }: { children: ReactNode }) {
  const [clock, setClock] = useState<Clock | null>(null);
  const [tick, setTick] = useState(0);
  const [connected, setConnected] = useState(false);
  const [theme, setThemeState] = useState<"light" | "dark">(initialTheme);
  const [palette, setPalette] = useState<Palette>(() => readPalette());
  const lastStep = useRef<number>(-1);
  const [user, setUser] = useState<Session | null>(() => { const s = readSession(); sessionRef.current = s; return s; });
  const [prefState, setPrefState] = useState<Prefs>(() => {
    const p = storedJson("prativimb-prefs", DEFAULT_PREFS);
    prefs.units = p.units; prefs.tz = p.tz;
    return p;
  });
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [hintsSeen, setHintsSeen] = useState<string[]>(() => { try { return JSON.parse(stored("prativimb-hints", "[]")); } catch { return []; } });
  const refresh = () => setTick(t => t + 1);

  const signIn = (s: Session) => { sessionRef.current = s; setUser(s); store("prativimb-session", JSON.stringify(s)); refresh(); };
  const signOut = () => { sessionRef.current = null; setUser(null); try { localStorage.removeItem("prativimb-session"); } catch { /* ignore */ } };
  const can = (what: Permission) => Boolean(user && RULES[what].includes(user.role));

  const setPrefs = (p: Partial<Prefs>) => setPrefState(old => {
    const next = { ...old, ...p };
    prefs.units = next.units; prefs.tz = next.tz;
    store("prativimb-prefs", JSON.stringify(next));
    return next;
  });

  useEffect(() => {
    // Larger text scales the whole page, charts included, so nothing overlaps.
    (document.documentElement.style as CSSStyleDeclaration & { zoom: string }).zoom = prefState.size === "large" ? "1.15" : "";
  }, [prefState.size]);

  const nextId = useRef(1);
  const dismiss = useCallback((id: number) => setToasts(ts => ts.filter(t => t.id !== id)), []);
  const toast = useCallback((t: Omit<Toast, "id">) => {
    const id = nextId.current++;
    setToasts(ts => [...ts.slice(-2), { ...t, id }]);
    window.setTimeout(() => dismiss(id), t.undo ? 10000 : 6000);
  }, [dismiss]);

  const seeHint = (key: string) => setHintsSeen(h => { const n = [...new Set([...h, key])]; store("prativimb-hints", JSON.stringify(n)); return n; });
  const resetHints = () => { setHintsSeen([]); store("prativimb-hints", "[]"); setPrefs({ hints: true }); };
  const hintSeen = (key: string) => !prefState.hints || hintsSeen.includes(key);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem("prativimb-theme", theme); } catch { /* ignore */ }
    setPalette(readPalette());
  }, [theme]);

  const refreshClock = () => { api.clock().then(c => { setClock(c); setTick(t => t + 1); }).catch(() => {}); };

  useEffect(() => {
    refreshClock();
    let ws: WebSocket | null = null;
    let retry: number | undefined;
    const connect = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${location.host}/ws/stream`);
      ws.onopen = () => setConnected(true);
      ws.onclose = () => { setConnected(false); retry = window.setTimeout(connect, 3000); };
      ws.onmessage = ev => {
        const msg = JSON.parse(ev.data);
        if (msg.minute !== undefined) {
          setClock({ minute: msg.minute, now: msg.now, speed: msg.speed, paused: msg.paused, start: msg.start, end: msg.end });
          const step = Math.floor(msg.minute / 5);
          if (step !== lastStep.current) { lastStep.current = step; setTick(t => t + 1); }
        }
      };
    };
    connect();
    return () => { window.clearTimeout(retry); if (ws) { ws.onclose = null; ws.close(); } };
  }, []);

  const value = useMemo(() => ({
    clock, tick, connected, theme, setTheme: setThemeState, palette, refreshClock,
    clinician: user?.name ?? "", user, signIn, signOut, can, refresh,
    prefs: prefState, setPrefs, toast, toasts, dismiss, hintSeen, seeHint, resetHints,
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [clock, tick, connected, theme, palette, user, prefState, toasts, hintsSeen]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useLive(): Live {
  const v = useContext(Ctx);
  if (!v) throw new Error("LiveProvider missing");
  return v;
}

/** Fetch on mount and whenever the replay advances a CGM step. Keeps the old data while refetching. */
export function useLiveData<T>(fn: () => Promise<T>, deps: unknown[]): { data: T | null; error: string | null } {
  const { tick } = useLive();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    fn().then(d => { if (alive) { setData(d); setError(null); } }).catch(e => alive && setError(e instanceof Error ? e.message : String(e)));
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tick, ...deps]);
  return { data, error };
}
