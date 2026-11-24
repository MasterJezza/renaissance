#!/usr/bin/env bash
# Bygger rapporten: diagram (SVG) -> bilagetabeller -> HTML -> PDF.
# Kräver python3 med matplotlib, pandoc och Node med Playwright/Chromium.
set -euo pipefail
cd "$(dirname "$0")"
python3 charts.py
python3 tables.py > /dev/null
python3 - <<'PY'
s = open("rapport.md", encoding="utf-8").read()
t = open("bilaga_tabeller.md", encoding="utf-8").read()
open("rapport_full.md", "w", encoding="utf-8").write(s.replace("!!BILAGA_TABELLER!!", t))
PY
pandoc rapport_full.md -s --toc --toc-depth=2 --embed-resources --css style.css \
  --include-before-body=cover.html -o rapport.html
node build-pdf.js rapport.html Virkesmarknaden_Sverige_2024-2026.pdf
# Andra varvet: för in sidnummer i innehållsförteckningen
python3 toc_pages.py Virkesmarknaden_Sverige_2024-2026.pdf toc_pages.json
node build-pdf.js rapport.html Virkesmarknaden_Sverige_2024-2026.pdf toc_pages.json
rm -f rapport.html rapport_full.md toc_pages.json
echo "Klar: Virkesmarknaden_Sverige_2024-2026.pdf"
