import assert from 'node:assert/strict';
import { chromium } from 'playwright';

const baseUrl = process.env.TASK13C_PREVIEW_URL ?? 'http://127.0.0.1:4173/';
const url = new URL(baseUrl);
url.searchParams.set('task13cDurationMs', '2500');

const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
  await page.goto(url.toString(), { waitUntil: 'networkidle' });
  await page.waitForSelector('.runtime-overlay[data-runtime-mode="interactive"]', { timeout: 15000 });

  const probe = page.locator('#task13c-probe');
  assert.equal(await probe.count(), 1, 'Task 13C probe panel must be injected into the validation build');

  await page.locator('#task13c-start').click();
  await page.keyboard.down('w');
  await page.waitForTimeout(150);
  await page.keyboard.up('w');
  await page.keyboard.press('e');
  await page.waitForTimeout(2800);

  const evidenceText = await page.locator('#task13c-evidence').inputValue();
  const evidence = JSON.parse(evidenceText);

  assert.equal(evidence.schemaVersion, 1);
  assert.equal(evidence.sourceCarrierCommit, 'bf5ba41951b7d37c588ebd7abc0944a856782b2c');
  assert.equal(evidence.assetClass, 'nonfinal_test_fixture');
  assert.equal(evidence.webgl2.available, true);
  assert.ok(evidence.runtimeFrames.sampleCount > 0, 'runtime frame proxy must capture samples');
  assert.ok(evidence.inputs.keyDownCount >= 2, 'W and E key input evidence must be captured');
  assert.ok(evidence.durationMs >= 2000, 'short CI duration must complete');
} finally {
  await browser.close();
}
