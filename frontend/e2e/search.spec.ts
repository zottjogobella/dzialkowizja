import { test, expect, type Locator } from '@playwright/test';

/** Fill input and trigger Svelte's oninput handler */
async function typeInto(input: Locator, text: string) {
	await input.evaluate((el, val) => {
		const inp = el as HTMLInputElement;
		const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
			HTMLInputElement.prototype, 'value'
		)!.set!;
		nativeInputValueSetter.call(inp, val);
		inp.dispatchEvent(new Event('input', { bubbles: true }));
	}, text);
}

test.beforeEach(async ({ page }) => {
	await page.goto('/');
	await page.waitForLoadState('networkidle');
	await expect(page.locator('input[placeholder*="działki"]')).toBeVisible();
});

test.describe('Address search (PRG)', () => {
	test('returns suggestions for a Polish address', async ({ page }) => {
		await typeInto(page.locator('input[placeholder*="działki"]'), 'Poznanska 1, Poznan');

		const listbox = page.locator('#search-listbox');
		await expect(listbox).toBeVisible({ timeout: 10_000 });
		await expect(listbox.locator('li').first()).toBeVisible();
	});

	test('shows "Adres" badge for address suggestions', async ({ page }) => {
		await typeInto(page.locator('input[placeholder*="działki"]'), 'Krakowska 10, Wroclaw');

		const listbox = page.locator('#search-listbox');
		await expect(listbox).toBeVisible({ timeout: 10_000 });

		const badge = listbox.locator('li').first().locator('span', { hasText: 'Adres' });
		await expect(badge).toBeVisible();
	});

	test('selecting an address navigates to plot page', async ({ page }) => {
		test.setTimeout(60_000);
		await typeInto(page.locator('input[placeholder*="działki"]'), 'Poznanska 1, Poznan');

		const listbox = page.locator('#search-listbox');
		await expect(listbox).toBeVisible({ timeout: 15_000 });

		await listbox.locator('li').first().click();

		await page.waitForURL(/\/plot\//, { timeout: 10_000 });
		expect(page.url()).toContain('/plot/');
	});
});

test.describe('Lot ID search', () => {
	test('returns lot suggestions with "Działka" badge', async ({ page }) => {
		test.setTimeout(60_000);
		await typeInto(page.locator('input[placeholder*="działki"]'), '140904_2');

		const listbox = page.locator('#search-listbox');
		await expect(listbox).toBeVisible({ timeout: 30_000 });

		const badge = listbox.locator('li').first().locator('span', { hasText: 'Działka' });
		await expect(badge).toBeVisible();
	});
});
