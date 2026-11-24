# Råvarumarknaden för timmer, massaved och bränsleved i Sverige 2024–2026

Marknadsrapport för en privat skogsägare: priser (leveransvirke, avverkningsuppdrag,
köparnas prislistor, trädbränslen), volymer, drivkrafter, regionala skillnader,
scenarier för 2026–2027 och praktiska implikationer. Hela Sverige med uppdelning på
landsdelar. Dataläge 24 november 2026.

## Filer

- `Virkesmarknaden_Sverige_2024-2026.pdf` – färdig rapport (A4, 22 sidor inkl. bilagor).
- `rapport.md` – rapportens text (redigera här). `cover.html` – försättsblad.
- `charts.py` – bygger diagrammen i `figures/` (SVG) från källdata.
- `tables.py` – bygger bilagetabellerna (`bilaga_tabeller.md`) och nyckeltal.
- `data/` – källdata som hämtats till rapporten:
  - `skogsstyrelsen_leveransvirke_kvartal.csv` – avräkningspriser leveransvirke, 2023K3–2026K3 (JO0303_3ny).
  - `skogsstyrelsen_avverkningsuppdrag_kvartal.csv` – avräkningspriser avverkningsuppdrag, 2025K1–2026K3 (JO030304a).
  - `skogsstyrelsen_leveransvirke_ar_2019-2021.csv` – årspriser leveransvirke 2019–2021 (JO0303_1ny).
  - `energimyndigheten_tradbransle_kvartal.csv` – trädbränslepriser per kvartal 2019–2026K2 (EN0307).
  - `scb_kpi_1980_100_manad.csv` – KPI, fastställda tal, för reala jämförelser.
- `style.css`, `build.sh`, `build-pdf.js`, `toc_pages.py` – layout och PDF-bygge.

Siffror från Skogen (köparnas jämförpriser), Biometria (förbrukning och import) och
Skogsstyrelsens avverkningsstatistik är inskrivna direkt i `charts.py`/`tables.py`
med källa angiven i rapporten.

## Bygga om rapporten

Kräver `python3` med `matplotlib`, `pandoc` och Node med Playwright/Chromium.

```bash
./build.sh
```

Rapporten är ett marknadsunderlag och utgör inte investeringsrådgivning.
