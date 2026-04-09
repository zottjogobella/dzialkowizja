import { chromium } from '@playwright/test';

export default async function globalSetup() {
	const browser = await chromium.launch();
	const context = await browser.newContext({ ignoreHTTPSErrors: true });
	const page = await context.newPage();

	await page.request.post('https://45.137.213.188/api/auth/login', {
		data: { email: 'test', password: 'playwright' }
	});

	await context.storageState({ path: 'e2e/.auth.json' });
	await browser.close();
}
