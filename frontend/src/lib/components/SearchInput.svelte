<script lang="ts">
	import { goto } from '$app/navigation';
	import { searchSuggestions, resolvePlace, type SearchSuggestion } from '$lib/api/search';
	import { recordSearch } from '$lib/api/history';
	import { searchQuery, hasSearched } from '$lib/stores/search';
	import { loadHistory } from '$lib/stores/history';

	let inputValue = $state('');
	let inputEl: HTMLInputElement | undefined = $state();
	let wrapperEl: HTMLDivElement | undefined = $state();

	let suggestions = $state<SearchSuggestion[]>([]);
	let loading = $state(false);
	let open = $state(false);
	let selectedIndex = $state(-1);
	let error = $state('');
	let sessionToken = $state(crypto.randomUUID());

	let debounceTimer: ReturnType<typeof setTimeout> | undefined;
	let abortController: AbortController | undefined;

	function cleanup() {
		if (debounceTimer) clearTimeout(debounceTimer);
		if (abortController) abortController.abort();
	}

	async function fetchSuggestions(query: string) {
		cleanup();

		if (query.length < 2) {
			suggestions = [];
			open = false;
			loading = false;
			return;
		}

		loading = true;
		open = true;
		error = '';

		debounceTimer = setTimeout(async () => {
			abortController = new AbortController();
			try {
				const results = await searchSuggestions(query, abortController.signal, sessionToken);
				suggestions = results;
				selectedIndex = -1;
				open = results.length > 0;
			} catch (e: unknown) {
				if (e instanceof DOMException && e.name === 'AbortError') return;
				suggestions = [];
				open = false;
			} finally {
				loading = false;
			}
		}, 200);
	}

	function closeDropdown() {
		open = false;
		selectedIndex = -1;
	}

	async function selectSuggestion(suggestion: SearchSuggestion) {
		inputValue = suggestion.label;
		searchQuery.set(suggestion.label);
		hasSearched.set(true);
		closeDropdown();
		error = '';

		if (suggestion.place_id) {
			// Google address: resolve via PRG to find plot
			loading = true;
			try {
				const resolved = await resolvePlace(suggestion.place_id, sessionToken);
				sessionToken = crypto.randomUUID();
				if (resolved.id_dzialki) {
					recordSearch({
						query_text: suggestion.label,
						query_type: suggestion.type,
						result_count: suggestions.length,
						top_result_id: resolved.id_dzialki
					}).then(() => loadHistory()).catch(() => {});
					goto(`/plot/${encodeURIComponent(resolved.id_dzialki)}`);
				} else {
					error = 'Nie znaleziono działki dla tego adresu';
				}
			} catch {
				error = 'Błąd podczas wyszukiwania działki';
			} finally {
				loading = false;
			}
			return;
		}

		// Lot or legacy address with direct id_dzialki
		const plotId = suggestion.type === 'lot' ? suggestion.label : suggestion.id_dzialki;

		recordSearch({
			query_text: suggestion.label,
			query_type: suggestion.type,
			result_count: suggestions.length,
			top_result_id: plotId ?? undefined
		}).then(() => loadHistory()).catch(() => {});

		if (plotId) {
			goto(`/plot/${encodeURIComponent(plotId)}`);
		}
	}

	function handleInput() {
		fetchSuggestions(inputValue.trim());
	}

	function handleKeydown(e: KeyboardEvent) {
		if (!open && e.key !== 'Enter') return;

		switch (e.key) {
			case 'ArrowDown':
				e.preventDefault();
				if (!open && inputValue.trim().length >= 2) {
					// reopen if we have suggestions
					if (suggestions.length > 0) open = true;
					return;
				}
				selectedIndex = Math.min(selectedIndex + 1, suggestions.length - 1);
				break;
			case 'ArrowUp':
				e.preventDefault();
				selectedIndex = Math.max(selectedIndex - 1, -1);
				break;
			case 'Enter':
				e.preventDefault();
				if (open && selectedIndex >= 0 && selectedIndex < suggestions.length) {
					selectSuggestion(suggestions[selectedIndex]);
				} else if (inputValue.trim().length >= 2) {
					// If no item selected, trigger search anyway
					fetchSuggestions(inputValue.trim());
				}
				break;
			case 'Escape':
				closeDropdown();
				inputEl?.blur();
				break;
		}
	}

	function handleClickOutside(e: MouseEvent) {
		if (wrapperEl && !wrapperEl.contains(e.target as Node)) {
			closeDropdown();
		}
	}

	function handleFocus() {
		if (suggestions.length > 0 && inputValue.trim().length >= 2) {
			open = true;
		}
	}
</script>

<svelte:document onclick={handleClickOutside} />

<div class="relative w-full max-w-2xl" bind:this={wrapperEl}>
	<div class="relative">
		<input
			bind:this={inputEl}
			bind:value={inputValue}
			oninput={handleInput}
			onkeydown={handleKeydown}
			onfocus={handleFocus}
			type="text"
			placeholder="Wpisz numer działki lub adres..."
			class="w-full rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] px-6 py-4 text-lg shadow-sm outline-none transition-shadow focus:shadow-md focus:ring-2 focus:ring-[var(--color-primary)]/20"
			autocomplete="off"
			spellcheck="false"
			role="combobox"
			aria-expanded={open}
			aria-autocomplete="list"
			aria-controls="search-listbox"
			aria-activedescendant={selectedIndex >= 0 ? `search-option-${selectedIndex}` : undefined}
		/>
		{#if loading}
			<div class="absolute right-4 top-1/2 -translate-y-1/2">
				<div class="h-5 w-5 animate-spin rounded-full border-2 border-[var(--color-border)] border-t-[var(--color-primary)]"></div>
			</div>
		{/if}
	</div>

	{#if open && suggestions.length > 0}
		<ul
			id="search-listbox"
			role="listbox"
			class="absolute z-50 mt-2 w-full overflow-hidden rounded-xl border border-[var(--color-border)] bg-white shadow-lg"
		>
			{#each suggestions as suggestion, i (suggestion.label + suggestion.secondary + i)}
				<li
					id="search-option-{i}"
					role="option"
					aria-selected={i === selectedIndex}
					class="flex cursor-pointer items-center gap-3 px-4 py-3 transition-colors {i === selectedIndex ? 'bg-gray-100' : 'hover:bg-gray-50'}"
					onmouseenter={() => (selectedIndex = i)}
					onclick={() => selectSuggestion(suggestion)}
					onkeydown={(e) => { if (e.key === 'Enter') selectSuggestion(suggestion); }}
				>
					{#if suggestion.type === 'lot'}
						<span class="shrink-0 rounded-full bg-blue-100 px-2 py-0.5 text-[10px] font-semibold text-blue-700">Działka</span>
					{:else}
						<span class="shrink-0 rounded-full bg-green-100 px-2 py-0.5 text-[10px] font-semibold text-green-700">Adres</span>
					{/if}
					<div class="min-w-0 flex-1">
						<div class="truncate text-sm font-medium">{suggestion.label}</div>
						<div class="truncate text-xs text-[var(--color-text-muted)]">{suggestion.secondary}</div>
					</div>
				</li>
			{/each}
		</ul>
	{:else if open && loading}
		<div class="absolute z-50 mt-2 w-full rounded-xl border border-[var(--color-border)] bg-white px-4 py-6 shadow-lg">
			<div class="flex items-center justify-center gap-2 text-sm text-[var(--color-text-muted)]">
				<div class="h-4 w-4 animate-spin rounded-full border-2 border-[var(--color-border)] border-t-[var(--color-primary)]"></div>
				Szukam...
			</div>
		</div>
	{/if}

	{#if error}
		<p class="mt-2 text-center text-sm text-red-600">{error}</p>
	{/if}
</div>
