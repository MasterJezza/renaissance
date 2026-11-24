"""Genererar bilagetabeller (Markdown) och nyckeltal ur källdata i data/.

Kör: python3 tables.py  -> skriver bilaga_tabeller.md och skriver nyckeltal till stdout.
"""
import csv
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")


def read_wide(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        rows = list(csv.reader(f))
    periods = [h.replace(" Prel.", "*") for h in rows[0][2:]]
    data = {(r[0], r[1]): [None if v in ("..", "") else float(v) for v in r[2:]] for r in rows[1:]}
    return periods, data


def n(v, dec=0):
    if v is None:
        return "–"
    s = f"{v:,.{dec}f}".replace(",", " ").replace(".", ",")
    return s


def pct(a, b):
    if a is None or b is None:
        return "–"
    p = (a / b - 1) * 100
    return f"{p:+.0f} %".replace("-", "−")


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


LD = ["Norra Norrland", "Södra Norrland", "Svealand", "Götaland", "Hela landet"]
KPI = {"2019": 334.26, "2020": 335.92, "2021": 343.19, "2022": 371.91, "2023": 403.70,
       "2024": 415.15, "2025": 417.98}


def table(head, rows, align=None):
    out = ["| " + " | ".join(head) + " |",
           "|" + "|".join(align or ["---"] + ["---:"] * (len(head) - 1)) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out)


def main():
    md = []
    per, lev = read_wide("skogsstyrelsen_leveransvirke_kvartal.csv")
    per_a, avv = read_wide("skogsstyrelsen_avverkningsuppdrag_kvartal.csv")
    _, ar = read_wide("skogsstyrelsen_leveransvirke_ar_2019-2021.csv")

    # B1: leveransvirke kvartal per landsdel och sortiment
    md.append("### Tabell A1. Avräkningspriser för leveransvirke per landsdel och kvartal, 2023K3–2026K3\n")
    md.append("*Enhet: kr/m³fub, löpande priser, vid bilväg. Metodbyte från 2025K1. 2026K3 preliminärt (\\*). "
              "”–” = uppgift saknas eller för osäker. Källa: Skogsstyrelsen, tabell JO0303_3ny (hämtad 24 nov 2026).*\n")
    sorts = ["Tallsågtimmer", "Gransågtimmer", "Massaved av barrträd", "Massaved av lövträd", "Massaved totalt"]
    head = ["Landsdel / sortiment"] + [p[2:] for p in per]
    rows = []
    for ld in LD:
        for s in sorts:
            vals = lev.get((ld, s))
            if vals is None or all(v is None for v in vals):
                continue
            rows.append([f"{ld}: {s}"] + [n(v) for v in vals])
    md.append(table(head, rows))

    # B2: avverkningsuppdrag
    md.append("\n\n### Tabell A2. Avräkningspriser för avverkningsuppdrag per landsdel och kvartal, 2025K1–2026K3\n")
    md.append("*Enhet: kr/m³fub, löpande priser, vid bilväg. 2026K3 preliminärt (\\*). Källa: Skogsstyrelsen, tabell JO030304a.*\n")
    rows = []
    for ld in LD:
        for s in sorts + ["Bränsleved"]:
            vals = avv.get((ld, s))
            if vals is None or all(v is None for v in vals):
                continue
            rows.append([f"{ld}: {s}"] + [n(v) for v in vals])
    md.append(table(["Landsdel / sortiment"] + [p[2:] for p in per_a], rows))

    # B3: årsmedel och referens
    md.append("\n\n### Tabell A3. Årsnivåer för leveransvirke, hela landet, och jämförelse med referensperioden 2019–2023\n")
    md.append("*Enhet: kr/m³fub, löpande priser. F = officiellt utfall, H = härlett (se metodavsnitt), K = enkelt medel av kvartal. "
              "Real förändring beräknad med KPI (SCB, 1980=100, årsmedel).*\n")
    st = {"2019": ar[("Hela landet", "Sågtimmer")][0], "2020": ar[("Hela landet", "Sågtimmer")][1],
          "2021": ar[("Hela landet", "Sågtimmer")][2]}
    ma = {"2019": ar[("Hela landet", "Massaved")][0], "2020": ar[("Hela landet", "Massaved")][1],
          "2021": ar[("Hela landet", "Massaved")][2]}
    st["2022"] = st["2021"] * 1.14
    ma["2022"] = ma["2021"] * 1.19
    i24 = [per.index(p) for p in ("2024K1", "2024K2", "2024K3", "2024K4")]
    st24 = mean([lev[("Hela landet", "Sågtimmer")][i] for i in i24])
    ma24 = mean([lev[("Hela landet", "Massaved totalt")][i] for i in i24])
    st["2023"] = st24 / 1.30
    ma["2023"] = ma24 / 1.18
    ref_st = mean([st[y] for y in ("2019", "2020", "2021", "2022", "2023")])
    ref_ma = mean([ma[y] for y in ("2019", "2020", "2021", "2022", "2023")])
    kpi_ref = mean([KPI[y] for y in ("2019", "2020", "2021", "2022", "2023")])
    i25 = [per.index(p) for p in ("2025K1", "2025K2", "2025K3", "2025K4")]
    i26 = [per.index(p) for p in ("2026K1", "2026K2", "2026K3*")]
    st25 = mean([lev[("Hela landet", "Sågtimmer")][i] for i in i25])
    ma25 = mean([lev[("Hela landet", "Massaved totalt")][i] for i in i25])
    st26 = mean([lev[("Hela landet", "Sågtimmer")][i] for i in i26])
    ma26 = mean([lev[("Hela landet", "Massaved totalt")][i] for i in i26])
    rows = []
    for y, flag in (("2019", "F"), ("2020", "F"), ("2021", "F"), ("2022", "H"), ("2023", "H")):
        rows.append([y, flag, n(st[y]), n(ma[y])])
    rows.append(["**Snitt 2019–2023**", "H", f"**{n(ref_st)}**", f"**{n(ref_ma)}**"])
    rows.append(["2024", "K", n(st24), n(ma24)])
    rows.append(["2025 (nytt insamlingssätt)", "K", n(st25), n(ma25)])
    rows.append(["2026 K1–K3", "K", n(st26), n(ma26)])
    rows.append(["Nominell förändring 2025 mot snitt", "", pct(st25, ref_st), pct(ma25, ref_ma)])
    rows.append(["Real förändring 2025 mot snitt (KPI)", "",
                 pct(st25 / KPI["2025"], ref_st / kpi_ref), pct(ma25 / KPI["2025"], ref_ma / kpi_ref)])
    rows.append(["Nominell förändring 2026 K1–K3 mot 2025", "", pct(st26, st25), pct(ma26, ma25)])
    md.append(table(["År", "Typ", "Sågtimmer", "Massaved"], rows, ["---", "---", "---:", "---:"]))

    # B4: regional jämförelse 2019–2021 snitt (gammal serie) mot 2025 och 2026K3
    md.append("\n\n### Tabell A4. Leveransvirke per landsdel: snitt 2019–2021, 2025 (medel av kvartal) och 2026K3\n")
    md.append("*Enhet: kr/m³fub, löpande priser. Snitt 2019–2021 enligt gammal metod (prislistebaserad); 2025–2026 enligt ny metod. "
              "Tolka förändringar med försiktighet. Källa: Skogsstyrelsen, egna beräkningar.*\n")
    rows = []
    for ld in LD:
        for s_old, s_new, label in (("Tallsågtimmer", "Tallsågtimmer", "Tallsågtimmer"),
                                    ("Gransågtimmer", "Gransågtimmer", "Gransågtimmer"),
                                    ("Massaved", "Massaved totalt", "Massaved")):
            old = mean(ar[(ld, s_old)])
            v25 = mean([lev[(ld, s_new)][i] for i in i25])
            k3 = lev[(ld, s_new)][per.index("2026K3*")]
            rows.append([f"{ld}: {label}", n(old), n(v25), n(k3), pct(k3, v25)])
    md.append(table(["Landsdel / sortiment", "Snitt 2019–21", "2025", "2026K3*", "2026K3 mot 2025"], rows))

    # B5: trädbränsle
    with open(os.path.join(DATA, "energimyndigheten_tradbransle_kvartal.csv"), encoding="utf-8") as f:
        erows = list(csv.DictReader(f))
    md.append("\n\n### Tabell A5. Trädbränslepriser per kvartal, 2024K1–2026K2\n")
    md.append("*Enhet: kr/MWh fritt förbrukare, exkl. skatt, löpande priser. Källa: Energimyndigheten, EN0307, tabell 1 (uppdaterad 30 okt 2026).*\n")
    cols = ["Förädlade|Värmeverk", "Skogsflis|Värmeverk", "Skogsflis|Industri", "Biprodukter|Värmeverk",
            "Biprodukter|Industri", "Returträ|Värmeverk"]
    rows = [[r["Kvartal"].replace("Q", "K")] + [r[c] or "–" for c in cols] for r in erows if r["Kvartal"] >= "2024"]
    md.append(table(["Kvartal", "Förädlade, värmev.", "Skogsflis, värmev.", "Skogsflis, industri",
                     "Biprod., värmev.", "Biprod., industri", "Returträ, värmev."], rows))

    md.append("\n\n### Tabell A6. Trädbränslepriser, årsmedel, och referens 2019–2023\n")
    md.append("*Enhet: kr/MWh, löpande priser. Källa: Energimyndigheten, EN0307, tabell 2 (år) och tabell 1 (kvartal 2026).*\n")
    annual = {"Förädlade, värmeverk": [294, 311, 319, 353, 475, 567, 497],
              "Skogsflis, värmeverk": [199, 201, 195, 208, 298, 366, 376],
              "Skogsflis, industri": [187, 186, 183, 189, 236, 324, 339],
              "Biprodukter, värmeverk": [168, 172, 165, 171, 233, 317, 320]}
    h126 = {"Förädlade, värmeverk": (441 + 447) / 2, "Skogsflis, värmeverk": (367 + 366) / 2,
            "Skogsflis, industri": (328 + 323) / 2, "Biprodukter, värmeverk": (303 + 289) / 2}
    rows = []
    for k, v in annual.items():
        ref = mean(v[:5])
        rows.append([k, n(ref), n(v[5]), n(v[6]), n(h126[k]), pct(v[6], ref), pct(v[6], v[5]), pct(h126[k], v[6])])
    md.append(table(["Sortiment", "Snitt 2019–23", "2024", "2025", "2026 H1", "2025 mot snitt",
                     "2025 mot 2024", "2026 H1 mot 2025"], rows))

    md.append("\n\n### Tabell A7. Volymer: bruttoavverkning, import och industrins förbrukning\n")
    md.append("*Källor: Skogsstyrelsen (bruttoavverkning, milj. m³sk; 2021 preliminär i senast läsbara publikation, 2025 preliminär, 2026 prognos); "
              "Biometria (import och förbrukning, milj. m³fub); SCB via Biometria (import, milj. m³f).*\n")
    rows = [
        ["Bruttoavverkning (milj. m³sk)", "92,8", "93,1", "96,6", "95,0", "88,9", "87,7", "87,0", "84,6 (prognos)"],
        ["Import rundvirke, Biometria (milj. m³fub)", "8,6", "6,7", "6,2", "6,3", "6,8", "8,6", "7,7", "–"],
        ["Import rundvirke, SCB (milj. m³f)", "8,8", "7,2", "6,3", "6,5", "7,3", "9,2", "8,4", "–"],
        ["Industrins förbrukning, totalt (milj. m³fub)", "–", "–", "77,0", "75,2", "72,1", "72,9", "71,2", "–"],
        ["– varav massabruk", "–", "–", "37,5", "36,9", "36,5", "37,2", "35,6", "–"],
        ["– varav sågverk/trämek.", "–", "–", "39,5", "38,3", "35,6", "35,7", "35,6", "–"],
        ["Förbrukning av svenskt ursprung", "–", "–", "70,8", "68,9", "65,3", "64,2", "63,5", "–"],
    ]
    md.append(table(["Serie", "2019", "2020", "2021", "2022", "2023", "2024", "2025", "2026"], rows))

    with open(os.path.join(HERE, "bilaga_tabeller.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")

    print("ref_st", round(ref_st), "ref_ma", round(ref_ma), "st22", round(st["2022"]), "st23", round(st["2023"]),
          "ma22", round(ma["2022"]), "ma23", round(ma["2023"]))
    print("st24", round(st24), "ma24", round(ma24), "st25", round(st25), "ma25", round(ma25),
          "st26", round(st26), "ma26", round(ma26))
    print("real st25 vs ref", pct(st25 / KPI["2025"], ref_st / kpi_ref), "nom", pct(st25, ref_st))
    print("real ma25 vs ref", pct(ma25 / KPI["2025"], ref_ma / kpi_ref), "nom", pct(ma25, ref_ma))
    for s in ("Tallsågtimmer", "Gransågtimmer", "Massaved av barrträd", "Massaved av lövträd"):
        v = lev[("Hela landet", s)]
        peak = max(x for x in v if x)
        print(s, "peak", peak, per[v.index(peak)], "K3", v[-1], pct(v[-1], peak), "2025q", round(mean([v[i] for i in i25])),
              "26ytd", round(mean([v[i] for i in i26])))
    for ld in LD:
        v = lev[(ld, "Tallsågtimmer")]; g = lev[(ld, "Gransågtimmer")]
        print(ld, "tall K3 vs K3 25", pct(v[-1], v[per.index("2025K3")]), "gran", pct(g[-1], g[per.index("2025K3")]))


if __name__ == "__main__":
    main()
