import { expect, test } from '@playwright/test';

test('enters interactive mode, moves, and completes the approved primary action without sticking', async ({ page }) => {
  const pageErrors: string[] = [];
  page.on('pageerror', (error) => pageErrors.push(error.message));

  await page.goto('/');
  await expect(page.locator('[data-runtime-mode="interactive"]')).toBeVisible();

  const runtime = page.locator('[data-character-runtime]');
  await page.keyboard.down('KeyW');
  await expect(runtime).toHaveAttribute('data-state', 'move');
  await page.keyboard.up('KeyW');

  // Approved Task 2 binding is KeyE. The nonfinal Box fixture has zero clips,
  // so the semantic animation fallback must complete instead of leaving action sticky.
  await page.keyboard.press('KeyE');
  await expect(runtime).toHaveAttribute('data-state', 'interactiveIdle');

  expect(pageErrors).toEqual([]);
});

test('action completion preserves held forward intent', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('[data-runtime-mode="interactive"]')).toBeVisible();

  const runtime = page.locator('[data-character-runtime]');
  await page.keyboard.down('KeyW');
  await expect(runtime).toHaveAttribute('data-state', 'move');

  await page.keyboard.press('KeyE');
  await expect(runtime).toHaveAttribute('data-state', 'move');

  await page.keyboard.up('KeyW');
  await expect(runtime).toHaveAttribute('data-state', 'interactiveIdle');
});
