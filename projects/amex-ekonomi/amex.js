#!/usr/bin/env node
// Amex-webbläsare för molnkörning.
//
// En långlivad Playwright-process ("daemon") håller en inloggad Amex-session
// och tar emot kommandon via filer i körningskatalogen. Samma fil används som
// klient: `node amex.js <kommando> [argument]` skickar ett kommando och skriver
// ut svaret som JSON.
//
//   node amex.js daemon            # startas i bakgrunden en gång per körning
//   node amex.js status
//   node amex.js login             # fyller i användarnamn/lösenord från miljön
//   node amex.js otp-email         # byter verifieringsmetod till e-post och begär kod
//   node amex.js otp <kod>         # fyller i engångskoden
//   node amex.js export [periodtext]  # Excel-export med utökade uppgifter
//   node amex.js shot | text | url  # felsökning: skärmbild, synlig text, adress
//   node amex.js click "<synlig text>" | click-sel "<css>" | goto <url>
//   node amex.js stop
//
// Säkerhet: lösenordet läses bara från AMEX_PASSWORD och skrivs direkt in i
// det maskerade fältet. Det loggas, skrivs ut eller sparas aldrig, och
// `fill`-kommandon för godtyckliga fält finns medvetet inte.

const fs = require('fs');
const path = require('path');

const RUN_DIR = path.resolve(process.env.AMEX_RUN_DIR || path.join(__dirname, 'run'));
const CMD_DIR = path.join(RUN_DIR, 'cmd');
const RES_DIR = path.join(RUN_DIR, 'res');
const STATUS = path.join(RUN_DIR, 'status.json');
const LOGIN_URL =
  'https://www.americanexpress.com/sv-se/account/login?DestPage=https://global.americanexpress.com/activity/recent';
const ACTIVITY_URL = 'https://global.americanexpress.com/activity/recent';
const UA =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const now = () => new Date().toISOString();

function writeStatus(obj) {
  fs.writeFileSync(STATUS, JSON.stringify({ ...obj, at: now() }, null, 2));
}

function isAmexHost(url) {
  try {
    const h = new URL(url).hostname;
    return h === 'americanexpress.com' || h.endsWith('.americanexpress.com');
  } catch {
    return false;
  }
}

// ---------------------------------------------------------------- daemon

async function daemon() {
  const { chromium } = require('playwright');
  fs.mkdirSync(CMD_DIR, { recursive: true });
  fs.mkdirSync(RES_DIR, { recursive: true });
  fs.mkdirSync(path.join(RUN_DIR, 'net'), { recursive: true });

  const context = await chromium.launchPersistentContext(path.join(RUN_DIR, 'profile'), {
    headless: true,
    locale: 'sv-SE',
    timezoneId: 'Europe/Stockholm',
    userAgent: UA,
    viewport: { width: 1366, height: 900 },
    acceptDownloads: true,
    args: ['--disable-blink-features=AutomationControlled'],
  });
  const page = context.pages()[0] || (await context.newPage());

  // Spara Amex egna JSON-svar om transaktioner; används bara som reserv
  // om Excel-exporten inte går att hämta.
  let netCount = 0;
  page.on('response', async (resp) => {
    try {
      const u = resp.url();
      if (!isAmexHost(u) || !/transaction|activity/i.test(u)) return;
      const ct = resp.headers()['content-type'] || '';
      if (!ct.includes('json')) return;
      const body = await resp.text();
      netCount += 1;
      fs.writeFileSync(
        path.join(RUN_DIR, 'net', `${String(netCount).padStart(3, '0')}.json`),
        JSON.stringify({ url: u, status: resp.status(), body }, null, 0),
      );
    } catch {
      /* ignoreras */
    }
  });

  writeStatus({ state: 'started', pid: process.pid });
  let seq = 0;
  let running = true;
  while (running) {
    const files = fs.readdirSync(CMD_DIR).filter((f) => f.endsWith('.json')).sort();
    if (!files.length) {
      await sleep(300);
      continue;
    }
    for (const f of files) {
      const full = path.join(CMD_DIR, f);
      let cmd;
      try {
        cmd = JSON.parse(fs.readFileSync(full, 'utf8'));
      } catch {
        await sleep(100);
        continue; // halvskriven fil, försök igen
      }
      fs.unlinkSync(full);
      seq += 1;
      let res;
      try {
        res = await handle(page, context, cmd);
      } catch (e) {
        res = { ok: false, error: String((e && e.message) || e).slice(0, 2000) };
      }
      res.shot = await shot(page, `${String(seq).padStart(3, '0')}-${cmd.name}`);
      res.url = page.url();
      fs.writeFileSync(path.join(RES_DIR, `${cmd.id}.json`), JSON.stringify(res, null, 2));
      if (cmd.name === 'stop') running = false;
    }
  }
  await context.close();
  writeStatus({ state: 'stopped' });
}

async function shot(page, name) {
  try {
    const p = path.join(RUN_DIR, `${name}.png`);
    await page.screenshot({ path: p });
    return p;
  } catch {
    return null;
  }
}

async function visibleText(page, max = 6000) {
  try {
    const t = await page.evaluate(() => document.body.innerText);
    return t.replace(/\n{2,}/g, '\n').slice(0, max);
  } catch {
    return '';
  }
}

async function dismissCookies(page) {
  for (const label of [/Avböj alla/i, /Acceptera alla/i]) {
    const b = page.getByRole('button', { name: label });
    if (await b.first().isVisible().catch(() => false)) {
      await b.first().click().catch(() => {});
      await sleep(800);
      return true;
    }
  }
  return false;
}

async function clickFirstVisible(page, candidates) {
  for (const loc of candidates) {
    const n = await loc.count().catch(() => 0);
    for (let i = 0; i < n; i++) {
      const el = loc.nth(i);
      if (await el.isVisible().catch(() => false)) {
        await el.click();
        return true;
      }
    }
  }
  return false;
}

// Klassar sidan efter inloggningsförsök.
async function classify(page) {
  const url = page.url();
  const text = (await visibleText(page, 20000)).toLowerCase();
  const html = await page.content().catch(() => '');
  if (/recaptcha|hcaptcha|captcha|arkose|funcaptcha/i.test(html) && /captcha|robot|jag är inte/i.test(text + html))
    return 'captcha';
  if (/global\.americanexpress\.com\/(activity|dashboard|overview|statements)/.test(url) && !/logga in/.test(text.slice(0, 300)))
    return 'logged_in';
  if (/engångskod|verifieringskod|verifiera din identitet|bekräfta din identitet|one-time|verification code|identitet/.test(text))
    return 'otp_required';
  if (/felaktig|stämmer inte|incorrect|låst|locked/.test(text)) return 'login_error';
  if (/\/account\/login/.test(url) && (await page.locator('#eliloPassword').count())) return 'login_page';
  return 'unknown';
}

async function waitForSettled(page, ms = 45000) {
  const end = Date.now() + ms;
  let last = 'unknown';
  while (Date.now() < end) {
    await sleep(1500);
    last = await classify(page);
    if (last !== 'unknown' && last !== 'login_page') return last;
  }
  return last;
}

async function handle(page, context, cmd) {
  const a = cmd.args || [];
  switch (cmd.name) {
    case 'status':
      return { ok: true, state: await classify(page) };

    case 'url':
      return { ok: true };

    case 'text':
      return { ok: true, text: await visibleText(page) };

    case 'shot':
      return { ok: true };

    case 'goto': {
      if (!isAmexHost(a[0])) return { ok: false, error: 'Endast americanexpress.com tillåts' };
      await page.goto(a[0], { waitUntil: 'domcontentloaded', timeout: 60000 });
      await sleep(4000);
      return { ok: true, state: await classify(page) };
    }

    case 'click': {
      const re = new RegExp(a[0], 'i');
      const ok = await clickFirstVisible(page, [
        page.getByRole('button', { name: re }),
        page.getByRole('link', { name: re }),
        page.getByRole('radio', { name: re }),
        page.getByRole('checkbox', { name: re }),
        page.getByRole('option', { name: re }),
        page.getByRole('tab', { name: re }),
        page.getByText(re),
      ]);
      await sleep(2500);
      return { ok, state: await classify(page) };
    }

    case 'click-sel': {
      await page.locator(a[0]).first().click({ timeout: 10000 });
      await sleep(2500);
      return { ok: true, state: await classify(page) };
    }

    case 'login':
      return login(page);

    case 'otp-email':
      return otpEmail(page);

    case 'otp':
      return submitOtp(page, a[0]);

    case 'export':
      return exportExcel(page, a[0]);

    case 'stop':
      return { ok: true };

    default:
      return { ok: false, error: `Okänt kommando: ${cmd.name}` };
  }
}

async function login(page) {
  const user = process.env.AMEX_USERNAME;
  const pass = process.env.AMEX_PASSWORD;
  if (!user || !pass) return { ok: false, state: 'missing_secrets', error: 'AMEX_USERNAME/AMEX_PASSWORD saknas i miljön' };

  // Återanvänd sessionen om den redan är inloggad.
  if (!/global\.americanexpress\.com/.test(page.url())) {
    await page.goto(ACTIVITY_URL, { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(() => {});
    await sleep(4000);
  }
  if ((await classify(page)) === 'logged_in') return { ok: true, state: 'logged_in', reused: true };

  await page.goto(LOGIN_URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await sleep(3000);
  await dismissCookies(page);
  if (!isAmexHost(page.url())) return { ok: false, state: 'wrong_domain', error: `Oväntad domän: ${page.url()}` };

  const userField = page.locator('#eliloUserID');
  const passField = page.locator('#eliloPassword');
  await userField.waitFor({ state: 'visible', timeout: 20000 });
  await userField.fill(user);
  await passField.fill(pass);
  // Verifiering utan att läsa värdet: bara att fältet är icke-tomt och maskerat.
  const filled = await passField.evaluate((el) => el.type === 'password' && el.value.length > 0);
  if (!filled) return { ok: false, state: 'password_not_filled' };

  const clicked = await clickFirstVisible(page, [
    page.locator('#loginSubmit'),
    page.getByRole('button', { name: /^logga in$/i }),
    page.locator('form button[type=submit]'),
  ]);
  if (!clicked) return { ok: false, state: 'no_submit_button' };

  const state = await waitForSettled(page);
  writeStatus({ state });
  return { ok: state === 'logged_in', state, text: state === 'logged_in' ? undefined : await visibleText(page, 3000) };
}

async function otpEmail(page) {
  // 1) Byt verifieringsmetod om sidan inte redan erbjuder e-post.
  await clickFirstVisible(page, [
    page.getByRole('button', { name: /byt verifieringsmetod|ändra verifieringsmetod|annan metod|byt metod/i }),
    page.getByRole('link', { name: /byt verifieringsmetod|ändra verifieringsmetod|annan metod|byt metod/i }),
    page.getByText(/byt verifieringsmetod/i),
  ]);
  await sleep(2500);
  // 2) Välj e-post.
  const chose = await clickFirstVisible(page, [
    page.getByRole('radio', { name: /e-post|email|mejl/i }),
    page.getByRole('button', { name: /e-post|email|mejl/i }),
    page.getByRole('link', { name: /e-post|email|mejl/i }),
    page.getByText(/engångskod via e-post|skicka.*e-post|e-post/i),
  ]);
  await sleep(1500);
  // 3) Skicka koden.
  const requestedAt = now();
  const sent = await clickFirstVisible(page, [
    page.getByRole('button', { name: /skicka|fortsätt|nästa|send|continue/i }),
  ]);
  await sleep(3000);
  writeStatus({ state: 'otp_requested', requestedAt });
  return { ok: chose, chose_email: chose, clicked_send: sent, requestedAt, text: await visibleText(page, 3000) };
}

async function submitOtp(page, code) {
  if (!/^\d{4,8}$/.test(code || '')) return { ok: false, error: 'Koden ska vara 4–8 siffror' };
  let input = page.locator('input[autocomplete="one-time-code"]');
  if (!(await input.count())) input = page.locator('input[type=tel], input[inputmode=numeric], input[name*=otp i], input[id*=otp i], input[name*=code i], input[id*=code i]');
  const n = await input.count();
  if (!n) return { ok: false, error: 'Hittar inget kodfält' };
  if (n >= code.length && n > 1) {
    for (let i = 0; i < code.length; i++) await input.nth(i).fill(code[i]);
  } else {
    await input.first().fill(code);
  }
  // Kom ihåg enheten om rutan finns (hjälper inom samma körning).
  await clickFirstVisible(page, [page.getByRole('checkbox', { name: /kom ihåg|remember|lita på/i })]);
  await clickFirstVisible(page, [
    page.getByRole('button', { name: /verifiera|bekräfta|fortsätt|skicka|logga in|verify|continue|submit/i }),
  ]);
  const state = await waitForSettled(page);
  writeStatus({ state });
  return { ok: state === 'logged_in', state, text: state === 'logged_in' ? undefined : await visibleText(page, 3000) };
}

async function exportExcel(page, periodText) {
  if (!/\/activity/.test(page.url())) {
    await page.goto(ACTIVITY_URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await sleep(5000);
  }
  if ((await classify(page)) !== 'logged_in') return { ok: false, state: await classify(page), error: 'Inte inloggad' };
  await dismissCookies(page);

  if (periodText) {
    // Välj faktureringsperiod (t.ex. föregående kontoutdrag) via synlig text.
    await clickFirstVisible(page, [
      page.getByRole('button', { name: /period|kontoutdrag|senaste transaktioner|välj/i }),
      page.getByRole('combobox'),
    ]);
    await sleep(1500);
    const re = new RegExp(periodText, 'i');
    const ok = await clickFirstVisible(page, [page.getByRole('option', { name: re }), page.getByRole('link', { name: re }), page.getByText(re)]);
    if (!ok) return { ok: false, error: `Hittar inte perioden "${periodText}"`, text: await visibleText(page, 3000) };
    await sleep(5000);
  }

  const opened = await clickFirstVisible(page, [
    page.getByRole('button', { name: /ladda ner|hämta|exportera|download/i }),
    page.getByRole('link', { name: /ladda ner|hämta|exportera|download/i }),
    page.locator('[data-testid*=download i], [aria-label*=ladda ner i], [aria-label*=download i]'),
  ]);
  if (!opened) return { ok: false, error: 'Hittar ingen Ladda ner-knapp', text: await visibleText(page, 3000) };
  await sleep(2000);

  await clickFirstVisible(page, [
    page.getByRole('radio', { name: /excel/i }),
    page.getByText(/^excel$/i),
    page.getByLabel(/excel/i),
  ]);
  // Ta med alla ytterligare transaktionsuppgifter.
  const extra = page.getByRole('checkbox', { name: /ytterligare|utökade|additional|all.*detalj/i });
  if (await extra.count()) {
    if (!(await extra.first().isChecked().catch(() => true))) await extra.first().check().catch(() => extra.first().click());
  }
  await sleep(800);

  // Registrera nedladdningshändelsen INNAN den slutliga knappen klickas.
  const dl = page.waitForEvent('download', { timeout: 60000 });
  const dialog = page.getByRole('dialog');
  const scope = (await dialog.count()) ? dialog.last() : page;
  const clicked = await clickFirstVisible(page, [
    scope.getByRole('button', { name: /ladda ner|hämta|download/i }),
    scope.getByRole('link', { name: /ladda ner|hämta|download/i }),
  ]);
  if (!clicked) return { ok: false, error: 'Hittar ingen slutlig Hämta-knapp', text: await visibleText(page, 3000) };
  const download = await dl;
  const target = path.join(RUN_DIR, `export-${Date.now()}${path.extname(download.suggestedFilename()) || '.xlsx'}`);
  await download.saveAs(target);
  const failure = await download.failure();
  if (failure) return { ok: false, error: `Nedladdningen misslyckades: ${failure}` };
  return { ok: true, file: target, suggested: download.suggestedFilename(), at: now() };
}

// ---------------------------------------------------------------- klient

async function client(name, args) {
  fs.mkdirSync(CMD_DIR, { recursive: true });
  fs.mkdirSync(RES_DIR, { recursive: true });
  const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const tmp = path.join(CMD_DIR, `${id}.tmp`);
  fs.writeFileSync(tmp, JSON.stringify({ id, name, args }));
  fs.renameSync(tmp, path.join(CMD_DIR, `${id}.json`));
  const resFile = path.join(RES_DIR, `${id}.json`);
  const timeoutMs = Number(process.env.AMEX_CMD_TIMEOUT_MS || 180000);
  const end = Date.now() + timeoutMs;
  while (Date.now() < end) {
    if (fs.existsSync(resFile)) {
      process.stdout.write(fs.readFileSync(resFile, 'utf8') + '\n');
      return;
    }
    await sleep(300);
  }
  console.log(JSON.stringify({ ok: false, error: 'timeout: inget svar från daemon (läs status.json och senaste skärmbild innan nytt försök)' }));
  process.exitCode = 2;
}

const [, , name, ...args] = process.argv;
if (!name) {
  console.error('Användning: node amex.js daemon | <kommando> [argument]');
  process.exit(1);
}
fs.mkdirSync(RUN_DIR, { recursive: true });
(name === 'daemon' ? daemon() : client(name, args)).catch((e) => {
  console.error(String((e && e.stack) || e));
  try {
    writeStatus({ state: 'crashed', error: String(e && e.message) });
  } catch {}
  process.exit(1);
});
