import { writable } from 'svelte/store';
import type { HistoryItem } from '$lib/types/plot';

export const historyItems = writable<HistoryItem[]>([]);
export const historyLoaded = writable(false);
