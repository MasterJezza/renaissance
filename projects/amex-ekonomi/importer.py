#!/usr/bin/env python3
"""Förbereder import av Amex-transaktioner till kalkylbladet Ekonomi.

Tre steg, alla utan nätverk (kalkylbladet läses och skrivs av Claude via
Google Sheets-anslutningen; det här skriptet räknar bara):

  parse  EXPORT.xlsx [...] --out export.json
      Läser Amex Excel-export(er), mappar efter rubriknamn och behåller bara
      bokförda poster med Referens.

  plan   --export export.json --grid grid.json --out plan.json
      Jämför mot befintliga referenser, tar fram nya rader (stigande datum),
      förutspår kategori som bladets formel gör, och föreslår ansvarig och
      Finansiering utifrån historiken för samma köpställe.
      grid.json är svaret från get_spreadsheet med includeGridData för
      'AMEX Kvitton'!A1:T3000 och Index!A1:E1000 (värden + formler + revisionId).

  month  --summering summering.json --out month.json
      Avgör om Summering ska få en ny månadskolumn (högst en per månad) och
      bygger i så fall begäran, inklusive förlängda diagramkällor.

  build  --plan plan.json --out requests.json
      Validerar planen (efter att Claude granskat ansvarig/kategori) och
      bygger EN atomär spreadsheets.batchUpdate: format + datavalidering
      kopieras från närmaste kompletta rad, värden och hjälpformler skrivs
      uttryckligen per rad, och saknade köpställen läggs till i Index.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import re
import sys
from pathlib import Path

SPREADSHEET_ID = "1FQU_otIfWm6tgyC1pfqfp_vFxiEuWdv974jul1UA0As"
KVITTON_SHEET_ID = 0
INDEX_SHEET_ID = 1864865624
RESPONSIBLE = {"C G WEITZE", "HILDA GUSTAFSSON", "GEMENSAMT"}
PAYMENT_TEXT = "BETALNING MOTTAGEN, TACK"
PAYMENT_CATEGORY = "Fakturabetalning"

# Kolumner som kommer från exporten, i bladets rubrikordning.
IMPORT_HEADERS = [
    "Datum", "Beskrivning", "Kortmedlem", "Konto #", "Belopp",
    "Utökade specifikationer", "Visas på ditt kontoutdrag som", "Adress",
    "Ort", "Postnummer", "Land", "Referens",
]

# Standardformler om ingen mallrad skickas in. {r} = radnummer.
DEFAULT_FORMULAS = {
    "C": '=IFERROR(INDEX(Index!$C$3:$C,MATCH(E{r},Index!$B$3:$B,0)),IFERROR(INDEX(Index!$C$3:$C,MATCH(TRUE,ARRAYFORMULA(ISNUMBER(SEARCH(Index!$B$3:$B,E{r}))),0)),""))',
    "P": '=SUBSTITUTE(K{r}, CHAR(10), " ")',
    "Q": "=COUNTIFS($D$4:$D, D{r}, $E$4:$E, E{r}, $H$4:$H, H{r}) > 1",
    "R": "=WEEKDAY(D{r})",
    "S": "=EOMONTH(D{r},0)",
    "T": '=SWITCH(F{r},"C G WEITZE","CW","HILDA GUSTAFSSON","HG","GEMENSAMT","G")',
}


def col_letter(i: int) -> str:
    s = ""
    i += 1
    while i:
        i, rem = divmod(i - 1, 26)
        s = chr(65 + rem) + s
    return s


def col_index(letter: str) -> int:
    n = 0
    for ch in letter:
        n = n * 26 + ord(ch) - 64
    return n - 1


def norm(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().upper()


def clean_ref(s) -> str:
    return str(s or "").strip().lstrip("'").strip()


def parse_date(v) -> dt.date | None:
    if v is None or v == "":
        return None
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    if isinstance(v, (int, float)):
        return dt.date(1899, 12, 30) + dt.timedelta(days=int(v))
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y", "%m/%d/%Y", "%d-%m-%Y"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def parse_amount(v) -> float | None:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace(" ", " ").replace("kr", "").replace("SEK", "").strip()
    s = s.replace(" ", "")
    if "," in s and "." in s:
        # Den sista separatorn är decimaltecknet.
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def serial(d: dt.date) -> int:
    return (d - dt.date(1899, 12, 30)).days


# ------------------------------------------------------------------ parse

def cmd_parse(args):
    import openpyxl

    out = []
    for f in args.files:
        wb = openpyxl.load_workbook(f, data_only=True, read_only=True)
        found = False
        for ws in wb.worksheets:
            rows = list(ws.iter_rows(values_only=True))
            hdr_i = next(
                (i for i, r in enumerate(rows)
                 if r and "Referens" in [str(c).strip() if c is not None else "" for c in r]
                 and "Datum" in [str(c).strip() if c is not None else "" for c in r]),
                None,
            )
            if hdr_i is None:
                continue
            found = True
            hdr = [str(c).strip() if c is not None else "" for c in rows[hdr_i]]
            missing = [h for h in ("Datum", "Beskrivning", "Belopp", "Referens") if h not in hdr]
            if missing:
                sys.exit(f"{f}: saknar obligatoriska kolumner {missing}")
            for order, r in enumerate(rows[hdr_i + 1:]):
                if not r or all(c in (None, "") for c in r):
                    continue
                rec = {h: r[i] for i, h in enumerate(hdr) if h and i < len(r)}
                ref = clean_ref(rec.get("Referens"))
                joined = " ".join(str(v) for v in rec.values() if v is not None).lower()
                if not ref or "pågående" in joined or "pending" in joined:
                    continue  # pågående poster tas aldrig med
                d = parse_date(rec.get("Datum"))
                amt = parse_amount(rec.get("Belopp"))
                if d is None or amt is None:
                    sys.exit(f"{f}: kan inte tolka datum/belopp för referens {ref}")
                item = {h: ("" if rec.get(h) is None else str(rec.get(h)).strip()) for h in IMPORT_HEADERS if h in rec}
                item["Referens"] = ref
                item["_date"] = d.isoformat()
                item["_amount"] = amt
                item["_source"] = Path(f).name
                item["_order"] = order
                out.append(item)
        if not found:
            sys.exit(f"{f}: hittar ingen rubrikrad med Datum och Referens")
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1))
    dates = sorted(x["_date"] for x in out)
    print(json.dumps({"rows": len(out), "from": dates[0] if dates else None, "to": dates[-1] if dates else None}, ensure_ascii=False))


# ------------------------------------------------------------------- plan

def _load_json(path):
    data = json.loads(Path(path).read_text())
    if isinstance(data, list) and data and isinstance(data[0], dict) and "text" in data[0]:
        data = json.loads(data[0]["text"])  # MCP-svar sparat som innehållslista
    return data


def load_grid(path) -> tuple[dict, str | None]:
    """Läser svaret från get_spreadsheet(includeGridData) och returnerar
    {fliknamn: [[(visat värde, userEnteredValue-dict), ...], ...]} (rad 1 = index 0)."""
    data = _load_json(path)
    out = {}
    for sh in data.get("sheets", []):
        title = sh["properties"]["title"]
        grid = []
        for block in sh.get("data", []):
            start = block.get("startRow", 0)
            while len(grid) < start:
                grid.append([])
            for rd in block.get("rowData", []):
                grid.append([(c.get("formattedValue", ""), c.get("userEnteredValue", {})) for c in rd.get("values", [])])
        out[title] = grid
    return out, data.get("revisionId")


def shown(grid_rows):
    return [[c[0] for c in r] for r in grid_rows]


def _search_regex(pat: str):
    """Google Sheets SEARCH: skiftlägesokänslig, * ? är jokertecken, ~ skyddar."""
    out, i = "", 0
    while i < len(pat):
        ch = pat[i]
        if ch == "~" and i + 1 < len(pat):
            out += re.escape(pat[i + 1]); i += 2; continue
        out += ".*" if ch == "*" else "." if ch == "?" else re.escape(ch)
        i += 1
    return re.compile(out, re.IGNORECASE | re.DOTALL)


def index_match(desc: str, index: list[tuple[str, str]]) -> str:
    """Speglar bladets formel i kolumn C:
    1) MATCH(E, Index!B, 0): exakt (skiftlägesokänslig) träff, blanksteg räknas.
    2) annars första rad i Index!B där SEARCH(mönster, E) träffar. En tom rad
       träffar alltid (SEARCH("") = 1) och ger då tom kategori, så poster som
       ligger efter ett glapp i Index nås bara via exakt träff.
    """
    d = str(desc)
    for pat, cat in index:
        if pat and pat.upper() == d.upper():
            return cat
    for pat, cat in index:
        if not pat:
            return ""
        if _search_regex(pat).search(d):
            return cat
    return ""


def cmd_plan(args):
    grid, revision = load_grid(args.grid)
    if "AMEX Kvitton" not in grid or "Index" not in grid:
        sys.exit("Dumpen måste innehålla flikarna 'AMEX Kvitton' och 'Index'")
    kv = grid["AMEX Kvitton"]
    rows = shown(kv)
    hdr_i = next(i for i, r in enumerate(rows) if "Referens" in r and "Datum" in r)
    hdr = rows[hdr_i]
    col = {h: i for i, h in enumerate(hdr) if h and h not in col_map_skip()}
    for need in IMPORT_HEADERS + ["Finansiering", "Automatisk kategori"]:
        if need not in col:
            sys.exit(f"Rubriken '{need}' saknas i AMEX Kvitton")

    def cell(r, name):
        i = col[name]
        return r[i] if i < len(r) else ""

    data_start = hdr_i + 2  # 1-baserat radnummer för första dataraden
    existing_refs = collections.Counter()
    last_row = hdr_i + 1
    last_date = None
    hist = collections.defaultdict(list)
    for off, r in enumerate(rows[hdr_i + 1:]):
        rownum = data_start + off
        ref = clean_ref(cell(r, "Referens"))
        if not ref and not cell(r, "Datum"):
            continue
        last_row = rownum
        if ref:
            existing_refs[ref] += 1
        raw_d = kv[rownum - 1][col["Datum"]][1].get("numberValue") if col["Datum"] < len(kv[rownum - 1]) else None
        d = parse_date(raw_d if raw_d is not None else cell(r, "Datum"))
        if d and (last_date is None or d > last_date):
            last_date = d
        hist[norm(cell(r, "Beskrivning"))].append(
            {"F": cell(r, "Kortmedlem"), "C": cell(r, "Automatisk kategori"), "B": cell(r, "Finansiering"), "row": rownum}
        )
    dup_existing = [k for k, v in existing_refs.items() if v > 1]

    idx_rows = shown(grid["Index"])
    index = []  # i bladets ordning, inklusive tomma rader (de påverkar formeln)
    index_last_row = 2
    for off, r in enumerate(idx_rows[2:]):
        pat = r[1] if len(r) > 1 else ""
        cat = r[2] if len(r) > 2 else ""
        index.append((pat, cat))
        if pat:
            index_last_row = 3 + off
    index = index[: index_last_row - 2]
    categories = sorted({c for _, c in index if c})

    # Närmaste kompletta rad: sista dataraden där C och P–T har formler.
    tpl_row, formulas = None, None
    for rn in range(last_row, data_start - 1, -1):
        cells = kv[rn - 1]
        fs = {}
        for letter in DEFAULT_FORMULAS:
            i = col_index(letter)
            f = cells[i][1].get("formulaValue") if i < len(cells) else None
            if not f:
                break
            fs[letter] = re.sub(rf"(?<![$\d])(\$?[A-Z]{{1,3}}){rn}(?!\d)", r"\1{r}", f)
        else:
            tpl_row, formulas = rn, fs
            break
    if not tpl_row:
        sys.exit("Hittar ingen komplett mallrad med formler i C och P–T")
    formula_diff = [k for k in formulas if formulas[k] != DEFAULT_FORMULAS[k]]

    exported = []
    for f in args.export:
        exported.extend(json.loads(Path(f).read_text()))
    seen = set()
    new = []
    for x in exported:
        ref = x["Referens"]
        if ref in existing_refs or ref in seen:
            continue
        seen.add(ref)
        new.append(x)

    all_after = all(dt.date.fromisoformat(x["_date"]) >= last_date for x in new) if (new and last_date) else True
    new.sort(key=lambda x: x["_date"])  # stabil sortering: exportordning inom samma datum

    out_rows = []
    new_merchants = []
    for k, x in enumerate(new):
        desc = x.get("Beskrivning", "")
        h = hist.get(norm(desc), [])
        recent = h[-10:]
        f_hist = collections.Counter(e["F"] for e in recent if e["F"]).most_common(1)
        b_hist = collections.Counter(e["B"] for e in recent if e["B"]).most_common(1)
        c_hist = collections.Counter(e["C"] for e in recent if e["C"]).most_common(1)
        cat = index_match(desc, index)
        is_payment = norm(desc) == norm(PAYMENT_TEXT)
        cardholder = x.get("Kortmedlem", "")
        item = {
            "row": last_row + 1 + k,
            "values": {h_: x.get(h_, "") for h_ in IMPORT_HEADERS},
            "date": x["_date"],
            "amount": x["_amount"],
            "cardholder": cardholder,
            "history_count": len(h),
            "history_F": f_hist[0][0] if f_hist else None,
            "history_C": c_hist[0][0] if c_hist else None,
            "category_from_index": cat,
            "is_invoice_payment": is_payment,
            # Fält som Claude granskar och vid behov ändrar innan build:
            "F": f_hist[0][0] if f_hist else cardholder,
            "B": b_hist[0][0] if b_hist else "INTERN",
            "needs_review": (not h) or (not cat),
        }
        out_rows.append(item)
        if not cat and desc.upper() not in {m["pattern"].upper() for m in new_merchants}:
            # Mönstret måste vara exakt Beskrivning: nya Index-rader hamnar efter
            # glappet i Index och nås därför bara via exakt träff.
            new_merchants.append({"pattern": desc, "example_row": item["row"], "category": None,
                                  "history_C": item["history_C"]})

    plan = {
        "spreadsheet_id": SPREADSHEET_ID,
        "revision_id": revision,
        "header_row": hdr_i + 1,
        "template_row": tpl_row,
        "formulas": formulas,
        "formulas_differ_from_default": formula_diff,
        "columns": {h: col_letter(i) for h, i in col.items()},
        "last_row": last_row,
        "last_date": last_date.isoformat() if last_date else None,
        "existing_reference_count": sum(existing_refs.values()),
        "existing_duplicate_references": dup_existing,
        "exported_count": len(exported),
        "new_count": len(out_rows),
        "needs_full_sort": not all_after,
        "index_last_row": index_last_row,
        "categories": categories,
        "rows": out_rows,
        # Claude fyller i "category" (en befintlig kategori) för varje nytt
        # köpställe. "pattern" ska lämnas exakt som Beskrivning.
        "index_additions": new_merchants,
    }
    Path(args.out).write_text(json.dumps(plan, ensure_ascii=False, indent=1))
    print(json.dumps({k: plan[k] for k in ("revision_id", "template_row", "formulas_differ_from_default", "last_row", "last_date", "exported_count", "new_count", "needs_full_sort", "existing_duplicate_references")} | {
        "needs_review": sum(1 for r in out_rows if r["needs_review"]),
        "index_additions": len(new_merchants),
    }, ensure_ascii=False))


def col_map_skip():
    return {"Helper", "Signatur", ""}


# ------------------------------------------------------------------ build

def cmd_build(args):
    plan = json.loads(Path(args.plan).read_text())
    cols = plan["columns"]
    cats = set(plan["categories"])
    formulas, tpl_row = plan["formulas"], plan["template_row"]
    errors = []

    additions = plan.get("index_additions", [])
    for a in additions:
        if not a.get("category"):
            errors.append(f"Index-tillägg '{a['pattern']}' saknar kategori")
        elif a["category"] not in cats:
            errors.append(f"Index-tillägg '{a['pattern']}': '{a['category']}' är ingen befintlig kategori")
        if not str(a.get("pattern", "")).strip():
            errors.append("Index-tillägg med tomt mönster")
        elif not any(r["values"]["Beskrivning"].upper() == a["pattern"].upper() for r in plan["rows"]):
            errors.append(f"Index-tillägg '{a['pattern']}' motsvarar ingen ny rads Beskrivning exakt")
    # Nya Index-rader läggs sist; de nås bara via exakt träff (se index_match).
    index_after = [("", "")] + [(a["pattern"], a.get("category") or "") for a in additions]

    rows = plan["rows"]
    refs = [r["values"]["Referens"] for r in rows]
    if len(refs) != len(set(refs)):
        errors.append("Dubblettreferenser i planen")
    for r in rows:
        desc = r["values"]["Beskrivning"]
        if r["F"] not in RESPONSIBLE:
            errors.append(f"Rad {r['row']}: ansvarig '{r['F']}' är inte giltig")
        if r["B"] not in ("INTERN", "EXTERN"):
            errors.append(f"Rad {r['row']}: Finansiering '{r['B']}' är inte giltig")
        cat = r["category_from_index"] or index_match(desc, index_after)
        if not cat:
            errors.append(f"Rad {r['row']} ({desc}): blir utan kategori – lägg till i index_additions")
        if r["is_invoice_payment"] and cat and cat != PAYMENT_CATEGORY:
            errors.append(f"Rad {r['row']}: fakturabetalning matchar '{cat}', inte {PAYMENT_CATEGORY}")
        r["_category"] = cat
    if errors:
        print(json.dumps({"ok": False, "errors": errors}, ensure_ascii=False, indent=1))
        sys.exit(1)

    requests = []
    if rows:
        first = rows[0]["row"]
        last = rows[-1]["row"]
        if [r["row"] for r in rows] != list(range(first, last + 1)) or first != plan["last_row"] + 1:
            sys.exit("Radnumren i planen är inte sammanhängande efter sista dataraden")
        src = tpl_row  # närmaste kompletta rad
        width = col_index("T") + 1
        for paste in ("PASTE_FORMAT", "PASTE_DATA_VALIDATION"):
            requests.append({"copyPaste": {
                "source": {"sheetId": KVITTON_SHEET_ID, "startRowIndex": src - 1, "endRowIndex": src, "startColumnIndex": 0, "endColumnIndex": width},
                "destination": {"sheetId": KVITTON_SHEET_ID, "startRowIndex": first - 1, "endRowIndex": last, "startColumnIndex": 0, "endColumnIndex": width},
                "pasteType": paste, "pasteOrientation": "NORMAL"}})

        def s(v):
            return {"userEnteredValue": {"stringValue": str(v)}} if str(v) != "" else {}

        def n(v):
            return {"userEnteredValue": {"numberValue": v}}

        def fm(letter, rn):
            return {"userEnteredValue": {"formulaValue": formulas[letter].replace("{r}", str(rn))}}

        row_data = []
        for r in rows:
            v = r["values"]
            rn = r["row"]
            konto = str(v.get("Konto #", "")).strip()
            cells = {
                "B": s(r["B"]),
                "C": fm("C", rn),
                "D": n(serial(dt.date.fromisoformat(r["date"]))),
                "E": s(v["Beskrivning"]),
                "F": s(r["F"]),
                "G": n(int(konto)) if re.fullmatch(r"-?\d+", konto) else s(konto),
                "H": n(r["amount"]),
                "I": s(v.get("Utökade specifikationer", "")),
                "J": s(v.get("Visas på ditt kontoutdrag som", "")),
                "K": s(v.get("Adress", "")),
                "L": s(v.get("Ort", "")),
                "M": s(v.get("Postnummer", "")),
                "N": s(v.get("Land", "")),
                "O": s(v["Referens"]),
                "P": fm("P", rn), "Q": fm("Q", rn), "R": fm("R", rn), "S": fm("S", rn), "T": fm("T", rn),
            }
            # Säkerställ att kolumnbokstäverna stämmer med bladets rubriker.
            for h, letter in (("Datum", "D"), ("Beskrivning", "E"), ("Kortmedlem", "F"), ("Belopp", "H"), ("Referens", "O"), ("Finansiering", "B"), ("Automatisk kategori", "C")):
                if cols.get(h) != letter:
                    sys.exit(f"Rubriken '{h}' ligger i {cols.get(h)}, väntade {letter} – avbryter")
            row_data.append({"values": [cells[col_letter(i)] for i in range(1, width)]})
        requests.append({"updateCells": {
            "start": {"sheetId": KVITTON_SHEET_ID, "rowIndex": first - 1, "columnIndex": 1},
            "rows": row_data, "fields": "userEnteredValue"}})

        if plan.get("needs_full_sort"):
            requests.append({"sortRange": {
                "range": {"sheetId": KVITTON_SHEET_ID, "startRowIndex": plan["header_row"], "endRowIndex": last, "startColumnIndex": 0, "endColumnIndex": width},
                "sortSpecs": [{"dimensionIndex": col_index("D"), "sortOrder": "ASCENDING"}]}})

    if additions:
        i0 = plan["index_last_row"] + 1
        requests.append({"copyPaste": {
            "source": {"sheetId": INDEX_SHEET_ID, "startRowIndex": i0 - 2, "endRowIndex": i0 - 1, "startColumnIndex": 1, "endColumnIndex": 3},
            "destination": {"sheetId": INDEX_SHEET_ID, "startRowIndex": i0 - 1, "endRowIndex": i0 - 1 + len(additions), "startColumnIndex": 1, "endColumnIndex": 3},
            "pasteType": "PASTE_FORMAT", "pasteOrientation": "NORMAL"}})
        requests.append({"updateCells": {
            "start": {"sheetId": INDEX_SHEET_ID, "rowIndex": i0 - 1, "columnIndex": 1},
            "rows": [{"values": [{"userEnteredValue": {"stringValue": a["pattern"]}}, {"userEnteredValue": {"stringValue": a["category"]}}]} for a in additions],
            "fields": "userEnteredValue"}})

    Path(args.out).write_text(json.dumps(requests, ensure_ascii=False))
    summary = {
        "ok": True,
        "requests": len(requests),
        "rows": f"{rows[0]['row']}-{rows[-1]['row']}" if rows else None,
        "template_row": tpl_row,
        "write_control": {"requiredRevisionId": plan["revision_id"]},
        "date_range": [rows[0]["date"], rows[-1]["date"]] if rows else None,
        "gemensamt": sum(1 for r in rows if r["F"] == "GEMENSAMT"),
        "index_additions": [f"{a['pattern']} → {a['category']}" for a in additions],
        "expected_references": refs,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=1))


# ------------------------------------------------------------------ month

def _month_of(cell) -> tuple[int, int] | None:
    fv, uv = cell
    if "numberValue" in uv or ("formulaValue" in uv and fv):
        try:
            if "numberValue" in uv:
                d = parse_date(uv["numberValue"])
                return (d.year, d.month)
            d = dt.datetime.strptime(fv.strip(), "%b %Y")
            return (d.year, d.month)
        except (ValueError, AttributeError):
            return None
    return None


def _strip_legacy_colors(o):
    """Ta bort äldre 'color'-fält där 'colorStyle' finns (API:t vill ha ett av dem)."""
    if isinstance(o, dict):
        for k in list(o):
            if k.endswith("Style") and k[:-5] in o and k[:-5] in ("color", "foregroundColor", "backgroundColor"):
                del o[k[:-5]]
        for v in o.values():
            _strip_legacy_colors(v)
    elif isinstance(o, list):
        for v in o:
            _strip_legacy_colors(v)
    return o


def cmd_month(args):
    """Avgör om Summering ska få en ny månadskolumn och bygger i så fall
    begäran: infoga EN kolumn efter sista månaden, kopiera föregående
    kolumns formler + format dit, och förläng de diagramkällor som slutade
    exakt vid sista månadskolumnen så att de fortsätter täcka alla månader."""
    data = _load_json(args.summering)
    sh = next(x for x in data["sheets"] if x["properties"]["title"] == "Summering")
    sid = sh["properties"]["sheetId"]
    nrows = sh["properties"]["gridProperties"]["rowCount"]
    grid, _ = load_grid(args.summering)
    rows = grid["Summering"]
    row3 = rows[2]
    last = max(i for i, c in enumerate(row3) if _month_of(c))
    last_month = _month_of(row3[last])
    if args.today:
        today = dt.date.fromisoformat(args.today)
    else:
        from zoneinfo import ZoneInfo
        today = dt.datetime.now(ZoneInfo("Europe/Stockholm")).date()
    cur = (today.year, today.month)
    info = {"last_month_column": col_letter(last), "last_month": "%d-%02d" % last_month, "today": today.isoformat()}
    if last_month >= cur:
        info["needed"] = False
        Path(args.out).write_text("[]")
        print(json.dumps(info, ensure_ascii=False))
        return
    nxt = (last_month[0] + (last_month[1] // 12), last_month[1] % 12 + 1)
    if nxt != cur:
        info["note"] = f"Mer än en månad saknas ({info['last_month']} → {today:%Y-%m}); lägger ändå bara till EN kolumn enligt regeln."
    # Kolumnen efter sista månaden måste vara tom i bladet.
    for r in rows:
        if len(r) > last + 1 and (r[last + 1][0] or r[last + 1][1]):
            sys.exit(f"Kolumn {col_letter(last + 1)} är inte tom – avbryter utan ändring")
    reqs = [
        {"insertDimension": {"range": {"sheetId": sid, "dimension": "COLUMNS", "startIndex": last + 1, "endIndex": last + 2}, "inheritFromBefore": True}},
        {"copyPaste": {
            "source": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": nrows, "startColumnIndex": last, "endColumnIndex": last + 1},
            "destination": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": nrows, "startColumnIndex": last + 1, "endColumnIndex": last + 2},
            "pasteType": "PASTE_NORMAL", "pasteOrientation": "NORMAL"}},
    ]
    charts = []
    for ch in sh.get("charts", []):
        spec = json.loads(json.dumps(ch["spec"]))
        hit = []

        def walk(o):
            if isinstance(o, dict):
                if o.get("sheetId") == sid and o.get("endColumnIndex") == last + 1 and "startColumnIndex" in o:
                    o["endColumnIndex"] = last + 2
                    hit.append(1)
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)
        walk(spec)
        if hit:
            reqs.append({"updateChartSpec": {"chartId": ch["chartId"], "spec": _strip_legacy_colors(spec)}})
            charts.append({"chartId": ch["chartId"], "ranges_extended": len(hit)})
    info.update({"needed": True, "new_column": col_letter(last + 1), "new_month": "%d-%02d" % nxt, "charts": charts})
    Path(args.out).write_text(json.dumps(reqs, ensure_ascii=False))
    print(json.dumps(info, ensure_ascii=False))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("parse"); a.add_argument("files", nargs="+"); a.add_argument("--out", required=True)
    b = sub.add_parser("plan"); b.add_argument("--export", nargs="+", required=True); b.add_argument("--grid", required=True); b.add_argument("--out", required=True)
    c = sub.add_parser("build"); c.add_argument("--plan", required=True); c.add_argument("--out", required=True)
    m = sub.add_parser("month"); m.add_argument("--summering", required=True); m.add_argument("--today"); m.add_argument("--out", required=True)
    args = p.parse_args()
    {"parse": cmd_parse, "plan": cmd_plan, "build": cmd_build, "month": cmd_month}[args.cmd](args)


if __name__ == "__main__":
    main()
