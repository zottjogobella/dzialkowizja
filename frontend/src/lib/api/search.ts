import { apiFetch, apiPost, ApiError } from './client';

export interface SearchSuggestion {
	type: 'lot' | 'address';
	label: string;
	secondary: string;
	id_dzialki?: string;
	lng?: number;
	lat?: number;
	place_id?: string;
}

export interface ResolveResponse {
	id_dzialki: string | null;
}

export async function searchSuggestions(
	query: string,
	signal?: AbortSignal,
	sessionToken?: string
): Promise<SearchSuggestion[]> {
	const params = new URLSearchParams({ q: query, limit: '5' });
	if (sessionToken) params.set('session_token', sessionToken);
	const res = await apiFetch(`/api/search?${params}`, { signal });
	if (!res.ok) throw new ApiError(res);
	return res.json();
}

export function resolvePlace(
	placeId: string,
	sessionToken?: string
): Promise<ResolveResponse> {
	return apiPost<ResolveResponse>('/api/search/resolve', {
		place_id: placeId,
		session_token: sessionToken
	});
}
