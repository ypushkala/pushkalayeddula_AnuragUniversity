import { useEffect, useRef, useState } from "react";
import { store, stored } from "../live";

const LANG: Record<string, string> = { en: "en-IN", hi: "hi-IN", ta: "ta-IN" };
const UNIT: Record<string, [RegExp, string][]> = {
  en: [[/mg\/dL/g, "milligrams per decilitre"], [/mmol\/L/g, "millimoles per litre"], [/\bmin\b/g, "minutes"], [/\b(\d+) g\b/g, "$1 grams"]],
  hi: [[/mg\/dL/g, "मिलीग्राम प्रति डेसीलीटर"], [/mmol\/L/g, "मिलीमोल प्रति लीटर"]],
  ta: [[/mg\/dL/g, "மில்லிகிராம் பர் டெசிலிட்டர்"], [/mmol\/L/g, "மில்லிமோல் பர் லிட்டர்"]],
};

/** Text as it should be spoken: units in words, split into sentences so a long message can be followed and stopped. */
export function spoken(text: string, lang: string): string[] {
  let t = text;
  for (const [re, w] of UNIT[lang] ?? []) t = t.replace(re, w);
  return t.split(/(?<=[.।?!])\s+/).map(x => x.trim()).filter(Boolean);
}

function voicesFor(lang: string): SpeechSynthesisVoice[] {
  const code = LANG[lang] ?? "en-IN";
  const vs = window.speechSynthesis.getVoices();
  const exact = vs.filter(v => v.lang.replace("_", "-") === code);
  return exact.length ? exact : vs.filter(v => v.lang.toLowerCase().startsWith(code.slice(0, 2)));
}

/** Reads text aloud with the device's own voices (Web Speech API); nothing leaves the device.
 *  If the device has no voice for the language and an English version is given, it offers that instead. */
export function Listen({ text, lang = "en", label = "Listen", stopLabel = "Stop", english, compact = false }: {
  text: string; lang?: string; label?: string; stopLabel?: string; english?: string; compact?: boolean;
}) {
  const supported = typeof window !== "undefined" && "speechSynthesis" in window;
  const [voices, setVoices] = useState<SpeechSynthesisVoice[] | null>(null);
  const [voiceName, setVoiceName] = useState(() => stored(`prativimb-voice-${lang}`, ""));
  const [slow, setSlow] = useState(() => stored("prativimb-voice-slow", "0") === "1");
  const [part, setPart] = useState<[number, number] | null>(null);
  const cancelled = useRef(false);

  useEffect(() => {
    if (!supported) return;
    const pick = () => { const v = window.speechSynthesis.getVoices(); if (v.length) setVoices(voicesFor(lang)); };
    pick();
    window.speechSynthesis.addEventListener("voiceschanged", pick);
    return () => { window.speechSynthesis.removeEventListener("voiceschanged", pick); window.speechSynthesis.cancel(); };
  }, [lang, supported]);
  if (!supported) return null;

  const stop = () => { cancelled.current = true; window.speechSynthesis.cancel(); setPart(null); };
  const speak = (t: string, l: string) => {
    const ss = window.speechSynthesis;
    ss.cancel();
    cancelled.current = false;
    const parts = spoken(t, l);
    const vs = voicesFor(l);
    const voice = vs.find(v => v.name === voiceName) ?? vs[0];
    const say = (i: number) => {
      if (cancelled.current || i >= parts.length) { setPart(null); return; }
      setPart([i + 1, parts.length]);
      const u = new SpeechSynthesisUtterance(parts[i]);
      u.lang = LANG[l] ?? "en-IN";
      if (voice) u.voice = voice;
      u.rate = slow ? 0.75 : 0.95;
      u.onend = () => say(i + 1);
      u.onerror = () => setPart(null);
      ss.speak(u);
    };
    say(0);
  };
  const missing = voices !== null && voices.length === 0 && lang !== "en";
  return (
    <span className="listen">
      <button className="btn" onClick={() => (part ? stop() : speak(text, lang))} aria-pressed={Boolean(part)}>{part ? stopLabel : label}</button>
      {part && <span className="small muted" aria-live="polite">{part[0]} / {part[1]}</span>}
      {(!compact || part) && <label className="small listen-slow"><input type="checkbox" checked={slow}
        onChange={e => { setSlow(e.target.checked); store("prativimb-voice-slow", e.target.checked ? "1" : "0"); }} />{lang === "hi" ? "धीरे" : lang === "ta" ? "மெதுவாக" : "Slower"}</label>}
      {!compact && voices && voices.length > 1 && (
        <select className="small" value={voiceName} aria-label="Voice"
          onChange={e => { setVoiceName(e.target.value); store(`prativimb-voice-${lang}`, e.target.value); }}>
          {voices.map(v => <option key={v.name} value={v.name}>{v.name}</option>)}
        </select>
      )}
      {missing && (
        <span className="small muted listen-missing">
          This device has no {lang === "hi" ? "Hindi" : "Tamil"} voice. Add one in the phone's or computer's speech settings
          {english ? <>, or <button className="link-btn" onClick={() => speak(english, "en")}>listen in English</button></> : ""}.
        </span>
      )}
    </span>
  );
}
