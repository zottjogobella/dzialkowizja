import { writable } from 'svelte/store';
import type { HistoryItem } from '$lib/types/plot';
import { fetchHistory } from '$lib/api/history';

export const historyItems = writable<HistoryItem[]>([]);
export const historyLoaded = writable(false);

export async function loadHistory(): Promise<void> {
	try {
		const res = await fetchHistory();
		historyItems.set(res.items);
	} catch {
		// silently fail — history is non-critical
	} finally {
		historyLoaded.set(true);
	}
}
