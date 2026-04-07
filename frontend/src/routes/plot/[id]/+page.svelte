<script lang="ts">
	import { page } from '$app/stores';
	import { getPlot } from '$lib/api/plots';
	import type { PlotDetail } from '$lib/types/plot';

	let plot = $state<PlotDetail | null>(null);
	let loading = $state(true);
	let error = $state('');

	$effect(() => {
		const id = $page.params.id ?? '';
		loading = true;
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
</script>

<svelte:head>
	<title>{plot?.id_dzialki ?? 'Działka'} - Działkowizja</title>
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
	{/if}
</div>
