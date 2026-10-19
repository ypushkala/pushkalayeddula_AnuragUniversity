"""House style for every static chart (reports and slides): paper, ink, one teal accent,
greys for comparison series, red only for alerts. Thin marks, hairline solid grid, direct labels."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

from prativimb import config

PAPER = "#F7F5F0"
PAPER_2 = "#EFECE5"
RULE = "#D8D3C8"
INK = "#1B1B19"
INK_2 = "#4A4843"
INK_3 = "#6A675F"
ACCENT = "#17635E"
GREY = "#9C988F"
GREY_DARK = "#6E6B64"
ALERT = "#B42318"

FONT_DIR = config.ROOT / "assets" / "fonts"
SANS, SERIF = "IBM Plex Sans", "IBM Plex Serif"


def use() -> None:
    for f in Path(FONT_DIR).glob("*.ttf"):
        font_manager.fontManager.addfont(str(f))
    plt.rcParams.update({
        "figure.facecolor": PAPER, "axes.facecolor": PAPER, "savefig.facecolor": PAPER,
        "font.family": SANS, "font.size": 9.5, "text.color": INK,
        "axes.edgecolor": RULE, "axes.linewidth": 0.8, "axes.labelcolor": INK_2, "axes.labelsize": 9,
        "axes.titlesize": 11, "axes.titleweight": "medium", "axes.titlelocation": "left", "axes.titlepad": 10,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.color": RULE, "grid.linewidth": 0.6, "grid.linestyle": "-",
        "xtick.color": INK_3, "ytick.color": INK_3, "xtick.labelsize": 8.5, "ytick.labelsize": 8.5,
        "xtick.major.size": 0, "ytick.major.size": 0, "xtick.major.pad": 5, "ytick.major.pad": 5,
        "lines.linewidth": 2.0, "lines.solid_capstyle": "round", "lines.solid_joinstyle": "round",
        "legend.frameon": False, "legend.fontsize": 8.5,
        "figure.dpi": 110, "savefig.dpi": 200, "savefig.bbox": "tight", "savefig.pad_inches": 0.15,
    })


def title(ax, text: str, sub: str | None = None) -> None:
    ax.set_title(text, fontfamily=SERIF, fontsize=12, color=INK, loc="left", pad=22 if sub else 10)
    if sub:
        ax.text(0, 1.02, sub, transform=ax.transAxes, fontsize=8.5, color=INK_3, va="bottom")


def save(fig, name: str) -> Path:
    config.FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    path = config.FIGURE_DIR / f"{name}.png"
    fig.savefig(path)
    plt.close(fig)
    return path
