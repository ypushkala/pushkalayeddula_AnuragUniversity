import { createContext, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api, type Clock } from "./api";

export interface Palette { paper: string; paper2: string; rule: string; ruleStrong: string; ink: string; ink2: string; ink3: string;
  accent: string; accentWash: string; grey: string; alert: string; band: string }

interface Live {
  clock: Clock | null; tick: number; connected: boolean; theme: "light" | "dark";
  setTheme: (t: "light" | "dark") => void; palette: Palette; refreshClock: () => void;
  clinician: string; setClinician: (n: string) => void; refresh: () => void;
}

export function stored(key: string, fallback: string): string {
  try { return localStorage.getItem(key) ?? fallback; } catch { return fallback; }
}
export function store(key: string, value: string): void {
  try { localStorage.setItem(key, value); } catch { /* storage may be unavailable */ }
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

export function LiveProvider({ children }: { children: ReactNode }) {
  const [clock, setClock] = useState<Clock | null>(null);
  const [tick, setTick] = useState(0);
  const [connected, setConnected] = useState(false);
  const [theme, setThemeState] = useState<"light" | "dark">(initialTheme);
  const [palette, setPalette] = useState<Palette>(() => readPalette());
  const lastStep = useRef<number>(-1);
  const [clinician, setClinicianState] = useState<string>(() => stored("prativimb-clinician", "Dr Rao"));
  const setClinician = (n: string) => { setClinicianState(n); store("prativimb-clinician", n); };
  const refresh = () => setTick(t => t + 1);

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

  const value = useMemo(() => ({ clock, tick, connected, theme, setTheme: setThemeState, palette, refreshClock,
    clinician, setClinician, refresh }), [clock, tick, connected, theme, palette, clinician]);
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
    fn().then(d => { if (alive) { setData(d); setError(null); } }).catch(e => alive && setError(String(e)));
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tick, ...deps]);
  return { data, error };
}
