import { writable } from 'svelte/store';
import type { PlotSummary } from '$lib/types/plot';

export const searchQuery = writable('');
export const searchResults = writable<PlotSummary[]>([]);
export const searchLoading = writable(false);
export const searchTotal = writable(0);
export const hasSearched = writable(false);
