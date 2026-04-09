import { defineConfig } from '@playwright/test';

export default defineConfig({
	testDir: 'e2e',
	timeout: 30_000,
	retries: 0,
	globalSetup: './e2e/global-setup.ts',
	use: {
		baseURL: 'https://45.137.213.188',
		ignoreHTTPSErrors: true,
		headless: true,
		storageState: 'e2e/.auth.json'
	}
});
