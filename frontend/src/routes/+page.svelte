<script lang="ts">
	import SearchInput from '$lib/components/SearchInput.svelte';
	import { hasSearched } from '$lib/stores/search';
</script>

<svelte:head>
	<title>Działkowizja</title>
</svelte:head>

{#if !$hasSearched}
	<!-- State A: Centered search (like ChatGPT landing) -->
	<div class="flex flex-1 flex-col items-center justify-center px-6">
		<h1 class="mb-2 text-4xl font-bold text-[var(--color-primary)]">Działkowizja</h1>
		<p class="mb-8 text-[var(--color-text-muted)]">Sprawdź dane o dowolnej działce w Polsce</p>
		<SearchInput />
	</div>
{:else}
	<!-- State B: Search at top -->
	<div class="mx-auto w-full max-w-4xl px-6 py-6">
		<div class="mb-8">
			<SearchInput />
		</div>
	</div>
{/if}
