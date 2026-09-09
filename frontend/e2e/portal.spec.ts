import { expect, test } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';

async function keys() {
  return JSON.parse(
    await readFile(process.env.E2E_SEED_FILE ?? resolve('../.local/demo-keys.json'), 'utf8'),
  ) as { customer: string; api_key: string }[];
}

test('customer can browse, preview, download, search, change view and sign out', async ({
  page,
  context,
}, testInfo) => {
  const [amy] = await keys();
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Çalışma alanınıza giriş yapın' })).toBeVisible();
  await page.getByLabel('API anahtarınız').fill(amy.api_key);
  await page.getByRole('button', { name: 'Güvenli giriş yap' }).click();
  await expect(page.getByRole('heading', { name: 'Her şey yerli yerinde.' })).toBeVisible();
  await expect(page.getByText('TenantFiles · Amy Energy', { exact: true })).toBeVisible();
  expect(
    (await context.cookies()).find((cookie) => cookie.name === 'tenantfiles_dev')?.httpOnly,
  ).toBe(true);
  expect(await page.evaluate(() => ({ ...localStorage, ...sessionStorage }))).toEqual({});
  for (const name of ['2026', '09', 'berlin_solar']) {
    await page.getByRole('button', { name: `${name} klasörünü aç`, exact: true }).click();
  }
  await expect(page.getByText('production.csv', { exact: true })).toBeVisible();
  await page.getByLabel('Bu klasörde ara', { exact: true }).fill('summary');
  await expect(page.getByText('production.csv', { exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: 'Aramayı temizle' }).click();
  await page.getByRole('button', { name: 'Kart görünümü' }).click();
  await expect(page.getByRole('button', { name: 'Kart görünümü' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await page.getByRole('button', { name: 'Liste görünümü' }).click();
  await page.screenshot({
    path: `../output/playwright/workspace-${testInfo.project.name}.png`,
    fullPage: true,
  });
  await page.getByRole('button', { name: 'production.csv önizle' }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByRole('columnheader', { name: 'energy_kwh' })).toBeVisible();
  await expect(dialog.getByRole('cell', { name: '1277', exact: true })).toBeVisible();
  await page.screenshot({
    path: `../output/playwright/preview-${testInfo.project.name}.png`,
    fullPage: true,
  });
  await page.getByRole('button', { name: 'Önizlemeyi kapat' }).click();
  await expect(dialog).toHaveCount(0);
  const downloaded = page.waitForEvent('download');
  await page.getByRole('link', { name: 'production.csv indir' }).click();
  const download = await downloaded;
  expect(download.suggestedFilename()).toBe('production.csv');
  expect(await readFile((await download.path())!, 'utf8')).toContain('energy_kwh');
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Her şey yerli yerinde.' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.getByRole('button', { name: 'Güvenli çıkış' }).click();
  await expect(page.getByLabel('API anahtarınız')).toBeVisible();
  await page.reload();
  await expect(page.getByLabel('API anahtarınız')).toBeVisible();
});

test('switching customer clears old data and cross-tenant file access is denied', async ({
  page,
}) => {
  const [amy, atlas] = await keys();
  await page.goto('/');
  await page.getByLabel('API anahtarınız').fill(amy.api_key);
  await page.getByRole('button', { name: 'Güvenli giriş yap' }).click();
  await expect(page.getByRole('heading', { name: 'Her şey yerli yerinde.' })).toBeVisible();
  const status = await page.evaluate(
    async () =>
      (await fetch('/api/files/download?path=atlas_c002/2026/09/berlin_solar/readme.txt')).status,
  );
  expect(status).toBe(404);
  await page.getByRole('button', { name: 'Güvenli çıkış' }).click();
  await page.getByLabel('API anahtarınız').fill(atlas.api_key);
  await page.getByRole('button', { name: 'Güvenli giriş yap' }).click();
  await expect(page.getByRole('heading', { name: 'Her şey yerli yerinde.' })).toBeVisible();
  await expect(page.getByText('Amy Energy', { exact: true })).toHaveCount(0);
  const content = await page.evaluate(async () =>
    (await fetch('/api/files/download?path=2026/09/berlin_solar/readme.txt')).text(),
  );
  expect(content).toContain('Atlas Labs');
  await page.getByRole('button', { name: 'Güvenli çıkış' }).click();
});
