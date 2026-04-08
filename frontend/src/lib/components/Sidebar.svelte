<script lang="ts">
	import { goto } from '$app/navigation';
	import { historyItems, historyLoaded, loadHistory } from '$lib/stores/history';
	import { searchQuery, hasSearched } from '$lib/stores/search';
	import { onMount } from 'svelte';

	let open = $state(false);

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

<!-- Toggle button — always visible -->
<button
	class="fixed top-3 left-3 z-50 flex h-9 w-9 items-center justify-center rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text-muted)] shadow-sm transition-colors hover:bg-gray-50"
	onclick={() => (open = !open)}
	aria-label={open ? 'Zamknij historię' : 'Otwórz historię'}
>
	<!-- Clock/history icon -->
	<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
		<circle cx="12" cy="12" r="10"/>
		<polyline points="12 6 12 12 16 14"/>
	</svg>
</button>

{#if open}
	<!-- Backdrop -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="fixed inset-0 z-40 bg-black/20"
		onclick={() => (open = false)}
		onkeydown={(e) => e.key === 'Escape' && (open = false)}
	></div>

	<!-- Sidebar panel -->
	<aside class="fixed top-0 left-0 z-50 flex h-full w-72 flex-col border-r border-[var(--color-border)] bg-[var(--color-surface)] shadow-lg">
		<div class="flex items-center justify-between border-b border-[var(--color-border)] p-4">
			<h2 class="text-sm font-semibold text-[var(--color-text-muted)] uppercase tracking-wider">Historia</h2>
			<button
				class="flex h-7 w-7 items-center justify-center rounded text-[var(--color-text-muted)] transition-colors hover:bg-gray-100"
				onclick={() => (open = false)}
				aria-label="Zamknij"
			>
				<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
					<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
				</svg>
			</button>
		</div>

		<nav class="flex-1 overflow-y-auto p-2">
			{#if $historyItems.length === 0}
				<p class="px-3 py-6 text-center text-sm text-[var(--color-text-muted)]">Brak historii</p>
			{:else}
				{#each $historyItems as item (item.id)}
					<button
						class="w-full rounded-lg px-3 py-2 text-left text-sm transition-colors hover:bg-gray-50"
						onclick={() => { rerunSearch(item); open = false; }}
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
{/if}
