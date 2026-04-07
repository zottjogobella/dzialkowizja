import type { ServerLoadEvent } from '@sveltejs/kit';

export const load = async ({ cookies, fetch }: ServerLoadEvent) => {
	const session = cookies.get('dzialkowizja_session');
	if (!session) {
		return { user: null };
	}

	try {
		const res = await fetch('http://localhost:8000/auth/me', {
			headers: { Cookie: `dzialkowizja_session=${session}` }
		});
		if (!res.ok) return { user: null };
		return { user: await res.json() };
	} catch {
		return { user: null };
	}
};
