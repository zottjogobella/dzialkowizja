<script lang="ts">
	import type { Investment } from '$lib/types/plot';

	interface Props {
		investment: Investment | null;
		onClose: () => void;
	}

	let { investment, onClose }: Props = $props();

	const TYPE_LABELS: Record<string, string> = {
		pozwolenie_budowa: 'Pozwolenie na budowę',
		zgloszenie: 'Zgłoszenie',
		warunki_zabudowy: 'Warunki zabudowy',
	};

	const TYPE_BADGES: Record<string, string> = {
		pozwolenie_budowa: 'bg-emerald-100 text-emerald-700',
		zgloszenie: 'bg-amber-100 text-amber-700',
		warunki_zabudowy: 'bg-sky-100 text-sky-700',
	};

	function distLabel(val: number | null): string {
		if (val === null) return '—';
		if (val >= 1000) return `${(val / 1000).toFixed(1)} km`;
		return `${val} m`;
	}

	function kubaturaLabel(val: number | null): string {
		if (val === null) return '—';
		return `${val.toLocaleString('pl-PL', { maximumFractionDigits: 1 })} m³`;
	}

	/** Pretty, stable ordering of raw RWDZ keys so the dump is readable. */
	function rawEntries(raw: Record<string, unknown> | null): [string, string][] {
		if (!raw) return [];
		return Object.entries(raw)
			.filter(([, v]) => v !== null && v !== undefined && String(v).trim() !== '')
			.map(([k, v]) => [k, typeof v === 'object' ? JSON.stringify(v) : String(v)] as [string, string])
			.sort((a, b) => a[0].localeCompare(b[0]));
	}

	let rawOpen = $state(false);

	function handleKey(e: KeyboardEvent) {
		if (e.key === 'Escape') onClose();
	}
</script>

<svelte:window onkeydown={handleKey} />

{#if investment}
	{@const typ = investment.typ ?? ''}
	{@const typLabel = TYPE_LABELS[typ] ?? typ}
	{@const badgeCls = TYPE_BADGES[typ] ?? 'bg-gray-100 text-gray-700'}

	<!-- Backdrop -->
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="fixed inset-0 z-40 bg-black/40"
		onclick={onClose}
	></div>

	<!-- Modal panel -->
	<div
		class="fixed left-1/2 top-1/2 z-50 flex max-h-[90vh] w-[min(42rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 flex-col rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-xl"
		role="dialog"
		aria-modal="true"
		aria-labelledby="investment-modal-title"
	>
		<div class="flex items-start justify-between gap-4 border-b border-[var(--color-border)] px-5 py-4">
			<div class="min-w-0 flex-1">
				<div class="mb-1.5 flex flex-wrap items-center gap-1.5">
					{#if typ}
						<span class="rounded-full px-2 py-0.5 text-[11px] font-medium {badgeCls}">{typLabel}</span>
					{/if}
					{#if investment.status}
						<span class="rounded-full bg-gray-100 px-2 py-0.5 text-[11px] text-gray-600">{investment.status}</span>
					{/if}
					{#if investment.kategoria}
						<span class="rounded-full bg-gray-100 px-2 py-0.5 text-[11px] text-gray-600">kat. {investment.kategoria}</span>
					{/if}
				</div>
				<h2 id="investment-modal-title" class="text-base font-semibold text-[var(--color-primary)]">
					{investment.opis ?? investment.rodzaj_inwestycji ?? typLabel ?? 'Inwestycja'}
				</h2>
			</div>
			<button
				class="flex h-8 w-8 shrink-0 items-center justify-center rounded text-[var(--color-text-muted)] transition-colors hover:bg-gray-100"
				onclick={onClose}
				aria-label="Zamknij"
			>
				<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
					<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
				</svg>
			</button>
		</div>

		<div class="flex-1 space-y-4 overflow-y-auto px-5 py-4 text-sm">
			<dl class="grid grid-cols-1 gap-x-6 gap-y-2 sm:grid-cols-2">
				{#if investment.data_decyzji}
					<div>
						<dt class="text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">Data decyzji</dt>
						<dd class="text-[var(--color-primary)]">{investment.data_decyzji}</dd>
					</div>
				{/if}
				{#if investment.data_wniosku}
					<div>
						<dt class="text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">Data wniosku</dt>
						<dd class="text-[var(--color-primary)]">{investment.data_wniosku}</dd>
					</div>
				{/if}
				{#if investment.distance_m != null}
					<div>
						<dt class="text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">Odległość od działki</dt>
						<dd class="text-[var(--color-primary)]">{distLabel(investment.distance_m)}</dd>
					</div>
				{/if}
				{#if investment.parcel_id}
					<div>
						<dt class="text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">Działka ewidencyjna</dt>
						<dd class="break-all text-[var(--color-primary)]">{investment.parcel_id}</dd>
					</div>
				{/if}
				{#if investment.kubatura != null}
					<div>
						<dt class="text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">Kubatura</dt>
						<dd class="text-[var(--color-primary)]">{kubaturaLabel(investment.kubatura)}</dd>
					</div>
				{/if}
				{#if investment.teryt_gmi}
					<div>
						<dt class="text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">TERYT gminy</dt>
						<dd class="text-[var(--color-primary)]">{investment.teryt_gmi}</dd>
					</div>
				{/if}
				{#if investment.source_id}
					<div>
						<dt class="text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">ID rekordu</dt>
						<dd class="break-all font-mono text-[11px] text-[var(--color-text-muted)]">{investment.source_id}</dd>
					</div>
				{/if}
			</dl>

			{#if investment.inwestor}
				<div>
					<div class="text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">Inwestor</div>
					<div class="whitespace-pre-wrap text-[var(--color-primary)]">{investment.inwestor}</div>
				</div>
			{/if}

			{#if investment.organ}
				<div>
					<div class="text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">Organ</div>
					<div class="whitespace-pre-wrap text-[var(--color-primary)]">{investment.organ}</div>
				</div>
			{/if}

			{#if investment.adres || investment.miejscowosc || investment.gmina || investment.wojewodztwo}
				<div>
					<div class="text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">Adres</div>
					<div class="text-[var(--color-primary)]">
						{[investment.adres, investment.miejscowosc, investment.gmina, investment.wojewodztwo].filter(Boolean).join(', ')}
					</div>
				</div>
			{/if}

			{#if investment.rodzaj_inwestycji}
				<div>
					<div class="text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">Rodzaj inwestycji</div>
					<div class="whitespace-pre-wrap text-[var(--color-primary)]">{investment.rodzaj_inwestycji}</div>
				</div>
			{/if}

			{#if investment.opis}
				<div>
					<div class="text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">Opis</div>
					<div class="whitespace-pre-wrap text-[var(--color-primary)]">{investment.opis}</div>
				</div>
			{/if}

			{#if investment.lat != null && investment.lng != null}
				<div>
					<div class="text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">Współrzędne</div>
					<div class="text-[var(--color-primary)]">
						{investment.lat.toFixed(6)}, {investment.lng.toFixed(6)}
					</div>
				</div>
			{/if}

			{#if rawEntries(investment.raw_data).length > 0}
			{@const raw = rawEntries(investment.raw_data)}
				<div class="border-t border-[var(--color-border)] pt-3">
					<button
						class="flex w-full items-center justify-between text-left text-[11px] uppercase tracking-wider text-[var(--color-text-muted)] hover:text-[var(--color-primary)]"
						onclick={() => (rawOpen = !rawOpen)}
					>
						<span>Wszystkie pola z RWDZ ({raw.length})</span>
						<span class="text-xs">{rawOpen ? '▲' : '▼'}</span>
					</button>
					{#if rawOpen}
						<dl class="mt-2 grid grid-cols-1 gap-x-6 gap-y-1.5 text-[12px] sm:grid-cols-[auto_1fr]">
							{#each raw as [k, v]}
								<dt class="font-mono text-[var(--color-text-muted)]">{k}</dt>
								<dd class="whitespace-pre-wrap break-words text-[var(--color-primary)]">{v}</dd>
							{/each}
						</dl>
					{/if}
				</div>
			{/if}
		</div>
	</div>
{/if}
