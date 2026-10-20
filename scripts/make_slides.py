"""Build docs/presentation.pptx and docs/presentation.pdf from one slide specification.

Every number is read from reports/metrics.json, so the deck always matches the latest run.
Two renderers (python-pptx and matplotlib) draw the same elements at the same positions.
"""
from __future__ import annotations

import json
import textwrap
from dataclasses import dataclass, field

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.image import imread
from PIL import Image

from prativimb import config
from prativimb.eval import style

SW, SH = 13.333, 7.5
PAPER, INK, INK2, INK3, RULE, ACCENT, ALERT = (style.PAPER, style.INK, style.INK_2, style.INK_3, style.RULE,
                                                style.ACCENT, style.ALERT)
SHOTS = config.DOCS_DIR / "screenshots"
FIG = config.FIGURE_DIR


@dataclass
class Text:
    x: float; y: float; w: float; text: str; size: float = 14; color: str = INK; serif: bool = False
    bold: bool = False; italic: bool = False; bullets: bool = False; spacing: float = 1.35; align: str = "left"


@dataclass
class Rule:
    x: float; y: float; w: float; color: str = RULE; width: float = 0.8


@dataclass
class Img:
    path: str; x: float; y: float; w: float; h: float; border: bool = False


@dataclass
class Table:
    x: float; y: float; widths: list; rows: list; size: float = 12; bold_last: bool = False; row_h: float = 0.36


@dataclass
class Slide:
    title: str
    kicker: str = ""
    elements: list = field(default_factory=list)
    notes: str = ""


def chars_per_line(w_in: float, size: float) -> int:
    return max(10, int(w_in * 72 / (size * 0.47)))


def wrap(t: Text) -> list[str]:
    out = []
    for para in t.text.split("\n"):
        if not para.strip():
            out.append("")
            continue
        prefix = "•  " if t.bullets else ""
        lines = textwrap.wrap(para, chars_per_line(t.w - (0.25 if t.bullets else 0), t.size)) or [""]
        out.append(prefix + lines[0])
        out += [("   " if t.bullets else "") + l for l in lines[1:]]
        if t.bullets:
            out.append("")
    return out[:-1] if t.bullets and out and out[-1] == "" else out


def load_metrics() -> dict:
    return json.loads((config.REPORT_DIR / "metrics.json").read_text())


def case_study() -> dict:
    """Ramesh's what-if numbers at the demo clock, from the same code path as the API."""
    from prativimb.api.services import AppState
    st = AppState()
    t = config.datetime_to_minute(config.DEMO_NOW)
    pid = config.HERO_IDS["ramesh"]
    fc = st.patient_forecast(pid, t, explain=False)
    run = lambda req: st.whatif(pid, t, req)
    return {"peak": fc["status"]["peak"], "walk": run({"walk_minutes": 15}), "millet": run({"swap": "millet"}),
            "both": run({"walk_minutes": 15, "swap": "millet"}), "early": run({"shift_hours": -1.0})}


def early_text(r: dict) -> str:
    d = r["delta"]["peak"]
    if abs(d) < 3:
        return ("Moving dinner earlier barely changes the peak tonight (it can only move to "
                f"{r['target_meal']['new_time']}). The twin can say no.")
    if d > 0:
        return f"Eating earlier raises the peak by {d:.0f} mg/dL: lunch glucose has not settled. The twin can say no."
    return f"Eating an hour earlier lowers the peak by {-d:.0f} mg/dL."


def spec(m: dict, cs: dict) -> list[Slide]:
    g, al, cf, c = m["glucose"], m["alerts"], m["conformal"], m["cardio"]
    lv = m["alert_level"]["alert_coverage"]
    hy = lambda h: g[str(h)]["hyb"]["rmse"]
    S = []

    S.append(Slide("", elements=[
        Text(0.9, 1.6, 11, "Prativimb", 54, INK, serif=True),
        Text(0.9, 2.75, 11, "A patient twin that answers what if, not just what next.", 24, INK2, serif=True, italic=True),
        Rule(0.9, 3.65, 11.5, INK, 1.0),
        Text(0.9, 3.95, 11, "Hybrid digital twin for Type 2 diabetes and cardiovascular risk, built for Indian patients.", 16, INK2),
        Text(0.9, 4.45, 11, "Happiest Health hackathon. Digital Twin track, Phase 1: prototype and code.", 14, INK3),
        Text(0.9, 5.45, 11, "<TeamName>, <CollegeName> / <Incubator>", 15, INK),
        Text(0.9, 5.9, 11.5, "<Member 1, role>   <Member 2, role>   <Member 3, role>   <Member 4, role>   <team email>", 12.5, INK2),
        Text(0.9, 6.55, 11.5, "Prativimb is Sanskrit for reflection. Patient data shown is synthetic; real data validation uses open access CGMacros.", 11, INK3),
    ]))

    S.append(Slide("The problem", "Why now", [
        Text(0.9, 1.75, 6.2, "India has about 101 million adults with diabetes and 136 million with prediabetes (ICMR-INDIAB, Lancet Diabetes & Endocrinology, 2023).\n"
             "Most see a doctor every three months. Glucose, sleep and heart rhythm change every five minutes.\n"
             "CGMs and watches now record that stream, but they show what already happened.\n"
             "Risk scores say who is at risk. They do not say what to change today, or how sure they are.", 16, INK, bullets=True),
        Rule(7.6, 1.8, 4.9), Text(7.6, 1.95, 4.9, "What a clinician needs at the bedside", 14, INK, serif=True),
        Text(7.6, 2.5, 4.9, "Which patients will go out of range in the next two hours?\nWhy, in words, not feature names?\n"
             "What would help this patient: a walk, a different grain, an earlier dinner?\nWho is drifting towards a cardiac event this week?", 14, INK2, bullets=True),
    ]))

    S.append(Slide("Why a twin, and not another classifier", "Our angle", [
        Table(0.9, 1.9, [3.3, 4.2, 4.2], [
            ["", "Risk classifier", "Prativimb twin"],
            ["Question", "What happens next?", "What happens next, and what if we change something?"],
            ["Model", "Learned from data only", "Physiology (ODE) plus a learned residual"],
            ["Personal", "Population average", "Parameters fitted to each patient's first week"],
            ["Out of range inputs", "Unreliable", "Physics extrapolates plausibly"],
            ["Uncertainty", "A score", "Calibrated interval with stated coverage"],
            ["Reasons", "Feature importances", "mg/dL contributions, one plain sentence"],
        ], size=13.5, row_h=0.55),
        Text(0.9, 6.15, 11.5, "Prativimb is a reflection of the patient you can question.", 16, INK, serif=True, italic=True),
    ]))

    S.append(Slide("Our approach in four ideas", "Method", [
        Text(0.9, 1.8, 5.5, "1. Hybrid twin", 18, INK, serif=True),
        Text(0.9, 2.3, 5.5, "Bergman minimal model extended with meals, exercise, sleep debt, circadian rhythm, night shifts and metformin. EHR sets the prior, the first week of wearables fits 8 personal parameters, LightGBM learns what the physics misses.", 13, INK2),
        Text(6.9, 1.8, 5.5, "2. Counterfactuals", 18, INK, serif=True),
        Text(6.9, 2.3, 5.5, "Re-simulate the next six hours after a walk, a millet swap, a shifted dinner, a missed dose, more sleep or a night shift. Shows peak and time above range for both.", 13, INK2),
        Text(0.9, 4.2, 5.5, "3. Honest uncertainty", 18, INK, serif=True),
        Text(0.9, 4.7, 5.5, f"Conformalised quantile regression gives 90% intervals that reach {cf['60']['cqr_coverage'] * 100:.1f}% coverage at 60 min on unseen patients. Alerts fire only when the lower bound crosses 180.", 13, INK2),
        Text(6.9, 4.2, 5.5, "4. India first", 18, INK, serif=True),
        Text(6.9, 4.7, 5.5, "Rice, roti, idli and iftar meals with their absorption speeds; Ramadan, Shivaratri, Ekadashi and Holi in the calendar; night shift workers; cardiovascular risk at lower BMI.", 13, INK2),
    ]))

    S.append(Slide("Architecture", "System", [Img(str(config.DOCS_DIR / "architecture.png"), 0.6, 1.45, 12.1, 5.6)]))

    S.append(Slide("Data: synthetic, Indian, reproducible", "Data", [
        Text(0.9, 1.75, 5.9, "200 fictional patients, 30 days each (14 Feb to 15 Mar 2026): healthy, prediabetes and T2D; hypertension, dyslipidaemia, family history.\n"
             "EHR as FHIR R4 bundles: ICD-10, LOINC, ATC, TCF7L2, KCNQ1, SLC30A8 and 9p21 markers, DPDP style consent.\n"
             "Glucose from the UVA/Padova model with simglucose parameters and Dexcom noise, adapted for T2D. HR every minute, sleep stages, nightly HRV, steps.\n"
             "Apple Health and Google Fit export formats, parsed back by our adapters.\n"
             "One command regenerates everything in about 20 seconds from seed 20260315.", 13.5, INK, bullets=True),
        Img(str(SHOTS / "04_twin_fatima_iftar.png"), 7.2, 1.7, 5.4, 4.9, border=True),
        Text(7.2, 6.7, 5.4, "Fatima (synthetic): Ramadan pattern in her glucose profile.", 11, INK3),
    ]))

    S.append(Slide("Models", "Method", [
        Table(0.9, 1.75, [2.6, 9.0], [
            ["Component", "What it does"],
            ["Twin ODE", "dG/dt = -(SG + X)G + SG Gb H(t) + cf Ra(t) - eE E G, with insulin action, insulin, two gut compartments, exercise and metformin states"],
            ["Calibration", "MAP least squares on days 1 to 7 with EHR priors; about one second per patient"],
            ["Residual model", "LightGBM on twin error at 30, 60, 90, 120 min from CGM history, meals, activity, sleep, adherence, EHR"],
            ["Uncertainty", f"CQR intervals at 90%; the alert tier uses the lower bound of the {lv:.0%} interval, chosen on calibration patients"],
            ["Cardio", "Isolation forest and personal z scores (unsupervised) plus LightGBM, stacked by logistic regression"],
            ["Explanations", "Exact Shapley values over six twin inputs plus TreeSHAP on the residual, in mg/dL"],
        ], size=12.5, row_h=0.62),
    ]))

    S.append(Slide("Results: glucose forecasting", "Event A", [
        Img(str(FIG / "glucose_rmse_by_horizon.png"), 0.7, 1.55, 6.6, 3.9),
        Table(7.7, 1.8, [2.6, 1.0, 1.0, 1.0], [
            ["RMSE, mg/dL", "30", "60", "120"],
            ["Twin, EHR only", f"{g['30']['cold']['rmse']:.1f}", f"{g['60']['cold']['rmse']:.1f}", f"{g['120']['cold']['rmse']:.1f}"],
            ["Twin, calibrated", f"{g['30']['phys']['rmse']:.1f}", f"{g['60']['phys']['rmse']:.1f}", f"{g['120']['phys']['rmse']:.1f}"],
            ["LightGBM only", f"{g['30']['ml']['rmse']:.1f}", f"{g['60']['ml']['rmse']:.1f}", f"{g['120']['ml']['rmse']:.1f}"],
            ["Hybrid", f"{hy(30):.1f}", f"{hy(60):.1f}", f"{hy(120):.1f}"],
        ], size=13, bold_last=True, row_h=0.46),
        Text(7.7, 4.4, 4.9, f"Hybrid beats both of its parts at every horizon. MARD at 60 min {g['60']['hyb']['mard']:.1f}%. "
             f"Clarke zone A {g['60']['clarke']['A']:.1f}% at 60 min, zones C to E {g['60']['clarke']['C'] + g['60']['clarke']['D'] + g['60']['clarke']['E']:.1f}%.", 13, INK2),
        Text(0.9, 6.3, 11.5, f"{m['split']['test_patients']} test patients never seen in training or calibration. Scored on days 8 to 30.", 12, INK3),
    ]))

    S.append(Slide("Results: alerts and honest uncertainty", "Event A", [
        Img(str(FIG / "alert_tradeoff.png"), 0.6, 1.5, 6.1, 3.75),
        Img(str(FIG / "conformal_coverage.png"), 6.9, 1.6, 5.9, 2.55),
        Text(6.9, 4.4, 5.8, f"Alert tier: {al['alert']['sensitivity'] * 100:.0f}% of spikes flagged, {al['alert']['precision'] * 100:.0f}% precision, "
             f"{al['alert']['false_alarms_per_patient_day']:.2f} false alarms per patient day, median {al['alert']['median_lead_min']:.0f} min ahead.\n"
             f"Watch tier: {al['hyb']['sensitivity'] * 100:.0f}% flagged a median {al['hyb']['median_lead_min']:.0f} min ahead, shown but not pushed.\n"
             f"Coverage of the 90% interval: {cf['30']['cqr_coverage'] * 100:.1f}% to {cf['120']['cqr_coverage'] * 100:.1f}% across horizons.", 12.5, INK, bullets=True),
    ]))

    cr = c["components"]["risk"]
    op = c["operating_point"]
    fu = json.loads((config.REPORT_DIR / "followup.json").read_text())
    cf = json.loads((config.REPORT_DIR / "counterfactual.json").read_text())
    half = next(x for x in fu["cardio_stress"]["results"] if x["strength"] == 0.5)
    quarter = next(x for x in fu["cardio_stress"]["results"] if x["strength"] == 0.25)
    load = fu["alert_load"]
    S.append(Slide("Results: cardiovascular risk flag", "Event B", [
        Img(str(FIG / "cardio_performance.png"), 0.6, 1.5, 12.1, 4.05),
        Text(0.9, 5.75, 11.6, f"Ensemble AUROC {cr['auroc']:.2f} (95% CI {cr['auroc_ci'][0]:.2f} to {cr['auroc_ci'][1]:.2f}), AUPRC {cr['auprc']:.2f} at "
             f"{c['prevalence'] * 100:.1f}% prevalence, sensitivity {cr['sens_at_90spec'] * 100:.0f}% at 90% specificity. "
             f"At the 95% specificity operating point {op['events_caught']} of {op['events']} test events were flagged up to 3 days ahead. "
             f"Only {c['n_events']} test events, so intervals are wide. The events come from our own simulator: with its warning signs "
             f"weakened to half strength the flag catches {half['events_flagged']} of {half['events']}, at a quarter {quarter['events_flagged']} of {quarter['events']}. "
             "A demonstration of the pipeline, not a clinical claim.", 12.5, INK2),
    ]))

    rd = m.get("real_data")
    if rd:
        a = rd["by_group"]["all"]
        S.append(Slide("Real CGM traces: what transfers and what does not", "Validation", [
            Img(str(FIG / "real_data_cgmacros.png"), 0.6, 1.5, 12.1, 4.3),
            Text(0.9, 5.95, 11.6, f"CGMacros (PhysioNet, open access): {rd['participants']} adults, Dexcom G6, meals with known carbohydrate. "
                 f"Trained only on synthetic data, the hybrid lands near persistence ({a['120']['hyb']:.1f} against {a['120']['persist']:.1f} mg/dL at 2 h). "
                 f"Told about meals in advance, the calibrated twin reaches {a['120']['known']:.1f}. Interval coverage recovers from "
                 f"{rd['conformal']['120']['synthetic_calibration'] * 100:.0f}% to {rd['conformal']['120']['site_recalibrated'] * 100:.0f}% after per site recalibration.", 12.5, INK2),
        ]))

    S.append(Slide("What if: Ramesh, 52, night shift, T2D", "Case study", [
        Img(str(SHOTS / "03_whatif_ramesh.png"), 0.6, 1.45, 7.6, 4.86, border=True),
        Text(8.6, 1.6, 4.2, f"19:45. The hybrid forecast expects dinner at {cs['walk']['target_meal']['time']} and a peak near "
             f"{cs['peak']:.0f} mg/dL, after three nights of 4.9 h sleep.\n"
             f"A 15 minute walk after dinner takes {-cs['walk']['delta']['peak']:.0f} mg/dL off the twin's 6 hour peak. "
             f"Millets instead of white rice take {-cs['millet']['delta']['peak']:.0f}.\n"
             f"Together: peak {-cs['both']['delta']['peak']:.0f} mg/dL lower and {-cs['both']['delta']['tar_min']:.0f} minutes less above 180.\n"
             + early_text(cs["early"]) + "\n"
             f"Checked against the reference simulator the twin never sees: across {cf['cases']} moments in {cf['patients']} test patients "
             f"the twin gets the direction of a change right {cf['overall']['direction_agree'] * 100:.0f}% of the time.", 12, INK, bullets=True),
    ]))

    S.append(Slide("Clinical workflow", "Use", [
        Img(str(SHOTS / "01_ward.png"), 0.6, 1.45, 6.0, 3.84, border=True),
        Img(str(SHOTS / "25_phone_loop.png"), 6.85, 1.45, 5.9, 4.04, border=True),
        Text(0.6, 5.55, 6.0, "1. Ward grouped by urgency, with why each alert fired; n opens the next unseen alert. "
             f"Load measured: {load['high_per_patient_day']:.1f} confident high alerts per patient per day, {load['high_came_true'] * 100:.0f}% came true. "
             "2. The first action fits the alert: check now, call, book a review, try a change. Undo for 10 seconds.", 11.5, INK2),
        Text(6.85, 5.7, 5.9, "3. A suggestion to the patient's phone in Hindi, Tamil or English; the reply enters the forecast and the outcome "
             "comes back to both sides. 4. Every alert's outcome, week plans checked a week later, handover, festival planner.", 11.5, INK2),
    ]))

    S.append(Slide("Privacy, safety and limits", "Governance", [
        Text(0.9, 1.75, 5.6, "Synthetic data only: no personal data under the DPDP Act 2023 or HIPAA was used.\n"
             "Consent on screen: the patient can withdraw glucose, wearable or ABDM record sharing, and the service stops using that source.\n"
             "Roles checked by the service: doctor, nurse or health educator, patient. Every action and undo is audited.\n"
             "Deployment design: on premises inference, no identifiers in model features, clinic single sign on.\n"
             "Decision support only, not a diagnosis. The clinician decides.", 13.5, INK, bullets=True),
        Rule(7.0, 1.8, 5.5), Text(7.0, 1.95, 5.5, "Limitations we state openly", 14, INK, serif=True),
        Text(7.0, 2.5, 5.5, "Synthetic ground truth is still a model; real data will be harder.\n"
             f"Only {c['n_events']} cardiovascular events in test patients, from our own simulator; no real outcome validation yet.\n"
             "Conformal coverage is approximate with serially correlated readings, and lower below 70 mg/dL.\n"
             "Unlogged meals remain the main source of missed spikes.", 13, INK2, bullets=True),
    ]))

    S.append(Slide("Impact and roadmap", "Next", [
        Table(0.9, 1.8, [2.4, 9.2], [
            ["Now", "Working prototype: data, twin, models, API, dashboard, tests, docs. Reproducible from one seed."],
            ["3 months", "Retrospective validation on de-identified CGM and EHR data under an ethics approval; Indian food absorption library."],
            ["6 months", "Federated learning of the residual model across hospitals; the twin stays per patient, only model updates move."],
            ["9 months", "ABDM integration (health ID, consent manager, FHIR); real device APIs (Libre, Dexcom, Health Connect)."],
            ["12 months", "Prospective pilot in a diabetes clinic with alert burden and time in range as outcomes."],
        ], size=13, row_h=0.72),
        Text(0.9, 5.85, 11.5, "Impact: fewer hours above range, earlier review of cardiac drift, and conversations about change grounded in the patient's own physiology.", 14, INK, serif=True, italic=True),
        Text(0.9, 6.55, 11.5, "Code: <public repository URL>.  Demo video: <unlisted YouTube URL>.  Thank you.", 13, INK2),
    ]))

    return S


# Renderers ----------------------------------------------------------------------------------

def fit(path: str, w: float, h: float) -> tuple[float, float]:
    iw, ih = Image.open(path).size
    r = min(w / iw, h / ih)
    return iw * r, ih * r


def render_pdf(slides: list[Slide], path) -> None:
    style.use()
    with PdfPages(path) as pdf:
        for n, s in enumerate(slides, 1):
            fig = plt.figure(figsize=(SW, SH))
            fig.patch.set_facecolor(PAPER)
            ax = fig.add_axes([0, 0, 1, 1])
            ax.set_xlim(0, SW); ax.set_ylim(SH, 0); ax.axis("off")
            if s.title:
                if s.kicker:
                    ax.text(0.9, 0.62, s.kicker.upper(), fontsize=10, color=INK3, fontfamily=style.SANS, va="top")
                ax.text(0.9, 0.86, s.title, fontsize=26, color=INK, fontfamily=style.SERIF, va="top")
                ax.plot([0.9, SW - 0.6], [1.38, 1.38], color=RULE, lw=0.8)
                ax.text(SW - 0.6, SH - 0.32, f"Prativimb   {n}", fontsize=9, color=INK3, ha="right", fontfamily=style.SANS)
            for e in s.elements:
                if isinstance(e, Text):
                    lines = wrap(e)
                    lh = e.size / 72 * e.spacing
                    for i, line in enumerate(lines):
                        ax.text(e.x + (e.w if e.align == "right" else 0), e.y + i * lh, line, fontsize=e.size, color=e.color,
                                fontfamily=style.SERIF if e.serif else style.SANS, va="top", ha=e.align,
                                fontweight="semibold" if e.bold else "normal", fontstyle="italic" if e.italic else "normal")
                elif isinstance(e, Rule):
                    ax.plot([e.x, e.x + e.w], [e.y, e.y], color=e.color, lw=e.width)
                elif isinstance(e, Img):
                    w, h = fit(e.path, e.w, e.h)
                    ax.imshow(imread(e.path), extent=(e.x, e.x + w, e.y + h, e.y), zorder=1)
                    if e.border:
                        ax.add_patch(plt.Rectangle((e.x, e.y), w, h, fill=False, edgecolor=RULE, lw=0.8, zorder=2))
                elif isinstance(e, Table):
                    y = e.y
                    for ri, row in enumerate(e.rows):
                        x = e.x
                        head = ri == 0
                        cells = [wrap(Text(0, 0, cw - 0.15, str(v), e.size)) for v, cw in zip(row, e.widths)]
                        nl = max(len(cl) for cl in cells)
                        rh = max(e.row_h, nl * e.size / 72 * 1.3 + 0.12)
                        for v, cw, cl in zip(row, e.widths, cells):
                            for li, line in enumerate(cl):
                                ax.text(x, y + 0.08 + li * e.size / 72 * 1.3, line, fontsize=e.size - (1.5 if head else 0),
                                        color=INK3 if head else INK, va="top", fontfamily=style.SANS,
                                        fontweight="semibold" if (e.bold_last and ri == len(e.rows) - 1) else "normal")
                            x += cw
                        y += rh
                        ax.plot([e.x, e.x + sum(e.widths)], [y, y], color=INK3 if head else RULE, lw=0.8 if head else 0.6)
            ax.set_xlim(0, SW); ax.set_ylim(SH, 0)
            pdf.savefig(fig)
            plt.close(fig)


def render_pptx(slides: list[Slide], path) -> None:
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_CONNECTOR
    from pptx.util import Inches, Pt

    rgb = lambda h: RGBColor.from_string(h.lstrip("#").upper())
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(SW), Inches(SH)
    blank = prs.slide_layouts[6]

    def text(slide, x, y, w, lines, size, color, serif=False, bold=False, italic=False, spacing=1.35, align="left"):
        h = max(0.4, len(lines) * size / 72 * spacing + 0.1)
        tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = tb.text_frame
        tf.word_wrap = False
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
        for i, line in enumerate(lines):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.line_spacing = spacing
            if align == "right":
                from pptx.enum.text import PP_ALIGN
                p.alignment = PP_ALIGN.RIGHT
            r = p.add_run()
            r.text = line
            f = r.font
            f.size, f.bold, f.italic = Pt(size), bold, italic
            f.name = "IBM Plex Serif" if serif else "IBM Plex Sans"
            f.color.rgb = rgb(color)

    def rule(slide, x, y, w, color, width):
        ln = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x), Inches(y), Inches(x + w), Inches(y))
        ln.line.color.rgb = rgb(color)
        ln.line.width = Pt(width)

    for n, s in enumerate(slides, 1):
        sl = prs.slides.add_slide(blank)
        bg = sl.background.fill
        bg.solid()
        bg.fore_color.rgb = rgb(PAPER)
        if s.title:
            if s.kicker:
                text(sl, 0.9, 0.55, 8, [s.kicker.upper()], 10, INK3)
            text(sl, 0.9, 0.8, 11.5, [s.title], 26, INK, serif=True)
            rule(sl, 0.9, 1.38, SW - 1.5, RULE, 0.8)
            text(sl, SW - 2.6, SH - 0.42, 2.0, [f"Prativimb   {n}"], 9, INK3, align="right")
        for e in s.elements:
            if isinstance(e, Text):
                text(sl, e.x, e.y, e.w, wrap(e), e.size, e.color, e.serif, e.bold, e.italic, e.spacing, e.align)
            elif isinstance(e, Rule):
                rule(sl, e.x, e.y, e.w, e.color, e.width)
            elif isinstance(e, Img):
                w, h = fit(e.path, e.w, e.h)
                pic = sl.shapes.add_picture(e.path, Inches(e.x), Inches(e.y), Inches(w), Inches(h))
                if e.border:
                    pic.line.color.rgb = rgb(RULE)
                    pic.line.width = Pt(0.75)
            elif isinstance(e, Table):
                y = e.y
                for ri, row in enumerate(e.rows):
                    x = e.x
                    head = ri == 0
                    cells = [wrap(Text(0, 0, cw - 0.15, str(v), e.size)) for v, cw in zip(row, e.widths)]
                    nl = max(len(cl) for cl in cells)
                    rh = max(e.row_h, nl * e.size / 72 * 1.3 + 0.12)
                    for cl, cw in zip(cells, e.widths):
                        text(sl, x, y + 0.08, cw - 0.1, cl, e.size - (1.5 if head else 0), INK3 if head else INK,
                             bold=e.bold_last and ri == len(e.rows) - 1, spacing=1.3)
                        x += cw
                    y += rh
                    rule(sl, e.x, y, sum(e.widths), INK3 if head else RULE, 0.8 if head else 0.6)
        if s.notes:
            sl.notes_slide.notes_text_frame.text = s.notes
    prs.save(path)


def main() -> None:
    slides = spec(load_metrics(), case_study())
    render_pptx(slides, config.DOCS_DIR / "presentation.pptx")
    render_pdf(slides, config.DOCS_DIR / "presentation.pdf")
    print(f"wrote docs/presentation.pptx and docs/presentation.pdf ({len(slides)} slides)")


if __name__ == "__main__":
    main()
