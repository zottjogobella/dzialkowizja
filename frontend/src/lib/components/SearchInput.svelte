<script lang="ts">
	import { searchQuery, searchResults, searchLoading, searchTotal, hasSearched } from '$lib/stores/search';
	import { search } from '$lib/api/search';

	let inputValue = $state('');
	let inputEl: HTMLInputElement | undefined = $state();

	async function handleSubmit() {
		const q = inputValue.trim();
		if (!q) return;

		searchQuery.set(q);
		searchLoading.set(true);
		hasSearched.set(true);

		try {
			const result = await search(q);
			searchResults.set(result.results);
			searchTotal.set(result.total);
		} catch {
			searchResults.set([]);
			searchTotal.set(0);
		} finally {
			searchLoading.set(false);
		}
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter') {
			e.preventDefault();
			handleSubmit();
		}
	}
</script>

<form onsubmit={handleSubmit} class="w-full max-w-2xl">
	<div class="relative">
		<input
			bind:this={inputEl}
			bind:value={inputValue}
			onkeydown={handleKeydown}
			type="text"
			placeholder="Wpisz numer działki lub adres..."
			class="w-full rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] px-6 py-4 text-lg shadow-sm outline-none transition-shadow focus:shadow-md focus:ring-2 focus:ring-[var(--color-primary)]/20"
			autocomplete="off"
			spellcheck="false"
		/>
		<button
			type="submit"
			class="absolute right-3 top-1/2 -translate-y-1/2 rounded-xl bg-[var(--color-primary)] px-5 py-2 text-white transition-colors hover:opacity-90"
		>
			Szukaj
		</button>
	</div>
</form>
