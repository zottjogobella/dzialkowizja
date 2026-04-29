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
		getPlotCenySrednie,
		type ListingsResponse,
		type InvestmentType,
		type TransactionType,
		type RoszczenieRow,
		type ArgumentacjaRow,
		type MpzpFeature,
		type MpzpResponse,
		type CenySrednieResponse,
	} from '$lib/api/plots';
	import type { PlotDetail, Listing, Transaction, Investment } from '$lib/types/plot';
	import PlotMap from '$lib/components/PlotMap.svelte';
	import InvestmentDetailsModal from '$lib/components/InvestmentDetailsModal.svelte';
	import PdfReportModal from '$lib/components/PdfReportModal.svelte';
	import { restrictions } from '$lib/stores/restrictions';

	// Whole-section / sub-section / per-field hiding driven by the admin
	// "Ukryte pola" panel. Wrapping every visible element in {#if !hidden(...)}
	// keeps the layout from leaving "Dane ukryte" stubs behind — a hidden
	// section vanishes entirely, and parent sections collapse to nothing
	// when *all* their children are hidden.
	const hidden = (key: string) => $restrictions.has(key);

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
	// Toggle: show transactions the RCN cleanup flagged as outlier/do_wyceny=0.
	// Default false (hide). Flipping this refetches since the filter lives
	// server-side in the /transactions endpoint.
	let showOutliers = $state(false);
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
	let cenySrednie = $state<CenySrednieResponse | null>(null);
	let cenySrednieLoading = $state(true);
	let selectedInvestment = $state<Investment | null>(null);
	let showPdfModal = $state(false);
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

		// Average RCN prices for the plot's gmina + powiat.
		cenySrednie = null;
		cenySrednieLoading = true;
		getPlotCenySrednie(id)
			.then((data) => {
				cenySrednie = data;
			})
			.catch(() => {
				cenySrednie = null;
			})
			.finally(() => {
				cenySrednieLoading = false;
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

	// Transactions — fetch ALL types once per (plot, showOutliers). Type
	// filtering is client-side via the $derived above so chip clicks are
	// instant, but the outlier filter lives server-side so a refetch is
	// needed when the toggle flips.
	let lastTxFetchKey = '';
	$effect(() => {
		const id = $page.params.id ?? '';
		const key = `${id}|${showOutliers ? 1 : 0}`;
		if (!id || key === lastTxFetchKey) return;
		lastTxFetchKey = key;
		transactionsLoading = true;
		getPlotTransactions(id, 'all', showOutliers)
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

	// CSV entities field has several shapes we must render:
	//   "NAME;;TYPE"                                  — no PESEL (193k rows)
	//   "NAME;PESEL;TYPE"                             — with PESEL (290k rows)
	//   multi-owner: same shapes joined by NEWLINES   — browsers collapse the
	//     newlines to spaces, so we must split before rendering
	// TYPE is one of KNOWN_TYPES. We strip PESEL (never shown) and keep just
	// name + type for display.
	const OWNER_TYPE_TOKENS = new Set(['os prawna', 'os fizyczna', 'panstwo']);
	type Owner = { name: string; pesel: string | null; type: string | null };
	function parseOwners(raw: string): Owner[] {
		const out: Owner[] = [];
		// Split on newlines first (multi-owner rows are one-per-line).
		for (const line of raw.split(/\r?\n/)) {
			const trimmed = line.trim();
			if (!trimmed) continue;
			// Collapse ";;" → ";" so a single split handles both shapes.
			const parts = trimmed.split(/;+/).map(p => p.trim()).filter(Boolean);
			if (parts.length === 0) continue;
			// Locate the type token. If missing, fall back to showing the raw
			// line as a nameless owner so we never drop data.
			const typeIdx = parts.findIndex(p => OWNER_TYPE_TOKENS.has(p.toLowerCase()));
			if (typeIdx === -1) {
				out.push({ name: trimmed, pesel: null, type: null });
				continue;
			}
			const type = parts[typeIdx];
			// Everything before the type is name + (optional) PESEL/NIP. If
			// the trailing token is 8–11 digits it's a PESEL (os fizyczna)
			// or NIP (os prawna) — surface it under the name.
			let nameTokens = parts.slice(0, typeIdx);
			let pesel: string | null = null;
			if (
				nameTokens.length > 1 &&
				/^\d{8,11}$/.test(nameTokens[nameTokens.length - 1])
			) {
				pesel = nameTokens[nameTokens.length - 1];
				nameTokens = nameTokens.slice(0, -1);
			}
			const name = nameTokens.join(' ').trim();
			out.push({ name: name || trimmed, pesel, type });
		}
		// Fallback: no newlines, no parseable content — show raw.
		if (out.length === 0 && raw.trim()) {
			out.push({ name: raw.trim(), pesel: null, type: null });
		}
		return out;
	}

	// Maps tab label → DOM id of the target section. "Wycena" has no dedicated
	// section so it scrolls to argumentacja (where valuation data lives).
	const TAB_TARGETS: Record<string, string> = {
		'Mapa': 'sec-mapa',
		'Wycena': 'sec-argumentacja',
		'Księga wieczysta': 'sec-ksiega-wieczysta',
		'Argumentacja': 'sec-argumentacja',
		'Transakcje': 'sec-transakcje',
		'Aktywność': 'sec-aktywnosc',
	};
	function scrollToTab(label: string) {
		const id = TAB_TARGETS[label];
		if (!id) return;
		const el = document.getElementById(id);
		if (!el) return;
		el.scrollIntoView({ behavior: 'smooth', block: 'start' });
		history.replaceState(null, '', `#${id}`);
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

<div class="flex flex-col gap-[14px]">
	{#if loading}
		<div class="glass-card flex items-center justify-center py-16">
			<div class="h-8 w-8 animate-spin rounded-full border-4 border-[var(--color-faint)] border-t-[var(--color-accent)]"></div>
		</div>
	{:else if error}
		<div class="glass-card p-6 text-red-700">{error}</div>
	{:else if plot}
		<!-- Title card -->
		<div class="glass-card" style="padding: 24px 30px 20px;">
			<div class="eyebrow mb-2.5">&mdash; DZIAŁKA EWIDENCYJNA</div>
			<div class="flex flex-wrap items-baseline gap-x-5 gap-y-2">
				<div class="font-mono text-[30px] font-medium" style="letter-spacing: -0.2px;">{plot.id_dzialki}</div>
				{#if !hidden('header.location')}
					<div class="font-serif text-[22px] font-medium italic text-[var(--color-mute)]">
						{[plot.miejscowosc, plot.ulica, plot.gmina].filter(Boolean).join(', ') || ''}
					</div>
				{/if}
				{#if !hidden('header.teryt_badge') || !hidden('header.gmina_badge')}
					<div class="ml-auto flex flex-wrap gap-1.5 font-mono text-[11px] text-[var(--color-mute)]" style="letter-spacing: 0.8px;">
						{#if plot.id_dzialki && !hidden('header.teryt_badge')}
							{@const parts = plot.id_dzialki.split('.')}
							{@const teryt = parts[0]?.split('_')[0] ?? ''}
							<span class="rounded-[20px] border border-[var(--color-glass-border)] bg-[var(--color-glass)] px-2.5 py-1">TERYT {teryt}</span>
						{/if}
						{#if plot.gmina && !hidden('header.gmina_badge')}
							<span class="rounded-[20px] border border-[var(--color-glass-border)] bg-[var(--color-glass)] px-2.5 py-1">{plot.gmina}</span>
						{/if}
					</div>
				{/if}
			</div>
			{#if true}
			{@const TAB_SECTIONS = {
				// A tab vanishes when the section it would scroll to is hidden.
				// "Wycena" and "Argumentacja" both scroll to argumentacja so they
				// share section.argumentacja.
				'Mapa': 'section.map',
				'Wycena': 'section.argumentacja',
				'Księga wieczysta': 'section.kw_card',
				'Argumentacja': 'section.argumentacja',
				'Transakcje': 'section.transactions',
				'Aktywność': 'section.investments',
			} as Record<string, string>}
			{@const visibleTabs = ['Mapa', 'Wycena', 'Księga wieczysta', 'Argumentacja', 'Transakcje', 'Aktywność']
				.filter(t => !hidden(TAB_SECTIONS[t]))}
			{#if (!hidden('header.tabs') && visibleTabs.length > 0) || !hidden('header.pdf_button')}
				<!-- Tabs -->
				<div class="mt-4 flex flex-wrap items-center gap-1 font-mono text-[11px] uppercase" style="letter-spacing: 1.2px;">
					{#if !hidden('header.tabs')}
						{#each visibleTabs as tab, i}
							<button
								type="button"
								onclick={() => scrollToTab(tab)}
								class="cursor-pointer rounded-[20px] px-3.5 py-1.5 transition-colors
									{i === 0 ? 'bg-[var(--color-ink)] font-semibold text-white' : 'border border-[var(--color-glass-border)] text-[var(--color-mute)] hover:bg-[var(--color-glass)]'}"
							>{tab}</button>
						{/each}
					{/if}
					{#if !hidden('header.pdf_button')}
						<button
							onclick={() => (showPdfModal = true)}
							class="ml-auto flex cursor-pointer items-center gap-1.5 rounded-[20px] bg-[var(--color-accent)] px-4 py-1.5 font-mono text-[11px] font-semibold text-white transition-opacity hover:opacity-90"
							style="letter-spacing: 1.2px;"
						>
							<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
								<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
							</svg>
							RAPORT PDF
						</button>
					{/if}
				</div>
			{/if}
			{/if}
		</div>

		<!-- Map card -->
		{#if !hidden('section.map')}
			<div id="sec-mapa" class="glass-card overflow-hidden p-3.5">
				<div class="overflow-hidden rounded-xl">
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
			</div>
		{/if}

		<!-- KW + Argumentacja row -->
		{@const showKwCard = roszczenieRow && roszczenieRow.source === 'sheet' && !hidden('section.kw_card')}
		{@const showArgCard = argumentacjaRow && !hidden('section.argumentacja')}
		{#if showKwCard || showArgCard}
			<div class="grid gap-[14px]" style="grid-template-columns: {showKwCard && showArgCard ? '1fr 2fr' : '1fr'};">
				{#if showKwCard && roszczenieRow}
					{@const basicFacts: Array<[string, string, string]> = [
						['Powierzchnia', formatArea(plot.area), 'plot.area'],
						['Budowlana', boolLabel(plot.is_buildable), 'plot.is_buildable'],
						['Typ', plot.lot_type ?? '—', 'plot.lot_type'],
						['Budynki (BDOT)', String(plot.building_count_bdot ?? '—'), 'plot.building_count_bdot'],
					]}
					{@const visibleFacts = basicFacts.filter(([, , key]) => !hidden(key))}
					<div id="sec-ksiega-wieczysta" class="glass-card px-6 py-5">
						<div class="eyebrow mb-3.5" style="letter-spacing: 1.5px;">&mdash; KSIĘGA WIECZYSTA I WŁAŚCICIEL</div>
						{#if !hidden('roszczenia.kw')}
							<!-- KW number -->
							<div class="glass-chip mb-3 px-4 py-3.5">
								<div class="font-mono text-[11px] text-[var(--color-mute)]">NUMER KW</div>
								{#if roszczenieRow.kw}
									<a
										href={ekwSearchUrl(roszczenieRow.kw)}
										target="_blank"
										rel="noopener"
										class="mt-1 block font-mono text-[15px] font-medium hover:underline"
									>{roszczenieRow.kw}</a>
								{:else}
									<div class="mt-1 font-mono text-[15px] text-[var(--color-mute)]">—</div>
								{/if}
							</div>
						{/if}
						{#if !hidden('roszczenia.entities')}
							<!-- Owner -->
							<div class="glass-chip mb-4 px-4 py-3.5">
								<div class="font-mono text-[11px] text-[var(--color-mute)]">WŁAŚCICIEL</div>
								{#if roszczenieRow.entities}
									{#each parseOwners(roszczenieRow.entities) as owner}
										<div class="mt-2 first:mt-1">
											<div class="font-serif text-[17px] font-medium">
												{owner.name}
												{#if owner.type}
													<span class="ml-1 text-[11px] text-[var(--color-mute)]">({owner.type})</span>
												{/if}
											</div>
											{#if owner.pesel}
												<div class="font-mono text-[11px] text-[var(--color-mute)]">
													{owner.pesel.length === 11 ? 'PESEL' : owner.pesel.length === 10 ? 'NIP' : 'REGON'}: {owner.pesel}
												</div>
											{/if}
										</div>
									{/each}
								{:else}
									<div class="mt-1 font-serif text-[17px] text-[var(--color-mute)]">—</div>
								{/if}
							</div>
						{/if}
						{#if !hidden('section.basic_facts') && visibleFacts.length > 0}
							<!-- Basic facts -->
							<div class="eyebrow mb-2" style="font-size: 9.5px; letter-spacing: 1.2px;">PODSTAWOWE</div>
							{#each visibleFacts as [label, value], i}
								<div class="flex justify-between border-b border-dashed border-[var(--color-faint)] py-[7px] text-xs {i === visibleFacts.length - 1 ? 'border-b-0' : ''}">
									<span class="text-[var(--color-mute)]">{label}</span>
									<span class="font-mono font-medium">{value}</span>
								</div>
							{/each}
						{/if}
					</div>
				{/if}

				{#if showArgCard && argumentacjaRow}
					<div id="sec-argumentacja" class="glass-card px-6 py-5">
						<div class="mb-3 flex items-baseline justify-between">
							<div class="eyebrow" style="letter-spacing: 1.5px;">&mdash; ARGUMENTACJA WYCENY</div>
							{#if argumentacjaRow.pewnosc_kategoria && !hidden('argumentacja.pewnosc')}
								<span class="glass-pill">
									{argumentacjaRow.pewnosc_kategoria} &middot; {argumentacjaRow.pewnosc_0_100}/100
								</span>
							{/if}
						</div>
						{#if argumentacjaRow.segment && !hidden('argumentacja.segment')}
							<div class="mb-2.5 flex justify-between font-mono text-[11px] text-[var(--color-mute)]" style="letter-spacing: 1.2px;">
								<span>SEGMENT &middot; {argumentacjaRow.segment}</span>
								{#if argumentacjaRow.procent_pow != null}
									<span>POKRYCIE &middot; {argumentacjaRow.procent_pow.toFixed(1)}%</span>
								{/if}
							</div>
						{/if}
						{#if !hidden('argumentacja.argumenty') && argumentacjaRow.argumenty.length > 0}
							<!-- Argumenty list -->
							<div>
								{#each argumentacjaRow.argumenty as arg, i}
									<div class="grid gap-3.5 border-b border-dashed border-[var(--color-faint)] py-[9px] text-xs leading-relaxed {i === argumentacjaRow.argumenty.length - 1 ? 'border-b-0' : ''}" style="grid-template-columns: 36px 1fr;">
										<div class="pt-0.5 font-mono text-[11px] font-semibold text-[var(--color-accent)]">{arg.waga}</div>
										<div>{arg.text}</div>
									</div>
								{/each}
							</div>
						{/if}
					</div>
				{/if}

			</div>
		{/if}

		<!-- MPZP -->
		{#if !hidden('section.mpzp')}
			<div class="glass-card px-6 py-5">
				<div class="mb-3 flex items-center justify-between">
					<div class="eyebrow" style="letter-spacing: 1.5px;">&mdash; PLAN ZAGOSPODAROWANIA</div>
					{#if !hidden('mpzp.zrodlo')}
						<span class="font-mono text-[11px] text-[var(--color-mute)]">
							źródło: <a href="https://integracja.gugik.gov.pl/" target="_blank" rel="noopener" class="text-[var(--color-accent)] hover:underline">GUGiK KI MPZP</a>
						</span>
					{/if}
				</div>
				{#if mpzpLoading}
					<div class="flex items-center gap-2 text-sm text-[var(--color-mute)]">
						<div class="h-4 w-4 animate-spin rounded-full border-2 border-[var(--color-faint)] border-t-[var(--color-accent)]"></div>
						Pobieram informacje o planie…
					</div>
				{:else if mpzpUpstreamError && mpzpFeatures.length === 0}
					<p class="text-sm text-[var(--color-mute)]">Nie udało się pobrać informacji z GUGiK. Spróbuj ponownie później.</p>
				{:else if mpzpFeatures.length === 0}
					<p class="text-sm text-[var(--color-mute)]">Działka nie jest objęta żadnym planem zarejestrowanym w krajowej integracji.</p>
				{:else}
					<div class="space-y-3">
						{#each mpzpFeatures as feat, i (i)}
							<div class="glass-chip p-3.5 text-sm">
								{#if feat.tytul_planu && !hidden('mpzp.tytul')}
									<div class="font-medium">{feat.tytul_planu}</div>
								{/if}
								{#if feat.przeznaczenie && !hidden('mpzp.przeznaczenie')}
									<div class="mt-1"><span class="text-[var(--color-mute)]">Przeznaczenie:</span> {feat.przeznaczenie}</div>
								{/if}
								{#if feat.uchwala && !hidden('mpzp.uchwala')}
									<div class="mt-1.5 text-xs">{feat.uchwala}</div>
								{/if}
								{#if !hidden('mpzp.meta') && (feat.status || feat.data_uchwalenia || feat.typ_planu)}
									<div class="mt-1.5 flex flex-wrap gap-x-4 gap-y-0.5 text-[11px] text-[var(--color-mute)]">
										{#if feat.status}
											<span>Status: <span class="text-[var(--color-ink)]">{feat.status}</span></span>
										{/if}
										{#if feat.data_uchwalenia}
											<span>Obowiązuje od: <span class="text-[var(--color-ink)]">{feat.data_uchwalenia}</span></span>
										{/if}
										{#if feat.typ_planu}
											<span>Typ: <span class="text-[var(--color-ink)]">{feat.typ_planu}</span></span>
										{/if}
									</div>
								{/if}
								{#if feat.opis && !hidden('mpzp.opis')}
									<p class="mt-2 whitespace-pre-wrap">{feat.opis}</p>
								{/if}
								{#if !hidden('mpzp.linki') && (feat.link_do_uchwaly || feat.rysunek_url)}
									<div class="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px]">
										{#if feat.link_do_uchwaly}
											<a href={feat.link_do_uchwaly} target="_blank" rel="noopener" class="text-[var(--color-accent)] hover:underline">Dokument uchwaly</a>
										{/if}
										{#if feat.rysunek_url}
											<a href={feat.rysunek_url} target="_blank" rel="noopener" class="text-[var(--color-accent)] hover:underline">Rysunek planu</a>
										{/if}
									</div>
								{/if}
							</div>
						{/each}
					</div>
				{/if}
			</div>
		{/if}

		<!-- Zoning -->
		{#if plot.zoning_symbol && !hidden('section.zoning')}
			{@const showH = plot.zoning_max_height != null && plot.zoning_max_height > 0 && !hidden('zoning.constraint.max_height')}
			{@const showC = plot.zoning_max_coverage != null && plot.zoning_max_coverage > 0 && !hidden('zoning.constraint.max_coverage')}
			{@const showG = plot.zoning_min_green != null && plot.zoning_min_green > 0 && !hidden('zoning.constraint.min_green')}
			<div class="glass-card px-6 py-5">
				<div class="mb-3 flex items-center justify-between">
					<div class="eyebrow" style="letter-spacing: 1.5px;">&mdash; PLAN OGÓLNY GMINY</div>
					{#if plot.pog_status && !hidden('zoning.status')}
						<span class="rounded-[20px] px-3 py-1 font-mono text-[11px] font-semibold" style="letter-spacing: 0.8px;
							{plot.pog_status.includes('obowiązujący')
								? 'background: rgba(61,90,42,0.10); color: var(--color-accent); border: 1px solid rgba(61,90,42,0.25);'
								: 'background: rgba(184,134,42,0.10); color: var(--color-amber); border: 1px solid rgba(184,134,42,0.25);'}"
						>{plot.pog_status.toUpperCase()}</span>
					{/if}
				</div>
				<div class="flex items-start gap-3">
					{#if !hidden('zoning.symbol')}
						<span class="glass-pill">{plot.zoning_symbol}</span>
					{/if}
					{#if plot.zoning_name && !hidden('zoning.name')}
						<span class="font-serif text-base font-medium">{plot.zoning_name}</span>
					{/if}
				</div>
				{#if showH || showC || showG}
					<div class="mt-4 space-y-1.5 text-sm text-[var(--color-mute)]">
						{#if showH}
							<div>Maksymalna wysokość zabudowy: <strong class="text-[var(--color-ink)]">{plot.zoning_max_height} m</strong></div>
						{/if}
						{#if showC}
							<div>Maks. udział pow. zabudowy: <strong class="text-[var(--color-ink)]">{plot.zoning_max_coverage}%</strong></div>
						{/if}
						{#if showG}
							<div>Min. pow. biologicznie czynna: <strong class="text-[var(--color-ink)]">{plot.zoning_min_green}%</strong></div>
						{/if}
					</div>
				{/if}
			</div>
		{/if}

		{#if plot.is_nature_protected && !hidden('section.nature_protection')}
			<div class="glass-card border-[var(--color-amber)] px-6 py-4 text-sm" style="background: rgba(184,134,42,0.08);">
				Działka znajduje się w obszarze chronionym: {plot.nature_protection?.join(', ') ?? '—'}
			</div>
		{/if}

		<!-- Średnie ceny RCN dla gminy i powiatu -->
		{#if !hidden('section.average_prices')}
		<div id="sec-ceny-srednie" class="glass-card px-6 py-5">
			<div class="mb-3 flex items-baseline justify-between">
				<div class="eyebrow" style="letter-spacing: 1.5px;">
					&mdash; ŚREDNIE CENY W OKOLICY
				</div>
				{#if cenySrednie}
					<div class="font-mono text-[11px] text-[var(--color-mute)]">
						gmina {cenySrednie.gmina_teryt} · powiat {cenySrednie.powiat_teryt}
					</div>
				{/if}
			</div>
			{#if cenySrednieLoading}
				<div class="flex items-center gap-2 text-sm text-[var(--color-mute)]">
					<div class="h-4 w-4 animate-spin rounded-full border-2 border-[var(--color-faint)] border-t-[var(--color-accent)]"></div>
					Ładuję średnie ceny…
				</div>
			{:else if !cenySrednie || (cenySrednie.gmina.length === 0 && cenySrednie.powiat_total.length === 0)}
				<p class="text-sm text-[var(--color-mute)]">Brak średnich cen dla tej gminy/powiatu</p>
			{:else}
				{#snippet cenyBlock(title: string, rows: Array<{ rodzaj_nieruchomosci: number; rodzaj_nazwa: string | null; liczba_transakcji: number; cena_za_m2_srednia: number | null; cena_za_m2_mediana: number | null; cena_za_m2_q1: number | null; cena_za_m2_q3: number | null; rok_min: number | null; rok_max: number | null }>)}
					<div>
						<div class="mb-2 font-mono text-[11px] font-semibold uppercase text-[var(--color-mute)]" style="letter-spacing: 1.2px;">{title}</div>
						{#if rows.length === 0}
							<p class="text-[11px] italic text-[var(--color-mute)]">Brak danych</p>
						{:else}
							<div class="overflow-hidden rounded-xl border border-[var(--color-glass-border)]">
								<div class="grid items-center bg-[var(--color-glass)] px-3 py-2 font-mono text-[11px] text-[var(--color-mute)]" style="grid-template-columns: 1.6fr 55px 85px 85px 85px 85px 55px; letter-spacing: 1.2px;">
									<div>RODZAJ</div><div class="text-right">N</div><div class="text-right">Q1</div><div class="text-right">MEDIANA</div><div class="text-right">ŚREDNIA</div><div class="text-right">Q3</div><div class="text-right">LATA</div>
								</div>
								{#each rows as r}
									<div class="grid items-center border-t border-[var(--color-faint)] px-3 py-2 font-mono text-[11px]" style="grid-template-columns: 1.6fr 55px 85px 85px 85px 85px 55px;">
										<div class="truncate text-[11px]" style="font-family: var(--font-sans);">{r.rodzaj_nazwa ?? `(rodzaj ${r.rodzaj_nieruchomosci})`}</div>
										<div class="text-right text-[var(--color-mute)]">{r.liczba_transakcji?.toLocaleString('pl-PL') ?? '—'}</div>
										<div class="text-right text-[var(--color-mute)]">{r.cena_za_m2_q1 != null ? formatPrice(r.cena_za_m2_q1) : '—'}</div>
										<div class="text-right">{r.cena_za_m2_mediana != null ? formatPrice(r.cena_za_m2_mediana) : '—'}</div>
										<div class="text-right font-semibold">{r.cena_za_m2_srednia != null ? formatPrice(r.cena_za_m2_srednia) : '—'}</div>
										<div class="text-right text-[var(--color-mute)]">{r.cena_za_m2_q3 != null ? formatPrice(r.cena_za_m2_q3) : '—'}</div>
										<div class="text-right text-[11px] text-[var(--color-mute)]">{r.rok_min && r.rok_max ? (r.rok_min === r.rok_max ? r.rok_min : `${r.rok_min}-${r.rok_max % 100}`) : '—'}</div>
									</div>
								{/each}
							</div>
						{/if}
					</div>
				{/snippet}

				<div class="grid gap-4 md:grid-cols-2">
					{#if !hidden('average_prices.gmina')}
						{@render cenyBlock('Gmina', cenySrednie.gmina)}
					{/if}
					{#if !hidden('average_prices.powiat_total')}
						{@render cenyBlock('Powiat (ogółem)', cenySrednie.powiat_total)}
					{/if}
				</div>

				{#if cenySrednie.powiat.length > 0 && !hidden('average_prices.powiat_segments')}
					<div class="mt-5">
						<div class="mb-2 font-mono text-[11px] font-semibold uppercase text-[var(--color-mute)]" style="letter-spacing: 1.2px;">Powiat — per segment rynku</div>
						<div class="overflow-hidden rounded-xl border border-[var(--color-glass-border)]">
							<div class="grid items-center bg-[var(--color-glass)] px-3 py-2 font-mono text-[11px] text-[var(--color-mute)]" style="grid-template-columns: 1.2fr 1.2fr 55px 85px 85px 85px 85px 55px; letter-spacing: 1.2px;">
								<div>RODZAJ</div><div>SEGMENT</div><div class="text-right">N</div><div class="text-right">Q1</div><div class="text-right">MEDIANA</div><div class="text-right">ŚREDNIA</div><div class="text-right">Q3</div><div class="text-right">LATA</div>
							</div>
							{#each cenySrednie.powiat as r}
								<div class="grid items-center border-t border-[var(--color-faint)] px-3 py-2 font-mono text-[11px]" style="grid-template-columns: 1.2fr 1.2fr 55px 85px 85px 85px 85px 55px;">
									<div class="truncate text-[11px]" style="font-family: var(--font-sans);">{r.rodzaj_nazwa ?? `(${r.rodzaj_nieruchomosci})`}</div>
									<div class="truncate text-[11px] text-[var(--color-mute)]" style="font-family: var(--font-sans);">{r.segment_rynku}</div>
									<div class="text-right text-[var(--color-mute)]">{r.liczba_transakcji?.toLocaleString('pl-PL') ?? '—'}</div>
									<div class="text-right text-[var(--color-mute)]">{r.cena_za_m2_q1 != null ? formatPrice(r.cena_za_m2_q1) : '—'}</div>
									<div class="text-right">{r.cena_za_m2_mediana != null ? formatPrice(r.cena_za_m2_mediana) : '—'}</div>
									<div class="text-right font-semibold">{r.cena_za_m2_srednia != null ? formatPrice(r.cena_za_m2_srednia) : '—'}</div>
									<div class="text-right text-[var(--color-mute)]">{r.cena_za_m2_q3 != null ? formatPrice(r.cena_za_m2_q3) : '—'}</div>
									<div class="text-right text-[11px] text-[var(--color-mute)]">{r.rok_min && r.rok_max ? (r.rok_min === r.rok_max ? r.rok_min : `${r.rok_min}-${r.rok_max % 100}`) : '—'}</div>
								</div>
							{/each}
						</div>
					</div>
				{/if}
			{/if}
		</div>
		{/if}

		<!-- Transakcje w okolicy -->
		{#if !hidden('section.transactions')}
		<div id="sec-transakcje" class="glass-card px-6 py-5">
			<div class="mb-3 flex items-baseline justify-between gap-3">
				<div class="eyebrow" style="letter-spacing: 1.5px;">
					&mdash; TRANSAKCJE W OKOLICY{#if !transactionsLoading} ({transactions.length}){/if}
				</div>
				{#if !hidden('transactions.show_outliers') || !hidden('transactions.type_chips')}
					<div class="flex flex-wrap items-center gap-3 font-mono text-[11px]">
						{#if !hidden('transactions.show_outliers')}
							<label class="flex cursor-pointer items-center gap-1.5 whitespace-nowrap text-[11px] text-[var(--color-mute)]">
								<input
									type="checkbox"
									bind:checked={showOutliers}
									class="h-3 w-3 accent-[var(--color-accent)]"
								/>
								POKAŻ ODRZUCONE
							</label>
						{/if}
						{#if !hidden('transactions.type_chips')}
							<div class="flex gap-1">
							{#each [
								{ v: 'all' as TransactionType, label: 'Wszystkie' },
								{ v: 'gruntowe' as TransactionType, label: 'Gruntowe' },
								{ v: 'inne' as TransactionType, label: 'Inne' },
							] as opt}
								<button
									onclick={() => (transactionsType = opt.v)}
									class="cursor-pointer rounded-[20px] px-3 py-1.5 transition-colors
										{transactionsType === opt.v
											? 'bg-[var(--color-ink)] font-semibold text-white'
											: 'border border-[var(--color-glass-border)] bg-[var(--color-glass)] text-[var(--color-mute)]'}"
								>
									{opt.label}
								</button>
							{/each}
							</div>
						{/if}
					</div>
				{/if}
			</div>
			{#if transactionsLoading}
				<div class="flex items-center gap-2 text-sm text-[var(--color-mute)]">
					<div class="h-4 w-4 animate-spin rounded-full border-2 border-[var(--color-faint)] border-t-[var(--color-accent)]"></div>
					Szukam transakcji…
				</div>
			{:else if transactions.length === 0}
				<p class="text-sm text-[var(--color-mute)]">Brak transakcji w okolicy</p>
			{:else}
				{@const showCena = !hidden('transactions.col.price')}
				{@const showCenaM2 = !hidden('transactions.col.price_m2')}
				{@const txCols = [
					'55px', '80px', '1.2fr', '1.5fr', '65px',
					...(showCena ? ['90px'] : []),
					...(showCenaM2 ? ['85px'] : []),
					'110px', '70px',
				].join(' ')}
				<div class="overflow-hidden rounded-xl border border-[var(--color-glass-border)]">
					<!-- Header -->
					<div class="grid items-center bg-[var(--color-glass)] px-4 py-2.5 font-mono text-[11px] text-[var(--color-mute)]" style="grid-template-columns: {txCols}; letter-spacing: 1.2px;">
						<div>ODL.</div><div>DATA</div><div>DZIAŁKA</div><div>MIEJSCOWOŚĆ</div><div class="text-right">POW.</div>
						{#if showCena}<div class="text-right">CENA</div>{/if}
						{#if showCenaM2}<div class="text-right">ZŁ/M²</div>{/if}
						<div>RODZAJ</div><div>RYNEK</div>
					</div>
					{#each transactions as t, i (t.id)}
						{@const rejected = t.outlier === 1 || t.do_wyceny === 0}
						<div
							id="transaction-{t.id}"
							class="grid items-center border-t border-[var(--color-faint)] px-4 py-2.5 font-mono text-[11.5px] transition-shadow {rejected ? 'opacity-50 line-through decoration-[var(--color-mute)]' : ''}"
							style="grid-template-columns: {txCols};"
							title={rejected ? (t.outlier === 1 ? 'Odrzucona: wartość odstająca (outlier)' : 'Odrzucona: nie nadaje się do wyceny') : ''}
						>
							<div class="text-[var(--color-mute)]">{distLabel(t.distance_m)}</div>
							<div>{t.data_transakcji ?? '—'}</div>
							<div class="font-medium">{t.id_dzialki ?? '—'}</div>
							<div class="truncate text-[11px] text-[var(--color-mute)]" style="font-family: var(--font-sans);">{[t.miejscowosc, t.ulica].filter(Boolean).join(', ') || '—'}</div>
							<div class="text-right">{t.powierzchnia_m2 != null ? formatArea(t.powierzchnia_m2) : '—'}</div>
							{#if showCena}
								<div class="text-right">{formatPrice(t.cena_do_analizy ?? t.cena_transakcji)}</div>
							{/if}
							{#if showCenaM2}
								<div class="text-right text-[var(--color-mute)]">{t.cena_za_m2 != null ? formatPrice(t.cena_za_m2) : '—'}</div>
							{/if}
							<div class="text-[11px] text-[var(--color-mute)]" style="font-family: var(--font-sans);">{t.rodzaj_nieruchomosci != null ? RODZAJ_NIERUCHOMOSCI[t.rodzaj_nieruchomosci] ?? t.rodzaj_nieruchomosci : '—'}</div>
							<div class="text-[11px]" style="font-family: var(--font-sans); color: {t.rodzaj_rynku === 1 ? 'var(--color-accent)' : t.rodzaj_rynku === 2 ? 'var(--color-amber)' : 'var(--color-mute)'};">
								{t.rodzaj_rynku != null ? RODZAJ_RYNKU[t.rodzaj_rynku] ?? t.rodzaj_rynku : '—'}
							</div>
						</div>
					{/each}
				</div>
			{/if}
		</div>
		{/if}

		<!-- Ogłoszenia w okolicy -->
		{#if !hidden('section.listings')}
		<div class="glass-card px-6 py-5">
			<div class="eyebrow mb-3" style="letter-spacing: 1.5px;">
				&mdash; OGŁOSZENIA W OKOLICY{#if !listingsLoading} ({activeListings.length + inactiveListings.length}){/if}
			</div>
			{#if listingsLoading}
				<div class="flex items-center gap-2 text-sm text-[var(--color-mute)]">
					<div class="h-4 w-4 animate-spin rounded-full border-2 border-[var(--color-faint)] border-t-[var(--color-accent)]"></div>
					Szukam ogłoszeń…
				</div>
			{:else if activeListings.length === 0 && inactiveListings.length === 0}
				<p class="text-sm text-[var(--color-mute)]">Brak ogłoszeń w okolicy</p>
			{:else}
				{#snippet listingCard(listing: Listing, faded: boolean)}
					<a
						id="listing-{listing.id}"
						href={listing.url ?? '#'}
						target="_blank"
						rel="noopener"
						class="glass-chip block p-4 transition-[filter] hover:brightness-[1.02] {faded ? 'opacity-60' : ''}"
					>
						<h3 class="truncate text-sm font-medium">{listing.name ?? 'Bez tytułu'}</h3>
						<div class="mt-1.5 flex flex-wrap gap-1.5">
							{#if listing.property_type}
								<span class="glass-pill" style="font-size: 11px; padding: 3px 8px;">{listing.property_type}</span>
							{/if}
							{#if listing.deal_type}
								<span class="glass-pill" style="font-size: 11px; padding: 3px 8px; {listing.deal_type.toLowerCase().includes('wynajem') ? 'background: rgba(184,134,42,0.1); color: var(--color-amber); border-color: rgba(184,134,42,0.25);' : ''}">{listing.deal_type}</span>
							{/if}
							{#if listing.site && !hidden('listings.card.site')}
								<span class="rounded-[20px] border border-[var(--color-glass-border)] bg-[var(--color-glass)] px-2 py-0.5 font-mono text-[11px] text-[var(--color-mute)]">{listing.site}</span>
							{/if}
						</div>
						<div class="mt-2 flex items-baseline justify-between">
							<span class="text-[11px] text-[var(--color-mute)]">
								{[listing.area ? listing.area + ' m2' : '', listing.city].filter(Boolean).join(' · ')}
							</span>
							{#if listing.price && !hidden('listings.card.price')}
								<span class="font-mono text-sm font-medium">{Number(listing.price).toLocaleString('pl-PL')} zł</span>
							{/if}
						</div>
					</a>
				{/snippet}

				{#if activeListings.length > 0 && !hidden('listings.active')}
					<div class="mb-2 font-mono text-[11px] font-semibold uppercase text-[var(--color-accent)]" style="letter-spacing: 1.2px;">Aktywne ({activeListings.length})</div>
					<div class="grid gap-2 md:grid-cols-2">
						{#each activeListings as listing (listing.id)}
							{@render listingCard(listing, false)}
						{/each}
					</div>
				{/if}

				{#if inactiveListings.length > 0 && !hidden('listings.inactive')}
					<div class="mb-2 mt-4 font-mono text-[11px] font-semibold uppercase text-[var(--color-mute)]" style="letter-spacing: 1.2px;">Nieaktywne ({inactiveListings.length})</div>
					<div class="grid gap-2 md:grid-cols-2">
						{#each inactiveListings as listing (listing.id)}
							{@render listingCard(listing, true)}
						{/each}
					</div>
				{/if}
			{/if}
		</div>
		{/if}

		<!-- Aktywność inwestycyjna -->
		{#if !hidden('section.investments')}
		<div id="sec-aktywnosc" class="glass-card px-6 py-5">
			<div class="mb-3 flex items-baseline justify-between">
				<div class="eyebrow" style="letter-spacing: 1.5px;">
					&mdash; AKTYWNOŚĆ INWESTYCYJNA{#if !investmentsLoading} ({investments.length}){/if}
				</div>
				{#if !hidden('investments.type_chips') || !hidden('investments.time_window')}
					<div class="flex flex-wrap items-center gap-2">
						{#if !hidden('investments.type_chips')}
							<div class="flex gap-1 font-mono text-[11px]">
								{#each ['all', 'pozwolenie', 'zgloszenie'] as t}
									<button
										onclick={() => (investmentsType = t as InvestmentType)}
										class="cursor-pointer rounded-[20px] px-3 py-1.5 transition-colors
											{investmentsType === t
												? 'bg-[var(--color-ink)] font-semibold text-white'
												: 'border border-[var(--color-glass-border)] bg-[var(--color-glass)] text-[var(--color-mute)]'}"
									>
										{INVESTMENT_TYPE_LABELS[t]}
									</button>
								{/each}
							</div>
						{/if}
						{#if !hidden('investments.time_window')}
							<select
								bind:value={investmentsMonths}
								class="rounded-[var(--r-sm)] border border-[var(--color-glass-border)] bg-[var(--color-glass)] px-2 py-1 font-mono text-[11px] text-[var(--color-mute)]"
							>
								<option value={12}>12 mies.</option>
								<option value={24}>24 mies.</option>
								<option value={36}>36 mies.</option>
								<option value={60}>5 lat</option>
							</select>
						{/if}
					</div>
				{/if}
			</div>
			{#if investmentsLoading}
				<div class="flex items-center gap-2 text-sm text-[var(--color-mute)]">
					<div class="h-4 w-4 animate-spin rounded-full border-2 border-[var(--color-faint)] border-t-[var(--color-accent)]"></div>
					Szukam inwestycji…
				</div>
			{:else if investments.length === 0}
				<p class="text-sm text-[var(--color-mute)]">Brak pozwoleń ani zgłoszeń w okolicy</p>
			{:else}
				<div class="grid gap-2">
					{#each investments as inv (inv.id)}
						{@const badge = inv.typ ? INVESTMENT_TYPE_BADGES[inv.typ] : null}
						<button
							type="button"
							id="investment-{inv.id}"
							onclick={() => (selectedInvestment = inv)}
							class="glass-chip grid w-full cursor-pointer items-center gap-4 p-4 text-left transition-[filter] hover:brightness-[1.02] focus:outline-none"
							style="grid-template-columns: 100px 1fr 1fr 110px;"
						>
							<div>
								{#if badge}
									<span class="inline-block rounded-[20px] px-2.5 py-1 font-mono text-[11px] font-semibold text-white" style="background: {badge.cls.includes('emerald') ? 'var(--color-accent)' : 'var(--color-amber)'}; letter-spacing: 0.8px;">
										{badge.label.toUpperCase()}
									</span>
								{/if}
							</div>
							<div>
								{#if inv.opis}
									<p class="text-sm">{inv.opis}</p>
								{/if}
								<div class="mt-1 font-mono text-[11px] text-[var(--color-mute)]">
									{inv.data_decyzji ?? inv.data_wniosku ?? ''}
									{#if inv.distance_m != null} &middot; {distLabel(inv.distance_m)}{/if}
								</div>
							</div>
							<div class="font-mono text-[11px] text-[var(--color-mute)]">
								{inv.miejscowosc ?? ''} {hidden('investments.card.organ') ? '' : (inv.organ ?? '')}
							</div>
							<div class="text-right font-mono text-[11px] text-[var(--color-accent)]">Więcej informacji &rarr;</div>
						</button>
					{/each}
				</div>
			{/if}
		</div>
		{/if}

		<InvestmentDetailsModal
			investment={selectedInvestment}
			onClose={() => (selectedInvestment = null)}
		/>

		<PdfReportModal
			open={showPdfModal}
			{plot}
			{roszczenieRow}
			{argumentacjaRow}
			{mpzpFeatures}
			{transactions}
			{activeListings}
			{inactiveListings}
			{investments}
			onClose={() => (showPdfModal = false)}
		/>
	{/if}
</div>
