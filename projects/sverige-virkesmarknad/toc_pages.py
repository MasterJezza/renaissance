"""Läser en renderad PDF och skriver sidnummer för varje rubrik (efter innehållsförteckningen) till JSON."""
import json
import subprocess
import sys

pdf, out = sys.argv[1], sys.argv[2]
n = int([l for l in subprocess.run(["pdfinfo", pdf], capture_output=True, text=True).stdout.splitlines()
         if l.startswith("Pages:")][0].split()[1])
toc = None
result = {}
texts = [subprocess.run(["pdftotext", "-f", str(i), "-l", str(i), "-layout", pdf, "-"],
                        capture_output=True, text=True).stdout for i in range(1, n + 1)]
# Rubriker hämtas från innehållsförteckningen (sida 2)
heads = [l.strip() for l in texts[1].splitlines() if l.strip() and l.strip() != "Innehåll"]
import re
heads = [re.sub(r"\s{2,}\d+$", "", h).strip() for h in heads]
for h in heads:
    for i in range(2, n):
        lines = [l.strip() for l in texts[i].splitlines()]
        if any(l == h or l.startswith(h + "  ") for l in lines):
            result[h] = str(i + 1)
            break
json.dump(result, open(out, "w", encoding="utf-8"), ensure_ascii=False)
print(f"{len(result)}/{len(heads)} rubriker hittade")
