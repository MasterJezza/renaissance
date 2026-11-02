# Amex → Ekonomi

Hämtar bokförda American Express-transaktioner och lägger in nya poster i
kalkylbladet Ekonomi ("AMEX Kvitton", "Index", "Summering"). Allt körs i en
Claude Code-molnsession som schemalagd uppgift, så datorn behöver inte vara
på.

## Delar

| Fil | Vad den gör |
| --- | --- |
| `amex.js` | En Playwright-webbläsare som körs i bakgrunden. Den loggar in på Amex med användarnamn och lösenord från miljön, hanterar byte till engångskod via e-post och laddar ner Excel-exporten. Den styrs med korta kommandon (`node amex.js login`, `export` …). |
| `importer.py` | Har fyra delsteg. `parse` läser exporten. `plan` jämför mot bladet via Referens och föreslår ansvarig och kategori. `build` bygger en enda atomär skrivning. `month` lägger till Summering-kolumnen. Skriptet använder inget nätverk. |
| `RUNBOOK.md` | Steg-för-steg-instruktionen som den schemalagda uppgiften följer, inklusive alla stopp och reservvägar. |

Google Sheets läses och skrivs av Claude via Google Sheets-anslutningen.
Engångskoden hämtas ur e-posten via Superhuman-anslutningen.

## Inställningar i molnmiljön

Lägg till följande i miljöns inställningar. Öppna miljömenyn i sessionens
titelrad och välj Edit. Lägg dem under Network secrets, eller som
miljövariabler om den sektionen saknas:

- `AMEX_USERNAME`: användar-ID hos Amex
- `AMEX_PASSWORD`: lösenordet

Nätverket måste släppa igenom `americanexpress.com` (det gör det i nuvarande
miljö).

## Köra lokalt eller testa

```bash
cd projects/amex-ekonomi
node amex.js daemon &          # webbläsaren i bakgrunden
node amex.js login             # → {"state": "logged_in" | "otp_required" | ...}
node amex.js otp-email         # vid otp_required
node amex.js otp 123456
node amex.js export            # → {"file": "run/export-….xlsx"}
python3 importer.py parse run/export-*.xlsx --out run/export.json
python3 importer.py plan --export run/export.json --grid run/grid.json --out run/plan.json
python3 importer.py build --plan run/plan.json --out run/requests.json
node amex.js stop
```

`run/` innehåller exporter, skärmbilder och webbläsarprofilen. Mappen är
undantagen från git och får aldrig checkas in.

## Skillnader mot Codex-versionen

- Chrome-profilen "Carl" och tillägget Amex Key Bridge ersätts av en webbläsare
  i molnet och lösenordet i en miljöhemlighet. Lösenordet fylls i direkt i det
  maskerade fältet och loggas eller visas aldrig.
- Engångskoden begärs via e-post och läses ur inkorgen. CAPTCHA, SMS och kod i
  appen är fortfarande hårda stopp.
- Reservvägen via Sheets i webbläsaren finns inte i molnet. I stället är
  skrivningen ett enda atomärt `batchUpdate` som är låst mot bladets revision.
  Därför kan ingen delskrivning och ingen dubblett uppstå.
- Kategoriförslaget räknas fram med samma logik som formeln i kolumn C. Den har
  kontrollerats mot alla rader med den nuvarande formeln, med 0 avvikelser.
