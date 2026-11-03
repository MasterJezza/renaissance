#!/usr/bin/env bash
# Bygger rapport.pdf från rapport.md (kräver pandoc och Playwright/Chromium).
set -euo pipefail
cd "$(dirname "$0")"
pandoc rapport.md -s --embed-resources --css style.css -o rapport.html
node build-pdf.js rapport.html Finland_skogsmarknad_2020-2026.pdf
rm -f rapport.html
echo "Klar: Finland_skogsmarknad_2020-2026.pdf"
