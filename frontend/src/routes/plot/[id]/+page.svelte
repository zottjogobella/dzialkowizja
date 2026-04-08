<script lang="ts">
	import { page } from '$app/stores';
	import { getPlot, getPlotGeometry, getPlotListings, getPlotBuildings, getPlotTransactions, type ListingsResponse } from '$lib/api/plots';
	import type { PlotDetail, Listing, Transaction } from '$lib/types/plot';
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

		transactionsLoading = true;
		getPlotTransactions(id)
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

	function formatPrice(val: number | null): string {
		if (val === null) return '—';
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

<div class="mx-auto w-full max-w-4xl px-6 py-6">
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
			<PlotMap {geometry} {buildings} loading={geometryLoading} />
		</div>

		<div class="grid gap-6 md:grid-cols-2">
			<!-- Basic info -->
			<section class="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
				<h2 class="mb-3 text-sm font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">Podstawowe</h2>
				<dl class="grid grid-cols-2 gap-2 text-sm">
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

			<!-- Zoning -->
			<section class="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
				<h2 class="mb-3 text-sm font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">Zagospodarowanie</h2>
				<dl class="grid grid-cols-2 gap-2 text-sm">
					<dt class="text-[var(--color-text-muted)]">Symbol</dt>
					<dd>{plot.zoning_symbol ?? '—'}</dd>
					<dt class="text-[var(--color-text-muted)]">Nazwa</dt>
					<dd class="col-span-2">{plot.zoning_name ?? '—'}</dd>
					<dt class="text-[var(--color-text-muted)]">Max wysokość</dt>
					<dd>{plot.zoning_max_height ?? '—'} m</dd>
					<dt class="text-[var(--color-text-muted)]">Max zabudowa</dt>
					<dd>{plot.zoning_max_coverage ?? '—'}%</dd>
				</dl>
			</section>

			<!-- Utilities -->
			<section class="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
				<h2 class="mb-3 text-sm font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">Media</h2>
				<dl class="grid grid-cols-2 gap-2 text-sm">
					<dt class="text-[var(--color-text-muted)]">Woda</dt>
					<dd>{boolLabel(plot.has_water)}</dd>
					<dt class="text-[var(--color-text-muted)]">Kanalizacja</dt>
					<dd>{boolLabel(plot.has_sewage)}</dd>
					<dt class="text-[var(--color-text-muted)]">Gaz</dt>
					<dd>{boolLabel(plot.has_gas)}</dd>
					<dt class="text-[var(--color-text-muted)]">Prąd</dt>
					<dd>{boolLabel(plot.has_electric)}</dd>
					<dt class="text-[var(--color-text-muted)]">Ogrzewanie</dt>
					<dd>{boolLabel(plot.has_heating)}</dd>
					<dt class="text-[var(--color-text-muted)]">Telekom</dt>
					<dd>{boolLabel(plot.has_telecom)}</dd>
				</dl>
			</section>

			<!-- Distances -->
			<section class="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
				<h2 class="mb-3 text-sm font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">Odległości</h2>
				<dl class="grid grid-cols-2 gap-2 text-sm">
					<dt class="text-[var(--color-text-muted)]">Droga</dt>
					<dd>{distLabel(plot.nearest_road_distance_m)} ({plot.nearest_road_name ?? '—'})</dd>
					<dt class="text-[var(--color-text-muted)]">Szkoła</dt>
					<dd>{distLabel(plot.nearest_education_m)}</dd>
					<dt class="text-[var(--color-text-muted)]">Zdrowie</dt>
					<dd>{distLabel(plot.nearest_healthcare_m)}</dd>
					<dt class="text-[var(--color-text-muted)]">Sklep</dt>
					<dd>{distLabel(plot.nearest_shopping_m)}</dd>
					<dt class="text-[var(--color-text-muted)]">Transport</dt>
					<dd>{distLabel(plot.nearest_transport_m)}</dd>
				</dl>
			</section>
		</div>

		{#if plot.is_nature_protected}
			<div class="mt-6 rounded-xl bg-amber-50 border border-amber-200 p-4 text-sm text-amber-800">
				Działka znajduje się w obszarze chronionym: {plot.nature_protection?.join(', ') ?? '—'}
			</div>
		{/if}

		<!-- Transakcje gruntowe w okolicy -->
		<details class="group mt-6 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)]" open>
			<summary class="flex cursor-pointer items-center justify-between px-5 py-4">
				<h2 class="text-lg font-semibold text-[var(--color-primary)]">
					Transakcje gruntowe
					{#if !transactionsLoading}
						<span class="ml-1 text-sm font-normal text-[var(--color-text-muted)]">({transactions.length})</span>
					{/if}
				</h2>
				<svg class="h-5 w-5 shrink-0 text-[var(--color-text-muted)] transition-transform group-open:rotate-180" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>
			</summary>
			<div class="px-5 pb-5">
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
									<tr class="border-t border-[var(--color-border)] {i % 2 === 0 ? '' : 'bg-[var(--color-surface)]'}">
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
	{/if}
</div>
