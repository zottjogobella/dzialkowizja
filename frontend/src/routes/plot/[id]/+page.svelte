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
		getPlotArgumentacja,
		getPlotMpzp,
		type ListingsResponse,
		type InvestmentType,
		type TransactionType,
		type RoszczenieRow,
		type ArgumentacjaRow,
		type MpzpFeature,
		type MpzpResponse,
	} from '$lib/api/plots';
	import type { PlotDetail, Listing, Transaction, Investment } from '$lib/types/plot';
	import PlotMap from '$lib/components/PlotMap.svelte';
	import InvestmentDetailsModal from '$lib/components/InvestmentDetailsModal.svelte';

	let plot = $state<PlotDetail | null>(null);
	let loading = $state(true);
	let error = $state('');
	let geometry = $state<GeoJSON.Feature | null>(null);
	let geometryLoading = $state(true);
	let activeListings = $state<Listing[]>([]);
	let inactiveListings = $state<Listing[]>([]);
	let listingsLoading = $state(true);
	let buildings = $state<GeoJSON.FeatureCollection | null>(null);
	// Full datasets fetched once per plot, filtered client-side by chip toggle.
	let allTransactions = $state<Transaction[]>([]);
	let transactionsLoading = $state(true);
	let transactionsType = $state<TransactionType>('all');
	let allInvestments = $state<Investment[]>([]);
	let investmentsLoading = $state(true);
	let investmentsType = $state<InvestmentType>('all');
	let investmentsMonths = $state(24);

	// Client-side filtering — chip changes are instant, no refetch.
	const transactions = $derived(
		transactionsType === 'all'
			? allTransactions
			: transactionsType === 'gruntowe'
				? allTransactions.filter(t => t.rodzaj_nieruchomosci === 1 || t.rodzaj_nieruchomosci === 2)
				: allTransactions.filter(t => t.rodzaj_nieruchomosci !== 1 && t.rodzaj_nieruchomosci !== 2),
	);
	const investments = $derived(
		investmentsType === 'all'
			? allInvestments
			: investmentsType === 'pozwolenie'
				? allInvestments.filter(i => i.typ === 'pozwolenie_budowa')
				: allInvestments.filter(i => i.typ === 'zgloszenie'),
	);
	let roszczenieRow = $state<RoszczenieRow | null>(null);
	let argumentacjaRow = $state<ArgumentacjaRow | null>(null);
	let selectedInvestment = $state<Investment | null>(null);
	let mpzpFeatures = $state<MpzpFeature[]>([]);
	let mpzpLoading = $state(true);
	let mpzpUpstreamError = $state(false);

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

		// Pre-computed claim value from roszczenia.csv (null if plot isn't in the sheet)
		roszczenieRow = null;
		argumentacjaRow = null;
		getPlotRoszczenie(id)
			.then((row) => {
				roszczenieRow = row;
			})
			.catch(() => {
				roszczenieRow = null;
			});
		getPlotArgumentacja(id)
			.then((row) => {
				argumentacjaRow = row;
			})
			.catch(() => {
				argumentacjaRow = null;
			});

		// MPZP designation via KI WMS GetFeatureInfo at the plot centroid.
		mpzpFeatures = [];
		mpzpUpstreamError = false;
		mpzpLoading = true;
		getPlotMpzp(id)
			.then((r: MpzpResponse | null) => {
				mpzpFeatures = r?.features ?? [];
				mpzpUpstreamError = !!r?.upstream_error;
			})
			.catch(() => {
				mpzpFeatures = [];
				mpzpUpstreamError = true;
			})
			.finally(() => {
				mpzpLoading = false;
			});
	});

	// Investments — fetch ALL types once per (id, months). Type filtering
	// is client-side via the $derived above so chip clicks are instant.
	let lastInvFetchKey = '';
	$effect(() => {
		const id = $page.params.id ?? '';
		const key = `${id}|${investmentsMonths}`;
		if (!id || key === lastInvFetchKey) return;
		lastInvFetchKey = key;
		investmentsLoading = true;
		getPlotInvestments(id, investmentsMonths, 'all')
			.then((data) => {
				allInvestments = data;
			})
			.catch(() => {
				allInvestments = [];
			})
			.finally(() => {
				investmentsLoading = false;
			});
	});

	// Transactions — fetch ALL types once per plot. Type filtering is
	// client-side via the $derived above so chip clicks are instant.
	let lastTxFetchKey = '';
	$effect(() => {
		const id = $page.params.id ?? '';
		if (!id || id === lastTxFetchKey) return;
		lastTxFetchKey = id;
		transactionsLoading = true;
		getPlotTransactions(id, 'all')
			.then((data) => {
				allTransactions = data;
			})
			.catch(() => {
				allTransactions = [];
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

	function ekwSearchUrl(kw: string): string {
		const dept = kw.split('/')[0] ?? '';
		return `https://przegladarka-ekw.ms.gov.pl/eukw_prz/KsiegiWieczyste/wyszukiwanieKW?komunikaty=true&kod=${encodeURIComponent(dept)}&isEnglish=false`;
	}

	// Owner strings in the CSV are "name;;type" pairs, sometimes chained for
	// multi-owner plots ("name1;;type1;;name2;;type2"). Pair them up so the UI
	// can render each owner as a single line with a muted type suffix.
	const OWNER_TYPE_TOKENS = new Set(['os prawna', 'os fizyczna', 'panstwo']);
	function parseOwners(raw: string): { name: string; type: string | null }[] {
		const parts = raw.split(';;').map(p => p.trim()).filter(Boolean);
		const out: { name: string; type: string | null }[] = [];
		for (let i = 0; i < parts.length; i++) {
			const name = parts[i];
			const next = parts[i + 1];
			if (next && OWNER_TYPE_TOKENS.has(next)) {
				out.push({ name, type: next });
				i += 1;
			} else {
				out.push({ name, type: null });
			}
		}
		return out;
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

		{#if roszczenieRow}
			<!-- Księga wieczysta + właściciel (tylko dla działek z arkusza) -->
			<section class="mb-6 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
				<h2 class="mb-3 text-sm font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">Księga wieczysta i właściciel</h2>
				<dl class="grid grid-cols-1 gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
					<div>
						<dt class="text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">Numer KW</dt>
						<dd class="text-[var(--color-primary)]">
							{#if roszczenieRow.kw}
								<a
									href={ekwSearchUrl(roszczenieRow.kw)}
									target="_blank"
									rel="noopener"
									class="font-mono hover:underline"
								>{roszczenieRow.kw}</a>
							{:else}
								<span class="inline-flex items-center gap-1.5 text-[var(--color-text-muted)]">
									<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
									Dane ukryte
								</span>
							{/if}
						</dd>
					</div>
					<div class="sm:col-span-2">
						<dt class="text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">Właściciel</dt>
						<dd class="text-[var(--color-primary)]">
							{#if roszczenieRow.entities}
								{#each parseOwners(roszczenieRow.entities) as owner}
									<div>
										<span>{owner.name}</span>
										{#if owner.type}
											<span class="ml-1 text-[11px] text-[var(--color-text-muted)]">({owner.type})</span>
										{/if}
									</div>
								{/each}
							{:else}
								<span class="inline-flex items-center gap-1.5 text-[var(--color-text-muted)]">
									<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
									Dane ukryte
								</span>
							{/if}
						</dd>
					</div>
				</dl>
			</section>
		{/if}

		{#if argumentacjaRow}
			<section class="mb-6 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
				<div class="mb-3 flex items-center justify-between">
					<h2 class="text-sm font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">Argumentacja wyceny</h2>
					{#if argumentacjaRow.pewnosc_kategoria}
						<span class="rounded-full px-2.5 py-0.5 text-[11px] font-semibold
							{argumentacjaRow.pewnosc_kategoria === 'WYSOKA' ? 'bg-green-100 text-green-800' :
							 argumentacjaRow.pewnosc_kategoria === 'SREDNIA' ? 'bg-yellow-100 text-yellow-800' :
							 'bg-red-100 text-red-800'}">
							Pewność: {argumentacjaRow.pewnosc_0_100}/100 ({argumentacjaRow.pewnosc_kategoria})
						</span>
					{/if}
				</div>

				<dl class="mb-3 grid grid-cols-2 gap-x-6 gap-y-1.5 text-sm sm:grid-cols-4">
					{#if argumentacjaRow.cena_ensemble != null}
						<div>
							<dt class="text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">Cena ensemble</dt>
							<dd class="font-medium text-[var(--color-primary)]">{argumentacjaRow.cena_ensemble.toFixed(0)} zł/m²</dd>
						</div>
					{/if}
					{#if argumentacjaRow.wartosc_total != null}
						<div>
							<dt class="text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">Wartość całkowita</dt>
							<dd class="font-medium text-[var(--color-primary)]">{argumentacjaRow.wartosc_total.toLocaleString('pl-PL', { maximumFractionDigits: 0 })} zł</dd>
						</div>
					{/if}
					{#if argumentacjaRow.cena_m2_roszczenie_orig != null}
						<div>
							<dt class="text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">Cena roszczenia</dt>
							<dd class="font-medium text-[var(--color-primary)]">{argumentacjaRow.cena_m2_roszczenie_orig.toFixed(0)} zł/m²</dd>
						</div>
					{/if}
					{#if argumentacjaRow.wartosc_roszczenia_orig != null}
						<div>
							<dt class="text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">Wartość roszczenia</dt>
							<dd class="font-medium text-[var(--color-primary)]">{argumentacjaRow.wartosc_roszczenia_orig.toLocaleString('pl-PL', { maximumFractionDigits: 0 })} zł</dd>
						</div>
					{/if}
					{#if argumentacjaRow.segment}
						<div>
							<dt class="text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">Segment</dt>
							<dd class="text-[var(--color-primary)]">{argumentacjaRow.segment}</dd>
						</div>
					{/if}
					{#if argumentacjaRow.procent_pow != null}
						<div>
							<dt class="text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">Pokrycie buforem</dt>
							<dd class="text-[var(--color-primary)]">{argumentacjaRow.procent_pow.toFixed(1)}%</dd>
						</div>
					{/if}
				</dl>

				{#if argumentacjaRow.argumenty.length > 0}
					<div class="space-y-2">
						{#each argumentacjaRow.argumenty as arg}
							<div class="flex gap-3 rounded-lg bg-[var(--color-background)] p-2.5 text-sm">
								<span class="shrink-0 rounded bg-[var(--color-border)] px-1.5 py-0.5 text-[11px] font-mono font-semibold text-[var(--color-text-muted)]">{arg.waga}</span>
								<span class="text-[var(--color-primary)]">{arg.text}</span>
							</div>
						{/each}
					</div>
				{/if}
			</section>
		{/if}

		<!-- MPZP - przeznaczenie z planu zagospodarowania -->
		<section class="mb-6 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
			<div class="mb-3 flex items-center justify-between">
				<h2 class="text-sm font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">Plan zagospodarowania</h2>
				<span class="text-[11px] text-[var(--color-text-muted)]">
					źródło: <a href="https://integracja.gugik.gov.pl/" target="_blank" rel="noopener" class="hover:underline">GUGiK KI MPZP</a>
				</span>
			</div>
			{#if mpzpLoading}
				<div class="flex items-center gap-2 text-sm text-[var(--color-text-muted)]">
					<div class="h-4 w-4 animate-spin rounded-full border-2 border-[var(--color-border)] border-t-[var(--color-primary)]"></div>
					Pobieram informacje o planie...
				</div>
			{:else if mpzpUpstreamError && mpzpFeatures.length === 0}
				<p class="text-sm text-[var(--color-text-muted)]">Nie udało się pobrać informacji z GUGiK. Spróbuj ponownie później.</p>
			{:else if mpzpFeatures.length === 0}
				<p class="text-sm text-[var(--color-text-muted)]">Działka nie jest objęta żadnym planem zarejestrowanym w krajowej integracji.</p>
			{:else}
				<div class="space-y-3">
					{#each mpzpFeatures as feat, i (i)}
						<div class="rounded-lg border border-[var(--color-border)] p-3 text-sm">
							{#if feat.tytul_planu}
								<div class="font-medium text-[var(--color-primary)]">{feat.tytul_planu}</div>
							{/if}
							{#if feat.przeznaczenie}
								<div class="mt-1 text-[var(--color-primary)]"><span class="text-[var(--color-text-muted)]">Przeznaczenie:</span> {feat.przeznaczenie}</div>
							{/if}
							{#if feat.uchwala}
								<div class="mt-1.5 text-[12px] text-[var(--color-primary)]">{feat.uchwala}</div>
							{/if}
							<div class="mt-1.5 flex flex-wrap gap-x-4 gap-y-0.5 text-[11px] text-[var(--color-text-muted)]">
								{#if feat.status}
									<span>Status: <span class="text-[var(--color-primary)]">{feat.status}</span></span>
								{/if}
								{#if feat.data_uchwalenia}
									<span>Obowiązuje od: <span class="text-[var(--color-primary)]">{feat.data_uchwalenia}</span></span>
								{/if}
								{#if feat.obowiazuje_do}
									<span>do: <span class="text-[var(--color-primary)]">{feat.obowiazuje_do}</span></span>
								{/if}
								{#if feat.typ_planu}
									<span>Typ: <span class="text-[var(--color-primary)]">{feat.typ_planu}</span></span>
								{/if}
							</div>
							{#if feat.opis}
								<p class="mt-2 whitespace-pre-wrap text-[var(--color-primary)]">{feat.opis}</p>
							{/if}
							{#if feat.dokument_przystepujacy}
								<div class="mt-1.5 text-[11px] text-[var(--color-text-muted)]">{feat.dokument_przystepujacy}</div>
							{/if}
							<div class="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px]">
								{#if feat.link_do_uchwaly}
									<a href={feat.link_do_uchwaly} target="_blank" rel="noopener" class="text-blue-600 hover:underline">Dokument uchwały</a>
								{/if}
								{#if feat.rysunek_url}
									<a href={feat.rysunek_url} target="_blank" rel="noopener" class="text-blue-600 hover:underline">Rysunek planu</a>
								{/if}
							</div>
						</div>
					{/each}
				</div>
			{/if}
		</section>

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
							<button
								type="button"
								id="investment-{inv.id}"
								onclick={() => (selectedInvestment = inv)}
								class="w-full rounded-lg border border-[var(--color-border)] p-4 text-left transition-colors hover:border-[var(--color-primary)] hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]"
							>
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
								<div class="mt-2 text-[11px] font-medium text-[var(--color-primary)]">Więcej informacji →</div>
							</button>
						{/each}
					</div>
				{/if}
			</div>
		</details>

		<InvestmentDetailsModal
			investment={selectedInvestment}
			onClose={() => (selectedInvestment = null)}
		/>
	{/if}
</div>
