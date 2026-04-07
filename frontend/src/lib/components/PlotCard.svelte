<script lang="ts">
	import type { PlotSummary } from '$lib/types/plot';

	let { plot }: { plot: PlotSummary } = $props();

	function formatArea(area: number | null): string {
		if (area === null) return '—';
		if (area >= 10_000) return `${(area / 10_000).toFixed(2)} ha`;
		return `${area.toFixed(0)} m²`;
	}
</script>

<a
	href="/plot/{encodeURIComponent(plot.id_dzialki)}"
	class="block rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 transition-shadow hover:shadow-md"
>
	<div class="mb-2 flex items-start justify-between">
		<h3 class="font-semibold text-[var(--color-primary)]">{plot.id_dzialki}</h3>
		{#if plot.is_buildable}
			<span class="rounded-full bg-green-100 px-2 py-0.5 text-xs text-green-700">Budowlana</span>
		{/if}
	</div>

	{#if plot.miejscowosc || plot.ulica}
		<p class="mb-1 text-sm text-[var(--color-text-muted)]">
			{[plot.miejscowosc, plot.ulica].filter(Boolean).join(', ')}
		</p>
	{/if}

	<div class="mt-3 flex gap-4 text-sm text-[var(--color-text-muted)]">
		<span>{formatArea(plot.area)}</span>
		{#if plot.lot_type}
			<span>{plot.lot_type}</span>
		{/if}
		{#if plot.zoning_symbol}
			<span>{plot.zoning_symbol}</span>
		{/if}
	</div>
</a>
