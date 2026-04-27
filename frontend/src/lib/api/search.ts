import { apiFetch, throwForResponse } from './client';

export interface SearchSuggestion {
	type: 'lot' | 'address';
	label: string;
	secondary: string;
	id_dzialki?: string;
	lng?: number;
	lat?: number;
	has_sluzebnosci?: boolean | null;
	has_10_or_more_owners?: boolean | null;
	has_state_owner?: boolean | null;
	no_kw_in_sheet?: boolean | null;
}

export async function searchSuggestions(
	query: string,
	signal?: AbortSignal
): Promise<SearchSuggestion[]> {
	const params = new URLSearchParams({ q: query, limit: '5' });
	const res = await apiFetch(`/api/search?${params}`, { signal });
	if (!res.ok) await throwForResponse(res);
	return res.json();
}
