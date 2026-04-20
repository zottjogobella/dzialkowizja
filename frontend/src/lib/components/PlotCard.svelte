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
	class="glass-chip block p-5 transition-[filter] hover:brightness-[1.02]"
>
	<div class="mb-2 flex items-start justify-between">
		<h3 class="font-mono text-sm font-medium">{plot.id_dzialki}</h3>
		{#if plot.is_buildable}
			<span class="glass-pill" style="font-size: 9px; padding: 3px 8px;">BUDOWLANA</span>
		{/if}
	</div>

	{#if plot.miejscowosc || plot.ulica}
		<p class="mb-1 font-serif text-sm italic text-[var(--color-mute)]">
			{[plot.miejscowosc, plot.ulica].filter(Boolean).join(', ')}
		</p>
	{/if}

	<div class="mt-3 flex gap-4 font-mono text-[11px] text-[var(--color-mute)]">
		<span>{formatArea(plot.area)}</span>
		{#if plot.lot_type}
			<span>{plot.lot_type}</span>
		{/if}
		{#if plot.zoning_symbol}
			<span>{plot.zoning_symbol}</span>
		{/if}
	</div>
</a>
