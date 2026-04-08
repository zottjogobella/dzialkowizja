<script lang="ts">
	import { goto } from '$app/navigation';
	import { historyItems, historyLoaded, loadHistory } from '$lib/stores/history';
	import { searchQuery, hasSearched } from '$lib/stores/search';
	import { onMount } from 'svelte';

	onMount(() => {
		if (!$historyLoaded) {
			loadHistory();
		}
	});

	function formatDate(iso: string): string {
		const d = new Date(iso);
		return d.toLocaleDateString('pl-PL', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
	}

	function rerunSearch(item: { query_text: string; query_type: string; top_result_id?: string | null }) {
		searchQuery.set(item.query_text);
		hasSearched.set(true);
		if (item.top_result_id) {
			goto(`/plot/${encodeURIComponent(item.top_result_id)}`);
		}
	}
</script>

<aside class="flex h-full w-72 flex-col border-r border-[var(--color-border)] bg-[var(--color-surface)]">
	<div class="border-b border-[var(--color-border)] p-4">
		<h2 class="text-sm font-semibold text-[var(--color-text-muted)] uppercase tracking-wider">Historia</h2>
	</div>

	<nav class="flex-1 overflow-y-auto p-2">
		{#if $historyItems.length === 0}
			<p class="px-3 py-6 text-center text-sm text-[var(--color-text-muted)]">Brak historii</p>
		{:else}
			{#each $historyItems as item (item.id)}
				<button
					class="w-full rounded-lg px-3 py-2 text-left text-sm transition-colors hover:bg-gray-50"
					onclick={() => rerunSearch(item)}
				>
					<div class="truncate font-medium">{item.query_text}</div>
					<div class="mt-0.5 text-xs text-[var(--color-text-muted)]">
						{item.result_count} wyników &middot; {formatDate(item.created_at)}
					</div>
				</button>
			{/each}
		{/if}
	</nav>
</aside>
