export type ApiErrorDetail = {
	code?: string;
	message?: string;
	[key: string]: unknown;
};

export class ApiError extends Error {
	status: number;
	detail: ApiErrorDetail | string | null;
	constructor(res: Response, detail: ApiErrorDetail | string | null) {
		super(`API error: ${res.status}`);
		this.status = res.status;
		this.detail = detail;
	}
	get code(): string | undefined {
		if (this.detail && typeof this.detail === 'object' && 'code' in this.detail) {
			return (this.detail as ApiErrorDetail).code;
		}
		return undefined;
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

async function parseError(res: Response): Promise<ApiErrorDetail | string | null> {
	try {
		const data = await res.clone().json();
		if (data && typeof data === 'object' && 'detail' in data) {
			return (data as { detail: ApiErrorDetail | string }).detail;
		}
		return null;
	} catch {
		return null;
	}
}

function storeOutsideHoursFlash(detail: ApiErrorDetail | string | null) {
	if (typeof localStorage === 'undefined') return;
	const message =
		detail && typeof detail === 'object' && typeof detail.message === 'string'
			? detail.message
			: 'Logowanie poza godzinami pracy.';
	try {
		localStorage.setItem('dzialkowizja_login_flash', message);
	} catch {
		// storage full / disabled — ignore
	}
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
		throw new ApiError(res, await parseError(res));
	}

	if (res.status === 403) {
		const detail = await parseError(res);
		if (detail && typeof detail === 'object' && detail.code === 'outside_hours') {
			storeOutsideHoursFlash(detail);
			window.location.href = '/auth/login';
			throw new ApiError(res, detail);
		}
		// fall through — caller inspects and renders normally.
	}

	return res;
}

export async function throwForResponse(res: Response): Promise<never> {
	throw new ApiError(res, await parseError(res));
}

export async function apiGet<T>(path: string): Promise<T> {
	const res = await apiFetch(path);
	if (!res.ok) await throwForResponse(res);
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
	if (!res.ok) await throwForResponse(res);
	return res.json();
}

export async function apiPut<T>(path: string, body?: unknown): Promise<T> {
	const res = await apiFetch(path, {
		method: 'PUT',
		headers: {
			'Content-Type': 'application/json',
			'X-CSRF-Token': getCsrfToken()
		},
		body: body ? JSON.stringify(body) : undefined
	});
	if (!res.ok) await throwForResponse(res);
	return res.json();
}

export async function apiDelete(path: string): Promise<void> {
	const res = await apiFetch(path, {
		method: 'DELETE',
		headers: {
			'X-CSRF-Token': getCsrfToken()
		}
	});
	if (!res.ok) await throwForResponse(res);
}
