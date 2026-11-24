"""Bygger rapportens diagram (SVG) från källdata i data/.

Kör:  python3 charts.py   (skriver till figures/)
"""
import csv
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
OUT = os.path.join(HERE, "figures")
os.makedirs(OUT, exist_ok=True)

# Validerad kategorisk palett (dataviz-referens, ljust läge) + neutral för "Hela landet".
C = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
NEUTRAL = "#3b3a37"
INK = "#0b0b0b"
INK2 = "#52514e"
GRID = "#e4e3df"
SURFACE = "#ffffff"
SEQ = ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#0d366b"]  # ordinal blå ramp

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 8.5,
    "axes.edgecolor": GRID,
    "axes.labelcolor": INK2,
    "xtick.color": INK2,
    "ytick.color": INK2,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.spines.left": False,
    "svg.fonttype": "none",
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
})

LANDSDELAR = ["Norra Norrland", "Södra Norrland", "Svealand", "Götaland"]


def read_wide(path):
    with open(path, encoding="utf-8") as f:
        rows = list(csv.reader(f))
    head = rows[0]
    periods = [h.replace(" Prel.", "*") for h in head[2:]]
    data = {}
    for r in rows[1:]:
        vals = [None if v in ("..", "") else float(v) for v in r[2:]]
        data[(r[0], r[1])] = vals
    return periods, data


def fmt_k(v, _=None):
    return f"{v:,.0f}".replace(",", " ")


def style_axes(ax, ylabel=None):
    ax.grid(axis="y", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.tick_params(axis="both", length=0, pad=4)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(fmt_k))
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=8)


def end_labels(ax, xs, series, min_gap):
    """Direktetiketter vid linjernas slut, med enkel kollisionshantering."""
    pts = []
    for name, ys, color in series:
        idx = max(i for i, v in enumerate(ys) if v is not None)
        pts.append([ys[idx], name, ys[idx], xs[idx]])
    pts.sort(key=lambda p: p[0])
    for i in range(1, len(pts)):
        if pts[i][0] - pts[i - 1][0] < min_gap:
            pts[i][0] = pts[i - 1][0] + min_gap
    for ypos, name, yval, x in pts:
        ax.annotate(f"{name} {fmt_k(yval)}", xy=(x, yval), xytext=(x + 0.35, ypos),
                    fontsize=7.5, color=INK, va="center", ha="left",
                    annotation_clip=False)


def line_chart(fname, periods, series, ylabel, break_at=None, min_gap=None,
               ylim=None, right_pad=3.6, height=2.9, ref=None):
    fig, ax = plt.subplots(figsize=(6.7, height))
    xs = list(range(len(periods)))
    for name, ys, color in series:
        lw = 2.4 if color == NEUTRAL else 1.6
        px = [x for x, y in zip(xs, ys) if y is not None]
        py = [y for y in ys if y is not None]
        ax.plot(px, py, color=color, linewidth=lw, solid_capstyle="round",
                solid_joinstyle="round", zorder=3)
        ax.scatter([px[-1]], [py[-1]], s=22, color=color, edgecolor=SURFACE,
                   linewidth=1.2, zorder=4)
    if ref:
        val, text = ref
        ax.axhline(val, color=INK2, linewidth=0.8, zorder=2)
        ax.annotate(text, xy=(0, val), xytext=(0.1, val), textcoords="data",
                    fontsize=7, color=INK2, va="top", ha="left",
                    bbox=dict(boxstyle="square,pad=0.15", fc=SURFACE, ec="none"))
    if break_at is not None and break_at in periods:
        bx = periods.index(break_at) - 0.5
        ax.axvline(bx, color=INK2, linewidth=0.8, zorder=1)
        ax.annotate("Metodbyte (ny insamling)", xy=(bx, 1), xycoords=("data", "axes fraction"),
                    xytext=(4, -2), textcoords="offset points", fontsize=7,
                    color=INK2, va="top")
    step = 1 if len(periods) <= 16 else 4
    ax.set_xticks(xs[::step])
    short = [p[2:] if len(p) >= 6 and p[:2] == "20" else p for p in periods]
    ax.set_xticklabels(short[::step], fontsize=7.5)
    ax.set_xlim(-0.4, len(periods) - 1 + right_pad)
    if ylim:
        ax.set_ylim(*ylim)
    style_axes(ax, ylabel)
    if min_gap is None:
        lo, hi = ax.get_ylim()
        min_gap = (hi - lo) * 0.065
    end_labels(ax, xs, series, min_gap)
    # Legend (alltid vid >= 2 serier)
    handles = [plt.Line2D([0], [0], color=c, lw=2.4 if c == NEUTRAL else 1.8) for _, _, c in series]
    ax.legend(handles, [n for n, _, _ in series], loc="lower left", bbox_to_anchor=(0, 1.02),
              ncol=len(series), frameon=False, fontsize=7.5, handlelength=1.6,
              columnspacing=1.2, borderaxespad=0)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, fname), format="svg")
    plt.close(fig)


def bars(fname, cats, groups, ylabel, colors, value_fmt="{:.1f}", ref=None, height=2.6,
         labels=True, legend=True, hatch_last=False, ylim=None):
    """Grupperade staplar. groups = [(namn, [värden per kategori])]."""
    fig, ax = plt.subplots(figsize=(6.7, height))
    n = len(groups)
    slot = 0.8 / n
    width = min(slot - 0.02, 0.36)
    for gi, (gname, vals) in enumerate(groups):
        for ci, v in enumerate(vals):
            if v is None:
                continue
            x = ci - 0.4 + slot * (gi + 0.5)
            hatch = "////" if (hatch_last and ci == len(vals) - 1) else None
            ax.bar(x, v, width=width, color=colors[gi] if n > 1 else colors[ci],
                   edgecolor=SURFACE if not hatch else "white", linewidth=0.8, hatch=hatch,
                   zorder=3, label=gname if ci == 0 else None)
            if labels:
                ax.annotate(value_fmt.format(v).replace(".", ","), xy=(x, v), xytext=(0, 2),
                            textcoords="offset points", ha="center", va="bottom",
                            fontsize=6.8 if n > 2 else 7.5, color=INK)
    if ref:
        val, text = ref
        ax.axhline(val, color=INK2, linewidth=0.8, zorder=4)
        ax.annotate(text, xy=(len(cats) - 0.5, val), xytext=(0, 3), textcoords="offset points",
                    ha="right", fontsize=7, color=INK2)
    ax.set_xticks(range(len(cats)))
    ax.set_xticklabels(cats, fontsize=7.5)
    style_axes(ax, ylabel)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:g}".replace(".", ",")))
    if ylim:
        ax.set_ylim(*ylim)
    if legend and n > 1:
        ax.legend(loc="lower left", bbox_to_anchor=(0, 1.02), ncol=n, frameon=False,
                  fontsize=7.5, borderaxespad=0, handlelength=1.2)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, fname), format="svg")
    plt.close(fig)


def dumbbell(fname, rows, labels_t, colors, xlabel, height=None, xlim=None, pct_from=0):
    """rows = [(etikett, [v_t0, v_t1, ...])]; punkter för varje tidpunkt, linje mellan första och sista."""
    height = height or 0.28 * len(rows) + 0.9
    fig, ax = plt.subplots(figsize=(6.7, height))
    for i, (lab, vals) in enumerate(rows):
        y = len(rows) - 1 - i
        valid = [v for v in vals if v is not None]
        ax.plot([min(valid), max(valid)], [y, y], color=GRID, linewidth=2.2, zorder=1,
                solid_capstyle="round")
        for ti, v in enumerate(vals):
            if v is None:
                continue
            ax.scatter(v, y, s=30, color=colors[ti], edgecolor=SURFACE, linewidth=1.2, zorder=3)
        last = vals[-1]
        first = vals[pct_from]
        if last is not None and first is not None:
            pct = (last / first - 1) * 100
            ax.annotate(f"{pct:+.0f} %".replace("-", "−"), xy=(max(valid), y), xytext=(6, 0),
                        textcoords="offset points", va="center", fontsize=7, color=INK2)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([r[0] for r in rows][::-1], fontsize=7.3)
    ax.grid(axis="x", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)
    ax.spines["bottom"].set_visible(False)
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(fmt_k))
    ax.set_xlabel(xlabel, fontsize=8)
    if xlim:
        ax.set_xlim(*xlim)
    handles = [plt.Line2D([0], [0], marker="o", color="none", markerfacecolor=c, markersize=6)
               for c in colors]
    ax.legend(handles, labels_t, loc="lower left", bbox_to_anchor=(0, 1.0), ncol=len(labels_t),
              frameon=False, fontsize=7.5, borderaxespad=0, handletextpad=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, fname), format="svg")
    plt.close(fig)


def main():
    # --- Leveransvirke per landsdel (Skogsstyrelsen) ---
    per, lev = read_wide(os.path.join(DATA, "skogsstyrelsen_leveransvirke_kvartal.csv"))

    def regional(sort):
        s = [(ld, lev[(ld, sort)], C[i]) for i, ld in enumerate(LANDSDELAR)]
        s.append(("Hela landet", lev[("Hela landet", sort)], NEUTRAL))
        return s

    line_chart("fig01_tall_leverans.svg", per, regional("Tallsågtimmer"), "kr/m³fub",
               break_at="2025K1")
    line_chart("fig02_gran_leverans.svg", per, regional("Gransågtimmer"), "kr/m³fub",
               break_at="2025K1")
    line_chart("fig04_massa_leverans.svg", per, regional("Massaved totalt"), "kr/m³fub",
               break_at="2025K1")
    line_chart("fig05_massa_barr_lov.svg", per,
               [("Barrmassaved", lev[("Hela landet", "Massaved av barrträd")], C[0]),
                ("Lövmassaved", lev[("Hela landet", "Massaved av lövträd")], C[1])],
               "kr/m³fub", break_at="2025K1", height=2.5)

    # --- Avverkningsuppdrag, hela landet ---
    per_a, avv = read_wide(os.path.join(DATA, "skogsstyrelsen_avverkningsuppdrag_kvartal.csv"))
    line_chart("fig03_avverkningsuppdrag.svg", per_a,
               [("Gransågtimmer", avv[("Hela landet", "Gransågtimmer")], C[0]),
                ("Tallsågtimmer", avv[("Hela landet", "Tallsågtimmer")], C[1]),
                ("Barrmassaved", avv[("Hela landet", "Massaved av barrträd")], C[2]),
                ("Bränsleved", avv[("Hela landet", "Bränsleved")], C[3])],
               "kr/m³fub", right_pad=2.2, height=2.7, ylim=(300, 1300))

    # --- Trädbränslen (Energimyndigheten) ---
    with open(os.path.join(DATA, "energimyndigheten_tradbransle_kvartal.csv"), encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    q = [r["Kvartal"] for r in rows]
    qlab = [k.replace("Q", "K") for k in q]

    def col(name):
        return [float(r[name]) if r[name] else None for r in rows]

    line_chart("fig06_tradbransle.svg", qlab,
               [("Förädlade, värmeverk", col("Förädlade|Värmeverk"), C[0]),
                ("Skogsflis, värmeverk", col("Skogsflis|Värmeverk"), C[1]),
                ("Skogsflis, industri", col("Skogsflis|Industri"), C[2]),
                ("Biprodukter, värmeverk", col("Biprodukter|Värmeverk"), C[3])],
               "kr/MWh", right_pad=9, height=3.0,
               ref=(220, "Skogsflis värmeverk, snitt 2019–2023: 220 kr/MWh"))

    # Skogsflis per region (värmeverk), 2025K1–2026K2
    regq = ["2025K1", "2025K2", "2025K3", "2025K4", "2026K1", "2026K2"]
    flis = {"Region 1 (norr)": [332, 342, 329, 322, 330, 323],
            "Region 2 (mitt)": [377, 379, 355, 355, 360, 368],
            "Region 3 (syd)": [399, 406, 388, 378, 380, 371]}
    line_chart("fig07_flis_region.svg", regq,
               [(k, v, C[i]) for i, (k, v) in enumerate(flis.items())],
               "kr/MWh", right_pad=1.9, height=2.4, ylim=(300, 420))

    # --- Volymer ---
    years = ["2019", "2020", "2021", "2022", "2023", "2024", "2025", "2026p"]
    brutto = [92.8, 93.1, 96.6, 95.0, 88.9, 87.7, 87.0, 84.6]
    bars("fig08_bruttoavverkning.svg", years, [("Bruttoavverkning", brutto)], "milj. m³sk",
         [C[0]] * 7 + ["#86b6ef"], ref=(93.3, "Snitt 2019–2023: 93,3"), hatch_last=True,
         ylim=(0, 105))

    imp_years = ["2019", "2020", "2021", "2022", "2023", "2024", "2025"]
    bars("fig09_import.svg", imp_years,
         [("Biometria (milj. m³fub, till industrin)", [8.6, 6.7, 6.2, 6.3, 6.8, 8.6, 7.7]),
          ("SCB (milj. m³f, inkl. bränsleved)", [8.8, 7.2, 6.3, 6.5, 7.3, 9.2, 8.4])],
         "miljoner m³", [C[0], C[1]], ylim=(0, 10.5))

    cons = {  # Biometria, industriell förbrukning milj. m³fub, 2021–2025
        "Norra Norrland": [10.3, 9.8, 9.6, 9.5, 9.8],
        "Södra Norrland": [17.8, 17.4, 16.4, 17.2, 16.9],
        "Svealand": [23.2, 22.4, 21.1, 21.1, 20.1],
        "Götaland": [25.7, 25.6, 25.0, 25.1, 24.4],
    }
    yrs = ["2021", "2022", "2023", "2024", "2025"]
    bars("fig10_forbrukning_landsdel.svg", list(cons.keys()),
         [(y, [cons[k][i] for k in cons]) for i, y in enumerate(yrs)],
         "milj. m³fub", SEQ, height=2.7, ylim=(0, 29))

    # --- Köparnas prislistor (Skogen, jämförpriser slutavverkning, avverkningsuppdrag) ---
    gran_rows = [
        ("Södra (Götaland)", [964, 1170, 934]),
        ("Stora Enso Västra Götaland", [920, 1118, 881]),
        ("Holmen Östergötland/Småland", [860, 1044, 785]),
        ("Mellanskog Uppland–Södermanland", [792, 925, 782]),
        ("Mellanskog Värmland/Örebro", [790, 922, 780]),
        ("Holmen Söderm./Västm./Närke/Värml.", [742, 791, 709]),
        ("Stora Enso Uppland/Västmanland", [722, 797, 691]),
        ("Holmen Dalarna", [756, 811, 618]),
        ("Holmen S Västernorrland", [594, 705, 665]),
        ("SCA Västernorrland (kust)", [589, 706, 649]),
        ("Norra Skog Västerbotten kust", [483, 483, 489]),
    ]
    dumbbell("fig11_prislistor_gran.svg", gran_rows, ["okt 2024", "sep 2025", "aug 2026"],
             [C[0], C[1], C[2]], "kr/m³fub, gran, medelpris i slutavverkning (avverkningsuppdrag)",
             xlim=(420, 1240), pct_from=1)

    massa_rows = [  # barrmassaved prima, kr/m³fub, 7 jan 2026 -> 10 aug 2026
        ("Södra (Götaland)", [560, 480]),
        ("Holmen Östergötland/Småland", [550, 475]),
        ("Stora Enso Bohuslän/Dalsland", [560, 480]),
        ("Mellanskog Uppland/Västm./Söderm.", [560, 460]),
        ("Sveaskog Dalarna", [560, 460]),
        ("Billerud Uppsala/Sthlm/Västm.", [460, 420]),
        ("Holmen Dalarna", [480, 350]),
        ("Stora Enso Dalarna", [465, 410]),
        ("Sveaskog Norrbotten/Västerbotten", [560, 460]),
        ("SCA Västerbotten/Norrbotten", [450, 400]),
        ("Norra Skog Norrland", [400, 410]),
        ("Billerud Norrbotten/Västerbotten", [485, 400]),
    ]
    dumbbell("fig12_prislistor_massa.svg", massa_rows, ["jan 2026", "aug 2026"],
             [C[0], C[1]], "kr/m³fub, barrmassaved (prima), listpris vid bilväg",
             xlim=(320, 600))


if __name__ == "__main__":
    main()
