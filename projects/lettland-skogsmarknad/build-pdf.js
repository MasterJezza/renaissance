// Renderar rapport.html till PDF med Chromium (Playwright).
const { chromium } = require('playwright');
const path = require('path');
(async () => {
  const [,, input, output] = process.argv;
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.goto('file://' + path.resolve(input), { waitUntil: 'load' });
  await page.pdf({
    path: output, format: 'A4', printBackground: true, preferCSSPageSize: true,
    displayHeaderFooter: true,
    headerTemplate: '<div style="font-size:7px;color:#5b6b63;width:100%;padding:0 16mm;font-family:DejaVu Sans,sans-serif;">Skogsmarknaden i Lettland 2020–2026 · Marknadsanalys</div>',
    footerTemplate: '<div style="font-size:7px;color:#5b6b63;width:100%;padding:0 16mm;font-family:DejaVu Sans,sans-serif;display:flex;justify-content:space-between;"><span>Ej investeringsrådgivning · Dataläge okt 2026</span><span>Sida <span class="pageNumber"></span> av <span class="totalPages"></span></span></div>',
  });
  await browser.close();
})();
