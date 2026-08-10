import { expect, test } from '@playwright/test';

test('window blur clears held keyboard input', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('[data-runtime-mode="interactive"]')).toBeVisible();

  const runtime = page.locator('[data-character-runtime]');
  await page.keyboard.down('KeyW');
  await expect(runtime).toHaveAttribute('data-held-inputs', '1');

  await page.evaluate(() => window.dispatchEvent(new Event('blur')));
  await expect(runtime).toHaveAttribute('data-held-inputs', '0');
});
