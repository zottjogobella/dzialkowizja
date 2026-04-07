import type { SearchResult } from '$lib/types/plot';
import { apiGet } from './client';

export async function search(query: string, limit = 20): Promise<SearchResult> {
	const params = new URLSearchParams({ q: query, limit: String(limit) });
	return apiGet<SearchResult>(`/api/search?${params}`);
}

export async function suggest(query: string): Promise<SearchResult> {
	const params = new URLSearchParams({ q: query });
	return apiGet<SearchResult>(`/api/search/suggest?${params}`);
}
