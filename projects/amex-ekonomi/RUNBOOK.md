# Körinstruktion: Amex → Ekonomi (molnkörning)

Den här filen är instruktionen som den schemalagda uppgiften följer vid varje
körning. Den ersätter Codex-versionen och är anpassad för en molncontainer:
ingen Chrome-profil, ingen nyckelring och ingen integrerad webbläsare – i
stället en Playwright-webbläsare (`amex.js`), hemligheter i miljön och Google
Sheets-anslutningen.

- Målkalkylblad: `1FQU_otIfWm6tgyC1pfqfp_vFxiEuWdv974jul1UA0As` (Ekonomi)
- Flikar: "AMEX Kvitton" (sheetId 0), "Index" (1864865624), "Summering" (1629863088)
- Arbetskatalog: `projects/amex-ekonomi` · körningsdata: `projects/amex-ekonomi/run/` (checkas aldrig in)

## Hårda stopp – ändra då INTE kalkylbladet

Stoppa, ändra ingenting i bladet och rapportera exakt vilket engångsingrepp
användaren behöver göra om något av följande inträffar:

- `AMEX_USERNAME` eller `AMEX_PASSWORD` saknas i miljön.
- Sidan ligger inte på `americanexpress.com` när inloggning ska ske.
- Amex visar CAPTCHA, kräver Touch ID/biometri, SMS-kod, kod i appen eller
  annan interaktiv verifiering som inte är engångskod via e-post.
- Ingen engångskod från Amex kommer till e-posten inom 5 minuter, eller koden
  avvisas två gånger.
- Amex säger att lösenordet är fel eller att kontot är låst (försök då inte
  igen – upprepade försök kan låsa kontot).
- Exporten kan inte hämtas OCH reservvägen inte kan verifiera Referens för
  varje post.

Ändra aldrig säkerhetsinställningar hos Amex eller i miljön för att få igenom
en körning.

## Lösenordet

Lösenordet finns bara i miljövariabeln `AMEX_PASSWORD` och fylls i av
`amex.js login`. Skriv aldrig ut, logga, kopiera eller spara det; kör inte
`env`, `printenv`, `echo $AMEX_PASSWORD` eller liknande. Kontrollera bara att
variablerna finns:

```bash
for v in AMEX_USERNAME AMEX_PASSWORD; do [ -n "${!v}" ] && echo "$v finns" || echo "$v SAKNAS"; done
```

## 1. Förbered

```bash
cd projects/amex-ekonomi && mkdir -p run && rm -rf run/cmd run/res run/*.png run/export-* run/net
python3 -c "import openpyxl" 2>/dev/null || pip install -q openpyxl
```

Starta webbläsaren i bakgrunden (Bash med `run_in_background: true`). Den körs
som fullständig Chromium i en virtuell skärm, eftersom Amex bot-skydd avvisar
"headless shell":

```bash
xvfb-run -a -s "-screen 0 1366x900x24" node amex.js daemon
```

Vänta tills `run/status.json` visar `"state": "started"` och kör sedan
`node amex.js status`.

## 2. Logga in

```bash
node amex.js login
```

Svaret är JSON med `state`:

- `logged_in` – gå vidare till steg 3.
- `otp_required` – kör `node amex.js otp-email`. Det klickar på "Byt
  verifieringsmetod", väljer e-post och begär koden, och svarar med
  `requestedAt`. Om `chose_email` är `false`: läs `text` och skärmbilden
  (`shot`) och använd `node amex.js click "<synlig text>"` för exakt de
  knappar som behövs (t.ex. "Byt verifieringsmetod", "E-post", "Skicka kod").
  Hämta sedan koden ur e-posten (se nedan) och kör `node amex.js otp <kod>`.
- `captcha`, `login_error`, `wrong_domain`, `missing_secrets`,
  `password_not_filled` – hårt stopp.
- `unknown` – läs `text` och skärmbilden innan något annat görs.
- `login_page` (formuläret står kvar utan felmeddelande) – läs
  `run/netlog.txt`. Om `POST …/myca/logon/emea/action/login` visar `FAILED`
  eller `403` blockerar Amex bot-skydd (Akamai) anslutningen. Det är ett hårt
  stopp: försök inte igen och försök inte kringgå skyddet.

**Hämta engångskoden från e-posten (Superhuman-anslutningen):** kör
`list_accounts`, och sök sedan i varje konto efter det senaste mejlet från
American Express (avsändardomän `americanexpress.com` eller `aexp.com`) som
kommit **efter** `requestedAt`. Vänta upp till 5 minuter, och kontrollera ungefär var
20:e sekund. Använd bara en kod som står i ett sådant mejl. Skriv inte ut
koden i rapporten. En kod som avvisas får ersättas av en ny kod högst en gång.

**Tekniska fel (timeout, "detached", inget svar):** anta inte att klicket
misslyckades. Läs först `run/status.json`, `node amex.js status` och senaste
skärmbilden (`node amex.js shot`, öppna PNG-filen). Högst två riktade
återhämtningsförsök per tekniskt fel. Inga blinda klick och inga upprepade
inloggningar – ett nytt `login` bara om sidan bevisligen visar
inloggningsformuläret igen.

Inloggningen är klar först när transaktionssidan visas (`logged_in`).

## 3. Hämta bokförda transaktioner

```bash
node amex.js export
```

Exporten görs med Excel-format och "alla ytterligare transaktionsuppgifter".
Nedladdningshändelsen registreras innan den sista Hämta-knappen klickas.
Svaret innehåller `file`. Tolka filen:

```bash
python3 importer.py parse run/export-XXXX.xlsx --out run/export.json
```

Pågående poster och poster utan Referens tas bort automatiskt. Exporten
innehåller både huvudkort och extrakort.

**Täckning:** om tidigaste datum i exporten (`from`) ligger *efter* sista
datumet i bladet (se `last_date` i steg 5) kan transaktioner från föregående
faktureringsperiod saknas. Kör då `node amex.js text` för att se vilka
perioder sidan erbjuder och exportera även föregående period med
`node amex.js export "<periodens synliga text>"`. Tolka båda filerna i samma
`parse`-anrop.

**Reserv om exporten inte går att hämta:** `run/net/*.json` innehåller Amex
egna JSON-svar för transaktionstabellen. De får användas för att bygga
`run/export.json` (samma fält som `parse` ger) endast om varje post har en
verifierbar Referens, ett datum och ett belopp och tydligt är bokförd. Saknas
Referens eller säker status för en post importeras den inte. Använd aldrig en
export från en tidigare körning.

## 4. Läs kalkylbladet

Läs metadata, rubriker, värden och formler i ett anrop med
`get_spreadsheet`:

- `ranges`: `["'AMEX Kvitton'!A1:T3000", "Index!A1:E1000"]`
- `includeGridData`: true
- `fields`: `["revisionId", "sheets.properties.title", "sheets.properties.sheetId", "sheets.data.startRow", "sheets.data.rowData.values.formattedValue", "sheets.data.rowData.values.userEnteredValue"]`

Svaret är några MB och sparas därför till en fil, och verktygssvaret anger
sökvägen. Kopiera den till `run/grid.json`. Om bladet har fler än 3000 rader
ökar du intervallet.

## 5. Planera

```bash
python3 importer.py plan --export run/export.json --grid run/grid.json --out run/plan.json
```

Utdata visar `new_count`. **Om `new_count` är 0: ändra ingenting i bladet**
(inte heller Summering). Stoppa webbläsaren och rapportera att inga nya
bokförda transaktioner fanns.

Om `existing_duplicate_references` inte är tom finns redan dubbletter i
bladet. Rapportera dem, men rör dem inte.

`plan.json` innehåller bland annat:

- `rows[]`, de nya raderna i stigande datumordning, med radnummer, förslag på
  ansvarig (`F`), `B` (Finansiering), `category_from_index` (det som bladets
  formel i kolumn C kommer att ge) samt historik (`history_F`, `history_C`).
- `index_additions[]`, köpställen som annars skulle bli utan kategori.
- `formulas`, hjälpformlerna från närmaste kompletta rad.
- `revision_id`, bladets version vid läsningen.

## 6. Granska kategori och ansvarig (redigera `run/plan.json`)

Gå igenom **varje** rad och sätt de slutliga värdena med ett litet
Python-skript som redigerar JSON-filen:

**Ansvarig (`F`)** ska vara `GEMENSAMT`, `C G WEITZE` eller `HILDA GUSTAFSSON`.
- Sätt `GEMENSAMT` för tydligt delade livsmedel, bränsle, återkommande
  gemensamma prenumerationer och gemensamma hushållsinköp.
- Följ historiken (`history_F`) för samma köpställe när den finns.
- Behåll kortmedlemmen (`cardholder`) för tydligt personliga köp. Vid
  otydlighet väljer du den mest sannolika.

**Finansiering (`B`)** ska vara `INTERN` eller `EXTERN`. Standard är `INTERN`.
Följ historiken.

**Nya köpställen (`index_additions`)**: sätt `category` till den mest
sannolika *befintliga* kategorin (listan finns i `categories`). Använd
historiken (`history_C`) och liknande köpställen i Index som facit. Ändra inte
`pattern`. Det ska vara exakt Beskrivning, eftersom nya Index-rader hamnar
efter ett glapp i Index och då bara nås via exakt träff. Ingen ny kategori får
lämnas tom.

**"BETALNING MOTTAGEN, TACK"** är en fakturabetalning. Den ska alltid ha
kategorin "Fakturabetalning", vilket den redan får via Index. Den får aldrig
räknas in i Summering eller i ansvarsfördelningen.

## 7. Skriv

```bash
python3 importer.py build --plan run/plan.json --out run/requests.json
```

`build` stoppar med en lista över fel om något saknas (ogiltig ansvarig,
kategori som saknas, fel kolumner). Rätta i `plan.json` och kör igen.

Skicka sedan **hela** `run/requests.json` som `requests` i ett enda
`update_spreadsheet`-anrop, med
`writeControl: {"requiredRevisionId": "<revision_id från plan.json>"}`.
Anropet är atomärt, så antingen skrivs allt eller ingenting. Det gör följande:
- Kopierar bara format och datavalidering (inte värden) från närmaste
  kompletta rad till de nya raderna.
- Skriver varje importvärde och varje hjälpformel uttryckligen per rad i B–T.
- Lägger till nya köpställen sist i Index.
- Sorterar hela transaktionsraderna A–T efter Datum, men bara om
  `needs_full_sort` är true, alltså om äldre datum måste in mitt i.

**Om anropet misslyckas:**
- Revisionskonflikt (någon har ändrat bladet sedan steg 4): gör om steg 4–5.
  Behåll dina beslut genom att föra över `F`, `B` och kategorier per Referens
  till den nya planen. Bygg sedan och skriv igen.
- Osäkert resultat (timeout eller avbruten anslutning): läs först om
  referenserna (`get_values` på `'AMEX Kvitton'!O3:O3000`) och det exakta
  målintervallet. Skriv bara om ingen av de nya referenserna finns där. Högst
  ett nytt försök.
- Det finns ingen webbläsarväg till Google Sheets i molnet. Kan skrivningen
  inte genomföras säkert stoppar du och rapporterar.

## 8. Ny månadskolumn i Summering (högst en per månad)

Gäller bara när steg 7 har skrivit nya rader. Läs Summering med
`get_spreadsheet`:

- `ranges`: `["Summering!A1:AR50"]` (vidga om bladet har fler kolumner eller rader)
- `includeGridData`: true
- `fields`: `["revisionId", "sheets.properties", "sheets.charts", "sheets.data.startRow", "sheets.data.rowData.values.formattedValue", "sheets.data.rowData.values.userEnteredValue"]`

Spara svaret som `run/summering.json` och kör:

```bash
python3 importer.py month --summering run/summering.json --out run/month.json
```

Om `needed` är false gör du ingenting. Annars skickar du `run/month.json` som
`requests` i ett `update_spreadsheet`-anrop med `requiredRevisionId` från just
den läsningen. Anropet gör följande:
- Infogar exakt en kolumn efter sista månaden.
- Kopierar föregående månads formler och format dit.
- Förlänger bara de diagramkällor som slutade exakt vid sista månadskolumnen.
  Inget annat i diagrammen ändras.

Om resultatet är osäkert läser du om rad 3 i Summering innan något nytt
försök. Den dubbelkollen gör att kolumnen aldrig kan läggas till två gånger.

## 9. Verifiera

Kontrollera följande efter skrivningen:

1. Varje referens i `expected_references` (från `build`) förekommer **exakt
   en gång** i `'AMEX Kvitton'!O3:O`.
2. För de nya raderna (läs dem med `get_spreadsheet`, både `formattedValue`
   och `userEnteredValue`):
   - C (kategori) och F (ansvarig) är ifyllda.
   - C och P–T är formler som pekar på sin egen rad.
   - Inga celler visar fel (`#N/A`, `#REF!`, `#VALUE!`, `#ERROR!`).
   - Datumen är stigande.
3. `Summering!B2` visar "Uppdaterad <senaste transaktionsdatum>".
4. Den nya månadskolumnen, om en skapades, visar inga fel, och rad 3 har
   rätt månad.
5. `Index!E` (Okategoriserade köpställen) listar inga av de nya köpställena.

Reparera endast fel som hör till den här importen. Rör aldrig manuell data,
andra formler eller formatering.

## 10. Avsluta och rapportera

```bash
node amex.js stop
```

Rapportera kortfattat på svenska:
- antal tillagda transaktioner och datumintervall
- nya köpställen med vald kategori
- antal `GEMENSAMT`
- om en ny månadskolumn skapades
- eventuella stopp eller avvikelser och vad användaren behöver göra

Checka aldrig in något från `run/`.
