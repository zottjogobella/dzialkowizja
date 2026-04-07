export class ApiError extends Error {
	status: number;
	constructor(res: Response) {
		super(`API error: ${res.status}`);
		this.status = res.status;
	}
}

function getCsrfToken(): string {
	if (typeof document === 'undefined') return '';
	return (
		document.cookie
			.split('; ')
			.find((c) => c.startsWith('dzialkowizja_csrf='))
			?.split('=')[1] ?? ''
	);
}

export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
	const res = await fetch(path, {
		...init,
		credentials: 'include',
		headers: {
			...(init?.headers as Record<string, string>)
		}
	});

	if (res.status === 401) {
		window.location.href = '/auth/login';
		throw new ApiError(res);
	}

	return res;
}

export async function apiGet<T>(path: string): Promise<T> {
	const res = await apiFetch(path);
	if (!res.ok) throw new ApiError(res);
	return res.json();
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
	const res = await apiFetch(path, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			'X-CSRF-Token': getCsrfToken()
		},
		body: body ? JSON.stringify(body) : undefined
	});
	if (!res.ok) throw new ApiError(res);
	return res.json();
}

export async function apiDelete(path: string): Promise<void> {
	const res = await apiFetch(path, {
		method: 'DELETE',
		headers: {
			'X-CSRF-Token': getCsrfToken()
		}
	});
	if (!res.ok) throw new ApiError(res);
}
