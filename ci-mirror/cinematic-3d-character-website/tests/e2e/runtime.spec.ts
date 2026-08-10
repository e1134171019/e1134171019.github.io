import { expect, test } from '@playwright/test';

test('enters interactive mode, moves, and observes the approved primary action', async ({ page }) => {
  const pageErrors: string[] = [];
  page.on('pageerror', (error) => pageErrors.push(error.message));

  await page.goto('/');
  await expect(page.locator('[data-runtime-mode="interactive"]')).toBeVisible();

  await page.keyboard.down('KeyW');
  await expect(page.locator('[data-character-runtime]')).toHaveAttribute('data-state', 'move');
  await page.keyboard.up('KeyW');

  // Approved Task 2 binding is KeyE. The older Task 12 plan's Space example is stale.
  await page.keyboard.press('KeyE');
  await expect(page.locator('[data-character-runtime]')).toHaveAttribute('data-state', 'action');

  expect(pageErrors).toEqual([]);
});
