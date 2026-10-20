import { useEffect, useState } from "react";

const LANG: Record<string, string> = { en: "en-IN", hi: "hi-IN", ta: "ta-IN" };

/** Reads text aloud with the device's own voices (Web Speech API); nothing is sent anywhere. */
export function Listen({ text, lang = "en", label = "Listen", stopLabel = "Stop" }: { text: string; lang?: string; label?: string; stopLabel?: string }) {
  const supported = typeof window !== "undefined" && "speechSynthesis" in window;
  const [speaking, setSpeaking] = useState(false);
  const [voice, setVoice] = useState<SpeechSynthesisVoice | null | undefined>(undefined);
  useEffect(() => {
    if (!supported) return;
    const pick = () => {
      const vs = window.speechSynthesis.getVoices();
      if (!vs.length) return;
      const code = LANG[lang] ?? "en-IN";
      setVoice(vs.find(v => v.lang === code) ?? vs.find(v => v.lang.startsWith(code.slice(0, 2))) ?? null);
    };
    pick();
    window.speechSynthesis.addEventListener("voiceschanged", pick);
    return () => { window.speechSynthesis.removeEventListener("voiceschanged", pick); window.speechSynthesis.cancel(); };
  }, [lang, supported]);
  if (!supported) return null;
  const toggle = () => {
    const ss = window.speechSynthesis;
    if (speaking) { ss.cancel(); setSpeaking(false); return; }
    ss.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = LANG[lang] ?? "en-IN";
    if (voice) u.voice = voice;
    u.rate = 0.9;
    u.onend = () => setSpeaking(false);
    u.onerror = () => setSpeaking(false);
    setSpeaking(true);
    ss.speak(u);
  };
  return (
    <span className="listen">
      <button className="btn" onClick={toggle} aria-pressed={speaking}>{speaking ? stopLabel : label}</button>
      {voice === null && lang !== "en" && <span className="small muted"> This device has no {lang === "hi" ? "Hindi" : "Tamil"} voice installed; it may read with another voice.</span>}
    </span>
  );
}
