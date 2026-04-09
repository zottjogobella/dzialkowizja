import { apiFetch, ApiError } from './client';

export interface SearchSuggestion {
	type: 'lot' | 'address';
	label: string;
	secondary: string;
	id_dzialki?: string;
	lng?: number;
	lat?: number;
}

export async function searchSuggestions(
	query: string,
	signal?: AbortSignal
): Promise<SearchSuggestion[]> {
	const params = new URLSearchParams({ q: query, limit: '5' });
	const res = await apiFetch(`/api/search?${params}`, { signal });
	if (!res.ok) throw new ApiError(res);
	return res.json();
}
