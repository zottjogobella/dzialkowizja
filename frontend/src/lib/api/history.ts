import { apiGet, apiPost, apiDelete } from './client';
import type { HistoryItem } from '$lib/types/plot';

interface HistoryResponse {
	items: HistoryItem[];
	total: number;
}

export async function fetchHistory(limit = 20): Promise<HistoryResponse> {
	return apiGet<HistoryResponse>(`/api/history?limit=${limit}`);
}

export async function recordSearch(params: {
	query_text: string;
	query_type: string;
	result_count: number;
	top_result_id?: string;
}): Promise<void> {
	await apiPost('/api/history', params);
}

export async function clearHistory(): Promise<void> {
	await apiDelete('/api/history');
}
