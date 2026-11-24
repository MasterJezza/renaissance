// Renderar rapport.html till PDF med Chromium (Playwright).
// Valfritt tredje argument: JSON-fil {rubriktext: sidnummer} som skrivs in i innehållsförteckningen.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
(async () => {
  const [,, input, output, tocJson] = process.argv;
  const pages = tocJson && fs.existsSync(tocJson) ? JSON.parse(fs.readFileSync(tocJson, 'utf8')) : {};
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.goto('file://' + path.resolve(input), { waitUntil: 'load' });
  await page.evaluate((pages) => {
    document.querySelectorAll('nav#TOC a').forEach(a => {
      const span = document.createElement('span');
      span.className = 'toc-page';
      span.textContent = pages[a.textContent.replace(/\s+/g, ' ').trim()] || '';
      a.appendChild(span);
    });
  }, pages);
  await page.pdf({
    path: output, format: 'A4', printBackground: true, preferCSSPageSize: true,
    displayHeaderFooter: true,
    headerTemplate: '<div style="font-size:7px;color:#5b6b63;width:100%;padding:0 16mm;font-family:DejaVu Sans,sans-serif;">Råvarumarknaden för timmer, massaved och bränsleved 2024–2026 · Sverige</div>',
    footerTemplate: '<div style="font-size:7px;color:#5b6b63;width:100%;padding:0 16mm;font-family:DejaVu Sans,sans-serif;display:flex;justify-content:space-between;"><span>Dataläge 24 nov 2026 · Ej investeringsrådgivning</span><span>Sida <span class="pageNumber"></span> av <span class="totalPages"></span></span></div>',
  });
  await browser.close();
})();
