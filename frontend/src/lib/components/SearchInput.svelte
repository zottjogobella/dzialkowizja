<script lang="ts">
	import { goto } from '$app/navigation';
	import { searchSuggestions, type SearchSuggestion } from '$lib/api/search';
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

		debounceTimer = setTimeout(async () => {
			abortController = new AbortController();
			try {
				const results = await searchSuggestions(query, abortController.signal);
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

	function selectSuggestion(suggestion: SearchSuggestion) {
		inputValue = suggestion.label;
		searchQuery.set(suggestion.label);
		hasSearched.set(true);
		closeDropdown();

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

<div class="relative w-full" bind:this={wrapperEl}>
	<!-- Search bar -->
	<div class="glass-chip flex items-stretch overflow-hidden" style="border-radius: 14px;">
		<div class="flex items-center border-r border-[var(--color-glass-border)] px-[18px] font-mono text-[10px] tracking-[1.5px] text-[var(--color-mute)]">
			ZAPYTAJ
		</div>
		<input
			bind:this={inputEl}
			bind:value={inputValue}
			oninput={handleInput}
			onkeydown={handleKeydown}
			onfocus={handleFocus}
			type="text"
			placeholder="Wpisz numer działki lub adres…"
			class="flex-1 border-none bg-transparent px-[18px] py-[18px] text-xl font-medium text-[var(--color-ink)] outline-none"
			style="letter-spacing: -0.3px; font-family: var(--font-sans);"
			autocomplete="off"
			spellcheck="false"
			role="combobox"
			aria-expanded={open}
			aria-autocomplete="list"
			aria-controls="search-listbox"
			aria-activedescendant={selectedIndex >= 0 ? `search-option-${selectedIndex}` : undefined}
		/>
		{#if loading}
			<div class="flex items-center pr-4">
				<div class="h-5 w-5 animate-spin rounded-full border-2 border-[var(--color-faint)] border-t-[var(--color-accent)]"></div>
			</div>
		{/if}
		<button
			class="m-1.5 cursor-pointer rounded-[var(--r-sm)] border-none px-7 text-[13px] font-semibold text-white"
			style="background: var(--color-accent); letter-spacing: 0.5px;"
			onclick={() => { if (inputValue.trim().length >= 2) fetchSuggestions(inputValue.trim()); }}
		>
			Szukaj &rarr;
		</button>
	</div>

	<!-- Suggestions dropdown -->
	{#if open && suggestions.length > 0}
		<div class="absolute z-50 mt-2 w-full" style="display: grid; gap: 6px;">
			{#each suggestions as suggestion, i (suggestion.label + suggestion.secondary + i)}
				<button
					id="search-option-{i}"
					role="option"
					aria-selected={i === selectedIndex}
					class="glass-chip grid w-full cursor-pointer items-center text-left transition-[filter]"
					style="grid-template-columns: 36px 80px 1fr 1fr 40px; padding: 11px 16px; border-color: {i === selectedIndex ? 'rgba(61,90,42,0.18)' : 'var(--color-glass-border)'}; background: {i === selectedIndex ? 'rgba(61,90,42,0.05)' : 'var(--color-glass)'};"
					onmouseenter={() => (selectedIndex = i)}
					onclick={() => selectSuggestion(suggestion)}
				>
					<div class="font-mono text-[10px] text-[var(--color-mute)]">{String(i + 1).padStart(2, '0')}</div>
					<div>
						<span class="glass-pill" style="padding: 4px 9px; font-size: 9px;">
							{suggestion.type === 'lot' ? 'DZIAŁKA' : 'ADRES'}
						</span>
					</div>
					<div class="font-serif text-base font-medium">{suggestion.label}</div>
					<div class="text-xs text-[var(--color-mute)]">{suggestion.secondary}</div>
					<div class="text-right font-mono text-[10px] text-[var(--color-mute)]">{i === 0 ? '&crarr;' : '&rarr;'}</div>
				</button>
			{/each}
		</div>
	{:else if open && loading}
		<div class="glass-card absolute z-50 mt-2 w-full px-4 py-6">
			<div class="flex items-center justify-center gap-2 text-sm text-[var(--color-mute)]">
				<div class="h-4 w-4 animate-spin rounded-full border-2 border-[var(--color-faint)] border-t-[var(--color-accent)]"></div>
				Szukam…
			</div>
		</div>
	{/if}
</div>
