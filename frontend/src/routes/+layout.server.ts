import { redirect, type ServerLoadEvent } from '@sveltejs/kit';

const PUBLIC_PATHS = ['/auth/login'];

export const load = async ({ cookies, fetch, url }: ServerLoadEvent) => {
	const isPublic = PUBLIC_PATHS.some((p) => url.pathname.startsWith(p));

	const session = cookies.get('dzialkowizja_session');
	if (!session) {
		if (!isPublic) throw redirect(302, '/auth/login');
		return { user: null };
	}

	try {
		const res = await fetch('http://localhost:8000/api/auth/me', {
			headers: { Cookie: `dzialkowizja_session=${session}` }
		});
		if (!res.ok) {
			if (!isPublic) throw redirect(302, '/auth/login');
			return { user: null };
		}
		return { user: await res.json() };
	} catch (e) {
		if (e instanceof Response || (e as any)?.status === 302) throw e;
		if (!isPublic) throw redirect(302, '/auth/login');
		return { user: null };
	}
};
