<script lang="ts">
	import { page } from '$app/stores';
	import {
		getPlot,
		getPlotGeometry,
		getPlotListings,
		getPlotBuildings,
		getPlotTransactions,
		getPlotInvestments,
		getPlotRoszczenie,
		type ListingsResponse,
		type InvestmentType,
		type TransactionType,
		type RoszczenieRow,
	} from '$lib/api/plots';
	import type { PlotDetail, Listing, Transaction, Investment } from '$lib/types/plot';
	import PlotMap from '$lib/components/PlotMap.svelte';

	let plot = $state<PlotDetail | null>(null);
	let loading = $state(true);
	let error = $state('');
	let geometry = $state<GeoJSON.Feature | null>(null);
	let geometryLoading = $state(true);
	let activeListings = $state<Listing[]>([]);
	let inactiveListings = $state<Listing[]>([]);
	let listingsLoading = $state(true);
	let buildings = $state<GeoJSON.FeatureCollection | null>(null);
	let transactions = $state<Transaction[]>([]);
	let transactionsLoading = $state(true);
	let transactionsType = $state<TransactionType>('all');
	let investments = $state<Investment[]>([]);
	let investmentsLoading = $state(true);
	let investmentsType = $state<InvestmentType>('all');
	let investmentsMonths = $state(24);
	let roszczenieRow = $state<RoszczenieRow | null>(null);

	const allListings = $derived([...activeListings, ...inactiveListings]);

	$effect(() => {
		const id = $page.params.id ?? '';
		loading = true;
		geometryLoading = true;
		error = '';

		getPlot(id)
			.then((p) => {
				plot = p;
			})
			.catch(() => {
				error = 'Nie udało się załadować danych działki';
			})
			.finally(() => {
				loading = false;
			});

		getPlotGeometry(id)
			.then((geo) => {
				geometry = geo as unknown as GeoJSON.Feature;
			})
			.catch(() => {
				geometry = null;
			})
			.finally(() => {
				geometryLoading = false;
			});

		listingsLoading = true;
		getPlotListings(id)
			.then((data) => {
				activeListings = data.active;
				inactiveListings = data.inactive;
			})
			.catch(() => {
				activeListings = [];
				inactiveListings = [];
			})
			.finally(() => {
				listingsLoading = false;
			});

		getPlotBuildings(id)
			.then((data) => {
				buildings = data;
			})
			.catch(() => {
				buildings = null;
			});

		// Initial transactions fetch — reset to default filter on nav and
		// kick off one request. Subsequent filter changes are handled by
		// the dedicated effect below.
		transactionsLoading = true;
		getPlotTransactions(id, transactionsType)
			.then((data) => {
				transactions = data;
			})
			.catch(() => {
				transactions = [];
			})
			.finally(() => {
				transactionsLoading = false;
			});

		// Pre-computed claim value from roszczenia.csv (null if plot isn't in the sheet)
		roszczenieRow = null;
		getPlotRoszczenie(id)
			.then((row) => {
				roszczenieRow = row;
			})
			.catch(() => {
				roszczenieRow = null;
			});
	});

	// Refetch investments when plot id OR filters change
	$effect(() => {
		const id = $page.params.id ?? '';
		if (!id) return;
		investmentsLoading = true;
		getPlotInvestments(id, investmentsMonths, investmentsType, 1000)
			.then((data) => {
				investments = data;
			})
			.catch(() => {
				investments = [];
			})
			.finally(() => {
				investmentsLoading = false;
			});
	});

	// Refetch transactions when the type filter changes. The initial
	// fetch happens inside the main $effect above; this one only fires
	// on subsequent filter chip clicks, guarded so we don't double-fetch
	// on first mount.
	let lastTxFetchKey = '';
	$effect(() => {
		const id = $page.params.id ?? '';
		if (!id) return;
		const key = `${id}|${transactionsType}`;
		if (key === lastTxFetchKey) return;
		if (lastTxFetchKey === '') {
			// First run — main $effect handles the initial fetch.
			lastTxFetchKey = key;
			return;
		}
		lastTxFetchKey = key;
		transactionsLoading = true;
		getPlotTransactions(id, transactionsType)
			.then((data) => {
				transactions = data;
			})
			.catch(() => {
				transactions = [];
			})
			.finally(() => {
				transactionsLoading = false;
			});
	});

	function handlePinClick(kind: 'transaction' | 'listing' | 'investment', id: number) {
		const elementId = `${kind}-${id}`;
		const el = document.getElementById(elementId);
		if (el) {
			el.scrollIntoView({ behavior: 'smooth', block: 'center' });
			el.classList.add('ring-2', 'ring-blue-400');
			setTimeout(() => el.classList.remove('ring-2', 'ring-blue-400'), 1500);
		}
	}

	const INVESTMENT_TYPE_LABELS: Record<string, string> = {
		all: 'Wszystkie',
		pozwolenie: 'Pozwolenia',
		zgloszenie: 'Zgłoszenia',
	};

	const INVESTMENT_TYPE_BADGES: Record<string, { label: string; cls: string }> = {
		pozwolenie_budowa: { label: 'Pozwolenie', cls: 'bg-emerald-100 text-emerald-700' },
		zgloszenie: { label: 'Zgłoszenie', cls: 'bg-amber-100 text-amber-700' },
		warunki_zabudowy: { label: 'WZ', cls: 'bg-sky-100 text-sky-700' },
	};

	function formatArea(area: number | null): string {
		if (area === null) return '—';
		if (area >= 10_000) return `${(area / 10_000).toFixed(2)} ha`;
		return `${area.toFixed(0)} m²`;
	}

	function boolLabel(val: boolean | null): string {
		if (val === null) return '—';
		return val ? 'Tak' : 'Nie';
	}

	function distLabel(val: number | null): string {
		if (val === null) return '—';
		if (val >= 1000) return `${(val / 1000).toFixed(1)} km`;
		return `${val} m`;
	}

	function formatPrice(val: number | null | undefined): string {
		if (val == null || val === 0) return '—';
		return val.toLocaleString('pl-PL', { maximumFractionDigits: 0 }) + ' zł';
	}

	const RODZAJ_NIERUCHOMOSCI: Record<number, string> = {
		1: 'Niezabudowana',
		2: 'Zabudowana',
		3: 'Budynkowa',
		4: 'Lokalowa',
	};
	const RODZAJ_RYNKU: Record<number, string> = { 1: 'Pierwotny', 2: 'Wtórny' };
	const RODZAJ_TRANSAKCJI: Record<number, string> = { 1: 'Sprzedaż', 2: 'Zamiana', 3: 'Inne' };

</script>

<svelte:head>
	<title>{plot?.id_dzialki ?? 'Działka'} - Gruntify</title>
</svelte:head>

<div class="mx-auto w-full max-w-6xl px-6 py-6">
	<a href="/" class="mb-4 inline-block text-sm text-[var(--color-text-muted)] hover:underline">&larr; Wróć do wyszukiwania</a>

	{#if loading}
		<div class="flex items-center justify-center py-12">
			<div class="h-8 w-8 animate-spin rounded-full border-4 border-[var(--color-border)] border-t-[var(--color-primary)]"></div>
		</div>
	{:else if error}
		<div class="rounded-xl bg-red-50 p-6 text-red-700">{error}</div>
	{:else if plot}
		<h1 class="mb-1 text-2xl font-bold text-[var(--color-primary)]">{plot.id_dzialki}</h1>
		<p class="mb-6 text-[var(--color-text-muted)]">
			{[plot.miejscowosc, plot.ulica, plot.gmina].filter(Boolean).join(', ')}
		</p>

		<div class="mb-6">
			<PlotMap
				idDzialki={plot.id_dzialki}
				{geometry}
				{buildings}
				{transactions}
				listings={allListings}
				{investments}
				{roszczenieRow}
				loading={geometryLoading}
				onPinClick={handlePinClick}
			/>
		</div>

		<!-- Zrzuty mapy -->
		<section class="mb-6 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
			<h2 class="mb-4 text-sm font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">Zrzuty mapy</h2>
			<div class="grid gap-4 grid-cols-2">
				{#each [
					{ type: 'ortho', label: 'Ortofotomapa' },
					{ type: 'map', label: 'Mapa bazowa' },
				] as item}
					{@const url = `/api/plots/${encodeURIComponent($page.params.id ?? '')}/snapshot/${item.type}`}
					<div class="rounded-lg border border-[var(--color-border)] overflow-hidden">
						<img
							src={url}
							alt={item.label}
							loading="lazy"
							class="aspect-square w-full object-contain bg-gray-100"
						/>
						<div class="flex items-center justify-between px-3 py-2">
							<span class="text-sm font-medium">{item.label}</span>
							<a href={url} download="{$page.params.id}_{item.type}.jpg" class="text-xs text-blue-600 hover:underline">Pobierz</a>
						</div>
					</div>
				{/each}
			</div>
		</section>

		<!-- Basic info -->
		<section class="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
			<h2 class="mb-3 text-sm font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">Podstawowe</h2>
			<dl class="grid grid-cols-2 gap-2 text-sm md:grid-cols-4">
				<dt class="text-[var(--color-text-muted)]">Powierzchnia</dt>
				<dd>{formatArea(plot.area)}</dd>
				<dt class="text-[var(--color-text-muted)]">Typ</dt>
				<dd>{plot.lot_type ?? '—'}</dd>
				<dt class="text-[var(--color-text-muted)]">Budowlana</dt>
				<dd>{boolLabel(plot.is_buildable)}</dd>
				<dt class="text-[var(--color-text-muted)]">Budynki (BDOT)</dt>
				<dd>{plot.building_count_bdot ?? '—'}</dd>
			</dl>
		</section>

		{#if plot.zoning_symbol}
			<section class="mt-6 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
				<h2 class="mb-3 text-sm font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">Plan Ogólny Gminy</h2>
				<div class="flex items-start gap-3">
					<span class="rounded-full bg-blue-100 px-3 py-1 text-xs font-semibold text-blue-700">{plot.zoning_symbol}</span>
					{#if plot.zoning_name}
						<h3 class="text-base font-medium text-[var(--color-primary)]">{plot.zoning_name}</h3>
					{/if}
				</div>
				{#if (plot.zoning_max_height != null && plot.zoning_max_height > 0) || (plot.zoning_max_coverage != null && plot.zoning_max_coverage > 0) || (plot.zoning_min_green != null && plot.zoning_min_green > 0)}
					<ul class="mt-4 space-y-1.5 text-sm text-[var(--color-text-muted)]">
						{#if plot.zoning_max_height != null && plot.zoning_max_height > 0}
							<li>Maksymalna wysokość zabudowy: <strong class="text-[var(--color-primary)]">{plot.zoning_max_height} m</strong></li>
						{/if}
						{#if plot.zoning_max_coverage != null && plot.zoning_max_coverage > 0}
							<li>Maksymalny udział powierzchni zabudowy: <strong class="text-[var(--color-primary)]">{plot.zoning_max_coverage}%</strong></li>
						{/if}
						{#if plot.zoning_min_green != null && plot.zoning_min_green > 0}
							<li>Minimalna powierzchnia biologicznie czynna: <strong class="text-[var(--color-primary)]">{plot.zoning_min_green}%</strong></li>
						{/if}
					</ul>
				{/if}
			</section>
		{/if}

		{#if plot.is_nature_protected}
			<div class="mt-6 rounded-xl bg-amber-50 border border-amber-200 p-4 text-sm text-amber-800">
				Działka znajduje się w obszarze chronionym: {plot.nature_protection?.join(', ') ?? '—'}
			</div>
		{/if}

		<!-- Transakcje gruntowe w okolicy -->
		<details class="group mt-6 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)]" open>
			<summary class="flex cursor-pointer items-center justify-between px-5 py-4">
				<h2 class="text-lg font-semibold text-[var(--color-primary)]">
					Transakcje w okolicy
					{#if !transactionsLoading}
						<span class="ml-1 text-sm font-normal text-[var(--color-text-muted)]">({transactions.length})</span>
					{/if}
				</h2>
				<svg class="h-5 w-5 shrink-0 text-[var(--color-text-muted)] transition-transform group-open:rotate-180" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>
			</summary>
			<div class="px-5 pb-5">
				<div class="mb-3 flex flex-wrap items-center gap-2 text-xs">
					<span class="text-[var(--color-text-muted)]">Typ:</span>
					{#each [
						{ v: 'all' as TransactionType, label: 'Wszystkie' },
						{ v: 'gruntowe' as TransactionType, label: 'Gruntowe' },
						{ v: 'inne' as TransactionType, label: 'Inne' },
					] as opt}
						<button
							onclick={() => (transactionsType = opt.v)}
							class="rounded-full border px-3 py-1 transition-colors {transactionsType === opt.v ? 'border-[var(--color-primary)] bg-[var(--color-primary)] text-white' : 'border-[var(--color-border)] text-[var(--color-text-muted)] hover:bg-gray-50'}"
						>
							{opt.label}
						</button>
					{/each}
				</div>
				{#if transactionsLoading}
					<div class="flex items-center gap-2 text-sm text-[var(--color-text-muted)]">
						<div class="h-4 w-4 animate-spin rounded-full border-2 border-[var(--color-border)] border-t-[var(--color-primary)]"></div>
						Szukam transakcji...
					</div>
				{:else if transactions.length === 0}
					<p class="text-sm text-[var(--color-text-muted)]">Brak transakcji w okolicy</p>
				{:else}
					<div class="overflow-x-auto rounded-lg border border-[var(--color-border)]">
						<table class="w-full text-sm">
							<thead class="bg-[var(--color-surface)] text-left text-xs uppercase tracking-wider text-[var(--color-text-muted)]">
								<tr>
									<th class="px-3 py-2">Odl.</th>
									<th class="px-3 py-2">Data</th>
									<th class="px-3 py-2">Działka</th>
									<th class="px-3 py-2">Miejscowość</th>
									<th class="px-3 py-2">Pow.</th>
									<th class="px-3 py-2">Cena</th>
									<th class="px-3 py-2">Cena/m²</th>
									<th class="px-3 py-2">Rodzaj</th>
									<th class="px-3 py-2">Rynek</th>
								</tr>
							</thead>
							<tbody>
								{#each transactions as t, i (t.id)}
									<tr id="transaction-{t.id}" class="border-t border-[var(--color-border)] transition-shadow {i % 2 === 0 ? '' : 'bg-[var(--color-surface)]'}">
										<td class="whitespace-nowrap px-3 py-2 text-[var(--color-text-muted)]">{distLabel(t.distance_m)}</td>
										<td class="whitespace-nowrap px-3 py-2">{t.data_transakcji ?? '—'}</td>
										<td class="whitespace-nowrap px-3 py-2 font-mono text-xs">{t.id_dzialki ?? '—'}</td>
										<td class="px-3 py-2">{[t.miejscowosc, t.ulica].filter(Boolean).join(', ') || '—'}</td>
										<td class="whitespace-nowrap px-3 py-2 text-right">{t.powierzchnia_m2 != null ? formatArea(t.powierzchnia_m2) : '—'}</td>
										<td class="whitespace-nowrap px-3 py-2 text-right font-medium">{formatPrice(t.cena_do_analizy ?? t.cena_transakcji)}</td>
										<td class="whitespace-nowrap px-3 py-2 text-right">{t.cena_za_m2 != null ? formatPrice(t.cena_za_m2) : '—'}</td>
										<td class="whitespace-nowrap px-3 py-2">{t.rodzaj_nieruchomosci != null ? RODZAJ_NIERUCHOMOSCI[t.rodzaj_nieruchomosci] ?? t.rodzaj_nieruchomosci : '—'}</td>
										<td class="whitespace-nowrap px-3 py-2">{t.rodzaj_rynku != null ? RODZAJ_RYNKU[t.rodzaj_rynku] ?? t.rodzaj_rynku : '—'}</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				{/if}
			</div>
		</details>

		<!-- Ogłoszenia w okolicy -->
		<details class="group mt-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)]" open>
			<summary class="flex cursor-pointer items-center justify-between px-5 py-4">
				<h2 class="text-lg font-semibold text-[var(--color-primary)]">
					Ogłoszenia w okolicy
					{#if !listingsLoading}
						<span class="ml-1 text-sm font-normal text-[var(--color-text-muted)]">({activeListings.length + inactiveListings.length})</span>
					{/if}
				</h2>
				<svg class="h-5 w-5 shrink-0 text-[var(--color-text-muted)] transition-transform group-open:rotate-180" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>
			</summary>
			<div class="px-5 pb-5">
				{#if listingsLoading}
					<div class="flex items-center gap-2 text-sm text-[var(--color-text-muted)]">
						<div class="h-4 w-4 animate-spin rounded-full border-2 border-[var(--color-border)] border-t-[var(--color-primary)]"></div>
						Szukam ogłoszeń...
					</div>
				{:else if activeListings.length === 0 && inactiveListings.length === 0}
					<p class="text-sm text-[var(--color-text-muted)]">Brak ogłoszeń w okolicy</p>
				{:else}
					{#snippet listingCard(listing: Listing, faded: boolean)}
						<a
							id="listing-{listing.id}"
							href={listing.url ?? '#'}
							target="_blank"
							rel="noopener"
							class="block rounded-lg border border-[var(--color-border)] p-4 transition-shadow hover:shadow-md {faded ? 'opacity-60' : ''}"
						>
							<h3 class="truncate text-sm font-medium">{listing.name ?? 'Bez tytułu'}</h3>
							<div class="mt-1.5 flex flex-wrap gap-1.5">
								{#if listing.property_type}
									<span class="rounded-full bg-blue-100 px-2 py-0.5 text-[10px] text-blue-700">{listing.property_type}</span>
								{/if}
								{#if listing.deal_type}
									<span class="rounded-full px-2 py-0.5 text-[10px] {listing.deal_type.toLowerCase().includes('wynajem') ? 'bg-orange-100 text-orange-700' : 'bg-green-100 text-green-700'}">{listing.deal_type}</span>
								{/if}
								{#if listing.site}
									<span class="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] text-gray-500">{listing.site}</span>
								{/if}
							</div>
							<div class="mt-2 flex items-baseline justify-between">
								<span class="text-xs text-[var(--color-text-muted)]">
									{[listing.area ? listing.area + ' m²' : '', listing.city].filter(Boolean).join(' · ')}
								</span>
								{#if listing.price}
									<span class="font-bold text-[var(--color-primary)]">{Number(listing.price).toLocaleString('pl-PL')} zł</span>
								{/if}
							</div>
						</a>
					{/snippet}

					{#if activeListings.length > 0}
						<h3 class="mb-3 text-sm font-semibold uppercase tracking-wider text-green-700">Aktywne ({activeListings.length})</h3>
						<div class="grid gap-2 md:grid-cols-2">
							{#each activeListings as listing (listing.id)}
								{@render listingCard(listing, false)}
							{/each}
						</div>
					{/if}

					{#if inactiveListings.length > 0}
						<h3 class="mb-3 mt-4 text-sm font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">Nieaktywne ({inactiveListings.length})</h3>
						<div class="grid gap-2 md:grid-cols-2">
							{#each inactiveListings as listing (listing.id)}
								{@render listingCard(listing, true)}
							{/each}
						</div>
					{/if}
				{/if}
			</div>
		</details>

		<!-- Aktywność inwestycyjna (GUNB RWDZ) -->
		<details class="group mt-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)]" open>
			<summary class="flex cursor-pointer items-center justify-between px-5 py-4">
				<h2 class="text-lg font-semibold text-[var(--color-primary)]">
					Aktywność inwestycyjna
					{#if !investmentsLoading}
						<span class="ml-1 text-sm font-normal text-[var(--color-text-muted)]">({investments.length})</span>
					{/if}
				</h2>
				<svg class="h-5 w-5 shrink-0 text-[var(--color-text-muted)] transition-transform group-open:rotate-180" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>
			</summary>
			<div class="px-5 pb-5">
				<div class="mb-3 flex flex-wrap items-center gap-2 text-xs">
					<span class="text-[var(--color-text-muted)]">Typ:</span>
					{#each ['all', 'pozwolenie', 'zgloszenie'] as t}
						<button
							onclick={() => (investmentsType = t as InvestmentType)}
							class="rounded-full border px-3 py-1 transition-colors {investmentsType === t ? 'border-[var(--color-primary)] bg-[var(--color-primary)] text-white' : 'border-[var(--color-border)] text-[var(--color-text-muted)] hover:bg-gray-50'}"
						>
							{INVESTMENT_TYPE_LABELS[t]}
						</button>
					{/each}
					<span class="ml-3 text-[var(--color-text-muted)]">Okres:</span>
					<select
						bind:value={investmentsMonths}
						class="rounded-md border border-[var(--color-border)] bg-white px-2 py-1 text-xs"
					>
						<option value={12}>12 mies.</option>
						<option value={24}>24 mies.</option>
						<option value={36}>36 mies.</option>
						<option value={60}>5 lat</option>
					</select>
				</div>

				{#if investmentsLoading}
					<div class="flex items-center gap-2 text-sm text-[var(--color-text-muted)]">
						<div class="h-4 w-4 animate-spin rounded-full border-2 border-[var(--color-border)] border-t-[var(--color-primary)]"></div>
						Szukam inwestycji...
					</div>
				{:else if investments.length === 0}
					<p class="text-sm text-[var(--color-text-muted)]">Brak pozwoleń ani zgłoszeń w okolicy</p>
				{:else}
					<div class="grid gap-2 md:grid-cols-2">
						{#each investments as inv (inv.id)}
							{@const badge = inv.typ ? INVESTMENT_TYPE_BADGES[inv.typ] : null}
							<div id="investment-{inv.id}" class="rounded-lg border border-[var(--color-border)] p-4 transition-shadow">
								<div class="mb-1.5 flex flex-wrap items-center gap-1.5">
									{#if badge}
										<span class="rounded-full px-2 py-0.5 text-[10px] font-medium {badge.cls}">{badge.label}</span>
									{/if}
									{#if inv.kategoria}
										<span class="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] text-gray-600">kat. {inv.kategoria}</span>
									{/if}
									{#if inv.distance_m != null}
										<span class="ml-auto text-[10px] text-[var(--color-text-muted)]">{distLabel(inv.distance_m)}</span>
									{/if}
								</div>
								{#if inv.opis}
									<p class="text-sm text-[var(--color-primary)]">{inv.opis}</p>
								{/if}
								<div class="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-[var(--color-text-muted)]">
									{#if inv.data_decyzji}
										<span>Decyzja: {inv.data_decyzji}</span>
									{:else if inv.data_wniosku}
										<span>Wniosek: {inv.data_wniosku}</span>
									{/if}
									{#if inv.miejscowosc}
										<span>{inv.miejscowosc}</span>
									{/if}
									{#if inv.organ}
										<span class="truncate">{inv.organ}</span>
									{/if}
								</div>
							</div>
						{/each}
					</div>
				{/if}
			</div>
		</details>

	{/if}
</div>
