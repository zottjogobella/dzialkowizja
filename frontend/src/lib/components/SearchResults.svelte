<script lang="ts">
	import { searchResults, searchLoading, searchTotal, hasSearched } from '$lib/stores/search';
	import PlotCard from './PlotCard.svelte';
</script>

{#if $searchLoading}
	<div class="flex items-center justify-center py-12">
		<div class="h-8 w-8 animate-spin rounded-full border-4 border-[var(--color-border)] border-t-[var(--color-primary)]"></div>
	</div>
{:else if $hasSearched && $searchResults.length === 0}
	<div class="py-12 text-center text-[var(--color-text-muted)]">
		<p class="text-lg">Brak wyników</p>
		<p class="mt-1 text-sm">Spróbuj innego numeru działki lub adresu</p>
	</div>
{:else if $searchResults.length > 0}
	<div class="mb-4 text-sm text-[var(--color-text-muted)]">
		Znaleziono {$searchTotal} {$searchTotal === 1 ? 'wynik' : 'wyników'}
	</div>
	<div class="grid gap-3">
		{#each $searchResults as plot (plot.id_dzialki)}
			<PlotCard {plot} />
		{/each}
	</div>
{/if}
