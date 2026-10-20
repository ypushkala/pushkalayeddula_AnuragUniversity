import "@fontsource/noto-sans-devanagari/400.css";
import "@fontsource/noto-sans-devanagari/600.css";
import "@fontsource/noto-sans-tamil/400.css";
import "@fontsource/noto-sans-tamil/600.css";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, fmt, hhmm, minuteToDate, type Lever, type Session } from "../api";
import { ConsentPanel } from "../components/ConsentPanel";
import { Listen } from "../components/Listen";
import { store, stored, useLive, useLiveData } from "../live";

export type Lang = "en" | "hi" | "ta";

// Lever wording keyed by the request the twin simulated.
export const LEVER_KEY = (r: Lever["request"]): string => {
  if (r.walk_minutes && r.swap === "millet") return "combo";
  if (r.walk_minutes === 15) return "walk15";
  if (r.walk_minutes === 30) return "walk30";
  if (r.swap) return r.swap;
  if (r.shift_hours && r.shift_hours < 0) return "early";
  if (r.sleep_hours) return "sleep";
  return "other";
};

export const SHARE_T: Record<Lang, Record<string, string>> = {
  en: {
    logHead: "Tell your care team about a meal", logNote: "It goes straight into your glucose forecast.", when: "When", food: "Food", size: "How much",
    eatnow: "Eating now", ago: "Ate 30 minutes ago", later: "In 1 hour", small: "Small", usual: "Usual", large: "Large", send: "Send",
    sent: "Sent. Your care team can see it.", dataHead: "Your data sharing",
    dataNote: "You can stop sharing at any time. Your care team will then stop seeing new readings from that source.",
    granted: "Shared", withdrawn: "Withdrawn", withdraw: "Stop sharing", grant: "Share again", since: "since", back: "Back to",
    rice_meal: "Rice, dal, sabzi", roti_meal: "Roti, dal, sabzi", millet_meal: "Ragi or jowar meal", idli_dosa: "Idli or dosa",
    poha_upma: "Poha or upma", biryani: "Biryani", tea_snack: "Tea with biscuits", fruit: "Fruit and milk", team: "your care team",
    title: "{name}, what could help tonight", now: "Your glucose now: {g} mg/dL.",
    forecast: "After your next meal it may rise to about {peak} mg/dL, around {time}.",
    calm: "Your glucose is expected to stay in the healthy range for the next two hours.",
    head: "What would help most, based on your glucose readings", line: "about {x} mg/dL lower at the peak",
    none: "No single change makes a large difference tonight. Keep to your usual plan.",
    disclaimer: "This is a suggestion from your care team, not a prescription. Talk to your doctor before changing any medicine.",
    footer: "Prepared {date} by {who} with Prativimb.", print: "Print", share: "Share on WhatsApp", lang: "Language",
    walk15: "Walk for 15 minutes after the meal", walk30: "Walk for 30 minutes after the meal",
    millet: "Eat millets (ragi or jowar) instead of white rice", brown_rice: "Eat brown rice instead of white rice",
    roti: "Eat roti instead of rice", half_portion: "Eat half the usual portion", early: "Eat the meal an hour earlier",
    sleep: "Sleep seven and a half hours for the next three nights", combo: "Walk 15 minutes and eat millets", other: "Other change",
  },
  hi: {
    logHead: "अपनी देखभाल टीम को भोजन के बारे में बताएँ", logNote: "यह सीधे आपकी शुगर के पूर्वानुमान में जुड़ जाता है।", when: "कब", food: "भोजन", size: "कितना",
    eatnow: "अभी खा रहे हैं", ago: "30 मिनट पहले खाया", later: "1 घंटे में", small: "कम", usual: "सामान्य", large: "ज़्यादा", send: "भेजें",
    sent: "भेज दिया। आपकी देखभाल टीम इसे देख सकती है।", dataHead: "आपके डेटा की साझेदारी",
    dataNote: "आप कभी भी साझा करना बंद कर सकते हैं। तब आपकी देखभाल टीम को उस स्रोत की नई रीडिंग नहीं दिखेंगी।",
    granted: "साझा", withdrawn: "वापस लिया गया", withdraw: "साझा करना बंद करें", grant: "फिर से साझा करें", since: "से", back: "वापस",
    rice_meal: "चावल, दाल, सब्ज़ी", roti_meal: "रोटी, दाल, सब्ज़ी", millet_meal: "रागी या ज्वार का भोजन", idli_dosa: "इडली या डोसा",
    poha_upma: "पोहा या उपमा", biryani: "बिरयानी", tea_snack: "चाय और बिस्कुट", fruit: "फल और दूध", team: "आपकी देखभाल टीम",
    title: "{name}, आज रात किन बातों से मदद मिल सकती है", now: "अभी आपकी शुगर: {g} mg/dL.",
    forecast: "अगले भोजन के बाद लगभग {time} बजे यह {peak} mg/dL तक जा सकती है।",
    calm: "अगले दो घंटों में आपकी शुगर सामान्य सीमा में रहने की उम्मीद है।",
    head: "आपकी शुगर रीडिंग के आधार पर सबसे ज़्यादा मदद इनसे मिलेगी", line: "शुगर का उच्चतम स्तर लगभग {x} mg/dL कम",
    none: "आज रात कोई एक बदलाव बड़ा फ़र्क नहीं डालता। अपनी सामान्य दिनचर्या जारी रखें।",
    disclaimer: "यह आपकी देखभाल टीम का सुझाव है, नुस्खा नहीं। कोई भी दवा बदलने से पहले अपने डॉक्टर से बात करें।",
    footer: "{date} को {who} द्वारा Prativimb से तैयार।", print: "प्रिंट करें", share: "WhatsApp पर भेजें", lang: "भाषा",
    walk15: "भोजन के बाद 15 मिनट टहलें", walk30: "भोजन के बाद 30 मिनट टहलें",
    millet: "सफ़ेद चावल की जगह रागी या ज्वार (मिलेट) खाएँ", brown_rice: "सफ़ेद चावल की जगह ब्राउन राइस खाएँ",
    roti: "चावल की जगह रोटी खाएँ", half_portion: "सामान्य से आधी मात्रा में खाएँ", early: "भोजन एक घंटा पहले करें",
    sleep: "अगली तीन रातें साढ़े सात घंटे सोएँ", combo: "15 मिनट टहलें और मिलेट खाएँ", other: "अन्य बदलाव",
  },
  ta: {
    logHead: "உங்கள் மருத்துவக் குழுவிடம் உணவைப் பற்றி சொல்லுங்கள்", logNote: "இது நேரடியாக உங்கள் சர்க்கரை முன்கணிப்பில் சேரும்.", when: "எப்போது", food: "உணவு", size: "எவ்வளவு",
    eatnow: "இப்போது சாப்பிடுகிறேன்", ago: "30 நிமிடங்களுக்கு முன் சாப்பிட்டேன்", later: "1 மணி நேரத்தில்", small: "குறைவாக", usual: "வழக்கம் போல்", large: "அதிகமாக", send: "அனுப்பு",
    sent: "அனுப்பப்பட்டது. உங்கள் மருத்துவக் குழு இதைப் பார்க்கலாம்.", dataHead: "உங்கள் தரவுப் பகிர்வு",
    dataNote: "எப்போது வேண்டுமானாலும் பகிர்வை நிறுத்தலாம். அதன் பிறகு அந்த மூலத்திலிருந்து புதிய அளவீடுகள் உங்கள் மருத்துவக் குழுவுக்குத் தெரியாது.",
    granted: "பகிரப்படுகிறது", withdrawn: "திரும்பப் பெறப்பட்டது", withdraw: "பகிர்வை நிறுத்து", grant: "மீண்டும் பகிர்", since: "முதல்", back: "திரும்ப",
    rice_meal: "சாதம், பருப்பு, காய்கறி", roti_meal: "சப்பாத்தி, பருப்பு, காய்கறி", millet_meal: "கேழ்வரகு அல்லது சோள உணவு", idli_dosa: "இட்லி அல்லது தோசை",
    poha_upma: "அவல் அல்லது உப்புமா", biryani: "பிரியாணி", tea_snack: "டீ மற்றும் பிஸ்கட்", fruit: "பழம் மற்றும் பால்", team: "உங்கள் மருத்துவக் குழு",
    title: "{name}, இன்றிரவு எது உதவக்கூடும்", now: "இப்போது உங்கள் சர்க்கரை அளவு: {g} mg/dL.",
    forecast: "அடுத்த உணவுக்குப் பிறகு இது சுமார் {time} மணிக்கு {peak} mg/dL வரை உயரலாம்.",
    calm: "அடுத்த இரண்டு மணி நேரம் உங்கள் சர்க்கரை அளவு சரியான வரம்பில் இருக்கும் என எதிர்பார்க்கப்படுகிறது.",
    head: "உங்கள் சர்க்கரை அளவீடுகளின் படி அதிகம் உதவக்கூடியவை", line: "உச்ச சர்க்கரை அளவு சுமார் {x} mg/dL குறையும்",
    none: "இன்றிரவு எந்த ஒரு மாற்றமும் பெரிய வேறுபாட்டை ஏற்படுத்தாது. உங்கள் வழக்கமான திட்டத்தைத் தொடருங்கள்.",
    disclaimer: "இது உங்கள் மருத்துவக் குழுவின் பரிந்துரை, மருந்துச் சீட்டு அல்ல. எந்த மருந்தையும் மாற்றும் முன் உங்கள் மருத்துவரிடம் பேசுங்கள்.",
    footer: "{date} அன்று {who} Prativimb மூலம் தயாரித்தது.", print: "அச்சிடு", share: "WhatsApp இல் பகிர்", lang: "மொழி",
    walk15: "உணவுக்குப் பின் 15 நிமிடம் நடக்கவும்", walk30: "உணவுக்குப் பின் 30 நிமிடம் நடக்கவும்",
    millet: "வெள்ளை அரிசிக்கு பதிலாக கேழ்வரகு அல்லது சோளம் (சிறுதானியம்) சாப்பிடவும்", brown_rice: "வெள்ளை அரிசிக்கு பதிலாக பழுப்பு அரிசி சாப்பிடவும்",
    roti: "அரிசிக்கு பதிலாக சப்பாத்தி சாப்பிடவும்", half_portion: "வழக்கமான அளவில் பாதி சாப்பிடவும்", early: "உணவை ஒரு மணி நேரம் முன்னதாக சாப்பிடவும்",
    sleep: "அடுத்த மூன்று இரவுகள் ஏழரை மணி நேரம் தூங்கவும்", combo: "15 நிமிடம் நடந்து சிறுதானியம் சாப்பிடவும்", other: "பிற மாற்றம்",
  },
};

const LISTEN: Record<Lang, [string, string]> = { en: ["Listen", "Stop"], hi: ["सुनें", "रोकें"], ta: ["கேளுங்கள்", "நிறுத்து"] };

export const fill = (s: string, v: Record<string, string | number>) => s.replace(/\{(\w+)\}/g, (_, k) => String(v[k] ?? ""));

const FOODS: [string, number][] = [["rice_meal", 90], ["roti_meal", 70], ["millet_meal", 60], ["idli_dosa", 55], ["poha_upma", 50],
  ["biryani", 95], ["tea_snack", 20], ["fruit", 25]];
const SIZES: [string, number][] = [["small", 0.6], ["usual", 1], ["large", 1.4]];
const WHENS: [string, number][] = [["eatnow", 0], ["ago", -30], ["later", 60]];

/** Patients log their own meals from the link their care team sent; it is entered as the patient, with an audit trail. */
function PatientMeal({ pid, t, as }: { pid: string; t: Record<string, string>; as: Session }) {
  const { refresh } = useLive();
  const [food, setFood] = useState("rice_meal");
  const [size, setSize] = useState(1);
  const [when, setWhen] = useState(0);
  const [msg, setMsg] = useState("");
  const send = () => {
    const carbs = Math.round((FOODS.find(f => f[0] === food)![1] * size) / 5) * 5;
    api.addMeal(pid, { minutes_from_now: when, carbs, kind: food, label: t[food] }, as)
      .then(() => { setMsg(t.sent); refresh(); }).catch(e => setMsg(e.message));
  };
  return (
    <section className="share-log no-print">
      <h2>{t.logHead}</h2>
      <p className="small muted">{t.logNote}</p>
      <div className="share-form">
        <label>{t.food}<select value={food} onChange={e => setFood(e.target.value)}>{FOODS.map(([k]) => <option key={k} value={k}>{t[k]}</option>)}</select></label>
        <label>{t.size}<select value={size} onChange={e => setSize(+e.target.value)}>{SIZES.map(([k, v]) => <option key={k} value={v}>{t[k]}</option>)}</select></label>
        <label>{t.when}<select value={when} onChange={e => setWhen(+e.target.value)}>{WHENS.map(([k, v]) => <option key={k} value={v}>{t[k]}</option>)}</select></label>
        <button className="btn primary" onClick={send}>{t.send}</button>
      </div>
      {msg && <p role="status">{msg}</p>}
    </section>
  );
}

export function Share() {
  const { id = "" } = useParams();
  const { clinician, clock, user } = useLive();
  const [lang, setLangState] = useState<Lang>(() => (stored("prativimb-share-lang", "en") as Lang));
  const setLang = (l: Lang) => { setLangState(l); store("prativimb-share-lang", l); };
  const det = useLiveData(() => api.patient(id), [id]).data;
  const fc = useLiveData(() => api.forecast(id), [id]).data;
  const lev = useLiveData(() => api.levers(id), [id]).data;
  const t = SHARE_T[lang];
  if (!det || !fc || !lev) return <main className="share" lang={lang}><p className="empty">Preparing.</p></main>;
  const first = det.patient.name.split(" ")[0];
  // Whoever opens the patient's link acts as the patient (as with a link sent by message); a signed in clinician stays themselves.
  const asPatient: Session = { role: "patient", name: first, pid: id };
  const clinicianView = Boolean(user && user.role !== "patient");
  const st = fc.available ? fc.status : null;
  const helpful = lev.levers.filter(l => l.peak <= -5).slice(0, 4);
  const lines: string[] = [fill(t.title, { name: first })];
  if (st) {
    lines.push(fill(t.now, { g: fmt(st.glucose) }));
    lines.push(st.peak > 180 ? fill(t.forecast, { peak: fmt(st.peak), time: hhmm(minuteToDate(st.peak_minute)) }) : t.calm);
  }
  const leverText = helpful.map(l => `${t[LEVER_KEY(l.request)]}: ${fill(t.line, { x: fmt(-l.peak) })}`);
  const date = clock ? new Date(clock.now).toLocaleDateString(lang === "en" ? "en-GB" : lang === "hi" ? "hi-IN" : "ta-IN",
    { day: "numeric", month: "long", timeZone: "Asia/Kolkata" }) : "";
  const en = SHARE_T.en;
  const englishText = [fill(en.title, { name: first }), ...(st ? [fill(en.now, { g: fmt(st.glucose) }),
    st.peak > 180 ? fill(en.forecast, { peak: fmt(st.peak), time: hhmm(minuteToDate(st.peak_minute)) }) : en.calm] : []),
    en.head, ...helpful.map(l => `${en[LEVER_KEY(l.request)]}: ${fill(en.line, { x: fmt(-l.peak) })}`)].join(". ");
  const shareText = [...lines, "", t.head + ":", ...leverText.map(x => `- ${x}`), "", t.disclaimer].join("\n");

  return (
    <main className="share" lang={lang} id="main">
      <div className="share-tools no-print">
        {clinicianView && <Link to={`/patient/${id}`} className="small">{t.back} {det.patient.name}</Link>}
        <label className="small">{t.lang}{" "}
          <select value={lang} onChange={e => setLang(e.target.value as Lang)}>
            <option value="en">English</option><option value="hi">हिन्दी</option><option value="ta">தமிழ்</option>
          </select>
        </label>
        <button className="btn" onClick={() => window.print()}>{t.print}</button>
        <a className="btn primary" href={`https://wa.me/?text=${encodeURIComponent(shareText)}`} target="_blank" rel="noreferrer">{t.share}</a>
      </div>
      <h1>{lines[0]}</h1>
      <div className="no-print"><Listen text={[...lines, t.head, ...leverText].join(". ")} lang={lang} label={LISTEN[lang][0]} stopLabel={LISTEN[lang][1]}
        english={englishText} /></div>
      {st && <p className="share-now">{lines[1]}<br />{lines[2]}</p>}
      <h2>{t.head}</h2>
      {helpful.length ? (
        <ol className="share-levers">
          {helpful.map((l, i) => (
            <li key={l.label}><span className="what">{t[LEVER_KEY(l.request)]}</span><span className="gain">{leverText[i].split(": ").slice(1).join(": ")}</span></li>
          ))}
        </ol>
      ) : <p>{t.none}</p>}
      <p className="share-disclaimer">{t.disclaimer}</p>
      <PatientMeal pid={id} t={t} as={asPatient} />
      <section className="share-data no-print">
        <h2>{t.dataHead}</h2>
        <p className="small muted">{t.dataNote}</p>
        <ConsentPanel pid={id} as={asPatient} labels={{ granted: t.granted, withdrawn: t.withdrawn, withdraw: t.withdraw, grant: t.grant, since: t.since }} />
      </section>
      <p className="small muted">{fill(t.footer, { date, who: clinicianView ? clinician : t.team })}</p>
      {lang !== "en" && <p className="small muted no-print">Hindi and Tamil text is a draft for review by a native speaking clinician before use with patients.</p>}
    </main>
  );
}
