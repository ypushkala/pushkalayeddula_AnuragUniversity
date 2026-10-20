import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, hhmm, type Session } from "../api";
import { Listen } from "../components/Listen";
import { store, stored, useLive, useLiveData } from "../live";
import { fill, SHARE_T, type Lang } from "./Share";

const P: Record<Lang, Record<string, string>> = {
  en: {
    head: "Messages from your care team", nudge: "{name}, after dinner your sugar may go up to about {peak}. {lever} could keep it nearer {after}.",
    calm: "{name}, your sugar looks steady for the next two hours. Keep to your usual plan.", ask: "Will you try it tonight?",
    will_walk: "I will walk after dinner", walked: "I walked 15 minutes just now", not_today: "Not today",
    thanksPlan: "Thank you. With the walk, your forecast now expects about {peak} after dinner.",
    thanksNot: "That is fine. We will keep an eye on it tonight.",
    result: "Tonight your sugar went up to {with}. Without the walk it would have reached about {without}. Well done.",
    pending: "We will tell you how the walk went once it has had time to work.", listen: "Listen", stop: "Stop",
    disclaimer: "From your care team at the diabetes clinic. Not an emergency service: if you feel unwell, call your doctor or 108.", you: "You",
    team: "Care team", none: "No messages from your care team yet.",
  },
  hi: {
    head: "आपकी देखभाल टीम के संदेश", nudge: "{name}, रात के खाने के बाद आपकी शुगर लगभग {peak} तक जा सकती है। अगर आप यह करें: {lever}, तो यह लगभग {after} के आसपास रह सकती है।",
    calm: "{name}, अगले दो घंटे आपकी शुगर ठीक दिख रही है। अपनी सामान्य दिनचर्या जारी रखें।", ask: "क्या आप आज रात यह करेंगे?",
    will_walk: "हाँ, खाने के बाद टहलेंगे", walked: "अभी 15 मिनट टहलकर आए", not_today: "आज नहीं",
    thanksPlan: "धन्यवाद। टहलने के साथ, खाने के बाद आपकी शुगर लगभग {peak} तक रहने की उम्मीद है।",
    thanksNot: "कोई बात नहीं। आज रात हम इस पर नज़र रखेंगे।",
    result: "आज रात आपकी शुगर {with} तक गई। बिना टहले यह लगभग {without} तक जाती। बहुत अच्छा।",
    pending: "टहलने का असर दिखने के बाद हम आपको बताएँगे।", listen: "सुनें", stop: "रोकें",
    disclaimer: "डायबिटीज़ क्लिनिक की देखभाल टीम की ओर से। यह आपातकालीन सेवा नहीं है: तबीयत ठीक न लगे तो अपने डॉक्टर को या 108 पर फ़ोन करें।", you: "आप",
    team: "देखभाल टीम", none: "अभी तक आपकी देखभाल टीम का कोई संदेश नहीं।",
  },
  ta: {
    head: "உங்கள் மருத்துவக் குழுவின் செய்திகள்", nudge: "{name}, இரவு உணவுக்குப் பிறகு உங்கள் சர்க்கரை சுமார் {peak} வரை உயரலாம். {lever} என்றால் அது சுமார் {after} அளவில் இருக்கலாம்.",
    calm: "{name}, அடுத்த இரண்டு மணி நேரம் உங்கள் சர்க்கரை சீராக உள்ளது. வழக்கமான திட்டத்தைத் தொடருங்கள்.", ask: "இன்றிரவு இதை முயற்சிப்பீர்களா?",
    will_walk: "சாப்பிட்ட பிறகு நடப்பேன்", walked: "இப்போதுதான் 15 நிமிடம் நடந்தேன்", not_today: "இன்று இல்லை",
    thanksPlan: "நன்றி. நடையுடன், உணவுக்குப் பிறகு உங்கள் சர்க்கரை சுமார் {peak} வரை இருக்கும் என எதிர்பார்க்கப்படுகிறது.",
    thanksNot: "பரவாயில்லை. இன்றிரவு நாங்கள் கவனித்துக் கொள்வோம்.",
    result: "இன்றிரவு உங்கள் சர்க்கரை {with} வரை சென்றது. நடக்காமல் இருந்திருந்தால் சுமார் {without} வரை சென்றிருக்கும். நன்று.",
    pending: "நடையின் பலன் தெரிந்ததும் உங்களுக்குச் சொல்கிறோம்.", listen: "கேளுங்கள்", stop: "நிறுத்து",
    disclaimer: "நீரிழிவு மருத்துவமனையின் மருத்துவக் குழுவிடமிருந்து. இது அவசர சேவை அல்ல: உடல்நிலை சரியில்லை என்றால் உங்கள் மருத்துவரை அல்லது 108 ஐ அழைக்கவும்.", you: "நீங்கள்",
    team: "மருத்துவக் குழு", none: "உங்கள் மருத்துவக் குழுவிடமிருந்து இன்னும் செய்திகள் இல்லை.",
  },
};

const FEST: Record<string, Record<Lang, string>> = {
  "Gudi Padwa": { en: "Gudi Padwa", hi: "गुड़ी पड़वा", ta: "குடி பட்வா" }, Ugadi: { en: "Ugadi", hi: "उगादि", ta: "யுகாதி" },
  Navratri: { en: "Navratri", hi: "नवरात्रि", ta: "நவராத்திரி" }, "Eid al-Fitr": { en: "Eid al-Fitr", hi: "ईद", ta: "ரம்ஜான்" },
};
const DISH: Record<string, Record<Lang, string>> = {
  "puran poli": { en: "puran poli", hi: "पूरन पोली", ta: "பூரண் போளி" },
  "obbattu (holige)": { en: "obbattu (holige)", hi: "ओब्बट्टु (होलिगे)", ta: "ஒப்பட்டு (ஹோளிகே)" },
  "bobbatlu and ugadi pachadi": { en: "bobbatlu", hi: "बोब्बट्लु", ta: "போளி" },
  sabudana: { en: "sabudana", hi: "साबूदाना", ta: "ஜவ்வரிசி" }, "sheer khurma": { en: "sheer khurma", hi: "शीर ख़ुरमा", ta: "ஷீர் குர்மா" },
};
const FEST_T: Record<Lang, { msg: string; half_sweets: string; walk: string; smaller_fast: string; general: string }> = {
  en: { general: "Small helpings of the sweets and a short walk after the festive meal help.", msg: "{name}, {festival} is on {date}. On a day like that your sugar may stay high for about {extra} minutes longer than usual. {tip}",
    half_sweets: "Taking half the usual helping of {dish} could take about {saved} minutes off that.",
    walk: "A 15 minute walk after the festive meal could take about {saved} minutes off that.",
    smaller_fast: "A smaller fast meal, with some curd or fruit, could take about {saved} minutes off that." },
  hi: { general: "मिठाई थोड़ी कम लें और त्योहार के भोजन के बाद थोड़ा टहलें, इससे मदद मिलती है।", msg: "{name}, {date} को {festival} है। ऐसे दिन आपकी शुगर सामान्य से लगभग {extra} मिनट ज़्यादा देर ऊँची रह सकती है। {tip}",
    half_sweets: "{dish} की आधी मात्रा लेने से इसमें लगभग {saved} मिनट कम हो सकते हैं।",
    walk: "त्योहार के भोजन के बाद 15 मिनट टहलने से इसमें लगभग {saved} मिनट कम हो सकते हैं।",
    smaller_fast: "व्रत का भोजन थोड़ा कम और साथ में दही या फल लेने से इसमें लगभग {saved} मिनट कम हो सकते हैं।" },
  ta: { general: "இனிப்புகளை குறைவாக எடுத்து, பண்டிகை உணவுக்குப் பின் சிறிது நடப்பது உதவும்.", msg: "{name}, {date} அன்று {festival}. அப்படிப்பட்ட நாளில் உங்கள் சர்க்கரை வழக்கத்தை விட சுமார் {extra} நிமிடம் அதிக நேரம் உயர்ந்தே இருக்கலாம். {tip}",
    half_sweets: "{dish} வழக்கமான அளவில் பாதி எடுத்தால் இதில் சுமார் {saved} நிமிடம் குறையலாம்.",
    walk: "பண்டிகை உணவுக்குப் பின் 15 நிமிடம் நடந்தால் இதில் சுமார் {saved} நிமிடம் குறையலாம்.",
    smaller_fast: "விரத உணவை சற்று குறைவாக, தயிர் அல்லது பழத்துடன் எடுத்தால் இதில் சுமார் {saved} நிமிடம் குறையலாம்." },
};
const LOCALE: Record<Lang, string> = { en: "en-IN", hi: "hi-IN", ta: "ta-IN" };

function Bubble({ who, time, text, lang, listen, stop, english }: { who: "team" | "you"; time: string; text: string; lang: Lang; listen?: string; stop?: string;
  english?: string }) {
  return (
    <div className={`bubble ${who}`}>
      <p>{text}</p>
      <div className="b-foot"><span className="small">{time}</span>{who === "team" && listen && <Listen text={text} lang={lang} label={listen} stopLabel={stop} english={english} compact />}</div>
    </div>
  );
}

/** What the patient sees on their phone: a nudge in their language, replies that reach the care team, and how it went. */
export function Phone() {
  const { id = "" } = useParams();
  const { clock, refresh, toast, user } = useLive();
  const [lang, setLangState] = useState<Lang>(() => (stored("prativimb-share-lang", "hi") as Lang));
  const setLang = (l: Lang) => { setLangState(l); store("prativimb-share-lang", l); };
  const det = useLiveData(() => api.patient(id), [id]).data;
  const msgs = useLiveData(() => api.messages(id), [id]).data;
  const acts = useLiveData(() => api.activities(id), [id]).data ?? [];
  const result = useLiveData(() => api.walkResult(id), [id]).data;
  const [busy, setBusy] = useState(false);
  if (!det || !msgs || !clock) return <main className="phone-page"><p className="empty">Loading.</p></main>;
  const t = P[lang], st = SHARE_T[lang];
  const first = det.patient.name.split(" ")[0];
  const me: Session = { role: "patient", name: first, pid: id };
  const text = (m: typeof msgs[number], l: Lang = lang): string => {
    const t = P[l], st = SHARE_T[l], lang_ = l;
    if (m.key === "nudge") return fill(t.nudge, { name: first, peak: m.params.peak ?? "", lever: st[m.params.lever ?? "walk15"] ?? "", after: m.params.after ?? "" });
    if (m.key === "festival") {
      const ft = FEST_T[lang_], pr = m.params;
      const date = pr.date ? new Date(`${pr.date}T12:00:00+05:30`).toLocaleDateString(LOCALE[lang_], { day: "numeric", month: "long", timeZone: "Asia/Kolkata" }) : "";
      // A suggestion that saves only a few minutes is not worth a number; say what generally helps instead.
      const tip = (pr.saved_min ?? 0) < 15 ? ft.general : fill(ft[(pr.tip ?? "walk") as "walk"], { dish: DISH[pr.dish ?? ""]?.[lang_] ?? pr.dish ?? "", saved: pr.saved_min ?? "" });
      return fill(ft.msg, { name: first, festival: FEST[pr.local_name ?? ""]?.[lang_] ?? pr.local_name ?? "", date, extra: pr.extra_min ?? "", tip });
    }
    if (m.key === "thanks_plan") return fill(t.thanksPlan, { peak: m.params.peak ?? "" });
    if (m.key === "thanks_not") return t.thanksNot;
    return t[m.key] ?? m.text;
  };
  const lastNudge = msgs.map(m => m.key).lastIndexOf("nudge");
  const awaiting = lastNudge >= 0 && !msgs.slice(lastNudge).some(m => m.from === "patient");
  const reply = (key: "will_walk" | "walked" | "not_today") => {
    setBusy(true);
    const act = key === "will_walk" ? api.addActivity(id, { minutes: 15, when: "after_next_meal" }, me)
      : key === "walked" ? api.addActivity(id, { minutes: 15, when: "done", minutes_ago: 15 }, me) : Promise.resolve(null);
    act.then(a => api.addMessage(id, { key, text: P.en[key] }, me).then(m => {
      refresh();
      toast({ text: "Reply sent to the care team.", undo: () => Promise.all([api.removeMessage(id, m.id, me), a ? api.removeActivity(id, a.id, me) : null]) });
    })).catch(e => toast({ text: e.message, error: true })).finally(() => setBusy(false));
  };
  const walked = acts.length > 0 && msgs.some(m => m.from === "patient" && m.key !== "not_today");
  return (
    <main className="phone-page" id="main" lang={lang}>
      <div className="phone-tools no-print">
        {user && user.role !== "patient" && <Link to={`/patient/${id}`} className="small">Back to {det.patient.name}</Link>}
        <label className="small">{st.lang}{" "}
          <select value={lang} onChange={e => setLang(e.target.value as Lang)}>
            <option value="en">English</option><option value="hi">हिन्दी</option><option value="ta">தமிழ்</option>
          </select>
        </label>
        <span className="small muted">Demo: what {first} sees on their phone. Replies reach the care team's dashboard at once.</span>
      </div>
      <div className="phone" aria-label={`${first}'s phone`}>
        <div className="phone-head"><b>{t.head}</b><span className="small">{det.patient.name}</span></div>
        {msgs.some(m => m.from !== "patient") && (
          <div className="phone-listen"><Listen text={msgs.filter(m => m.from !== "patient").map(m => text(m)).join(" ")} lang={lang}
            label={lang === "hi" ? "सभी संदेश सुनें" : lang === "ta" ? "எல்லா செய்திகளையும் கேளுங்கள்" : "Listen to all"} stopLabel={t.stop}
            english={msgs.filter(m => m.from !== "patient").map(m => text(m, "en")).join(" ")} /></div>
        )}
        <div className="thread">
          {!msgs.length && <p className="small muted">{t.none}</p>}
          {msgs.map(m => (
            <Bubble key={m.id} who={m.from === "patient" ? "you" : "team"} time={hhmm(m.t)} text={text(m)} lang={lang} english={text(m, "en")}
              listen={m.from === "patient" ? undefined : t.listen} stop={t.stop} />
          ))}
          {awaiting && <Bubble who="team" time={hhmm(msgs[lastNudge].t)} text={t.ask} lang={lang} listen={t.listen} stop={t.stop} />}
          {walked && result && (result.available
            ? <Bubble who="team" time={hhmm(clock.now)} text={fill(t.result, { with: Math.round(result.peak_with!), without: Math.round(result.peak_without!) })} lang={lang} listen={t.listen} stop={t.stop} />
            : <Bubble who="team" time={hhmm(clock.now)} text={t.pending} lang={lang} />)}
        </div>
        {awaiting && (
          <div className="replies">
            {(["will_walk", "walked", "not_today"] as const).map(k => (
              <button key={k} className={`btn ${k === "will_walk" ? "primary" : ""}`} disabled={busy} onClick={() => reply(k)}>{t[k]}</button>
            ))}
          </div>
        )}
        <p className="phone-foot small">{t.disclaimer}</p>
      </div>
    </main>
  );
}
