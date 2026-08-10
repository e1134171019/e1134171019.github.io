import { expect, test } from '@playwright/test';

test('development diagnostic can force the explicit unsupported WebGL2 fallback', async ({ page }) => {
  await page.goto('/?forceWebGL2Failure=1');

  const fallback = page.locator('[data-runtime-mode="fallback"]');
  await expect(fallback).toBeVisible();
  await expect(fallback.locator('.runtime-overlay__error-code')).toHaveText('錯誤代碼：unsupported_webgl2');
  await expect(fallback.getByText('目前顯示的是最低可用狀態介面，不等同於即時 3D 體驗。')).toBeVisible();
});
