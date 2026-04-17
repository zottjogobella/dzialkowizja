import tailwindcss from '@tailwindcss/vite';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

// In docker-compose the backend is reachable at http://backend:8000 from the
// frontend container, but on the host it's http://localhost:8000. Read from
// VITE_API_TARGET so the same config works in both setups.
const API_TARGET = process.env.VITE_API_TARGET ?? 'http://localhost:8000';

export default defineConfig({
	plugins: [tailwindcss(), sveltekit()],
	server: {
		proxy: {
			'/api': API_TARGET,
			'/health': API_TARGET
		}
	}
});
