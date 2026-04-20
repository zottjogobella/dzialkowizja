<script lang="ts">
	import { onMount } from 'svelte';
	import { apiGet, ApiError } from '$lib/api/client';

	type UserStats = {
		user_id: string;
		display_name: string;
		email: string;
		searches_today: number;
		searches_week: number;
		searches_month: number;
	};

	type TopPlot = {
		query_text: string;
		count: number;
	};

	type OrgStats = {
		total_searches_today: number;
		total_searches_week: number;
		total_searches_month: number;
		users: UserStats[];
		top_plots: TopPlot[];
	};

	let stats: OrgStats | null = $state(null);
	let loading = $state(true);
	let error: string | null = $state(null);
	let disabled = $state(false);

	async function load() {
		loading = true;
		error = null;
		disabled = false;
		try {
			stats = await apiGet<OrgStats>('/api/admin/stats');
		} catch (e) {
			if (e instanceof ApiError && e.status === 403) {
				disabled = true;
			} else {
				error = 'Nie udalo sie pobrac statystyk';
			}
		} finally {
			loading = false;
		}
	}

	onMount(load);
</script>

<h1 class="eyebrow mb-6">&mdash; STATYSTYKI ORGANIZACJI</h1>

{#if loading}
	<div class="flex items-center gap-2 text-sm text-[var(--color-mute)]">
		<div class="h-4 w-4 animate-spin rounded-full border-2 border-[var(--color-faint)] border-t-[var(--color-accent)]"></div>
		Ladowanie...
	</div>
{:else if disabled}
	<div class="glass-card px-6 py-8 text-center">
		<p class="text-sm text-[var(--color-mute)]">Statystyki nie sa wlaczone dla Twojej organizacji.</p>
		<p class="mt-2 text-sm text-[var(--color-mute)]">Skontaktuj sie z administratorem aplikacji aby je uruchomic.</p>
	</div>
{:else if error}
	<p class="text-sm text-red-600">{error}</p>
{:else if stats}
	<!-- Summary tiles -->
	<div class="mb-6 grid grid-cols-3 gap-[14px]">
		{#each [
			{ label: 'DZIS', value: stats.total_searches_today },
			{ label: 'TYDZIEN', value: stats.total_searches_week },
			{ label: 'MIESIAC', value: stats.total_searches_month },
		] as tile}
			<div class="glass-card px-5 py-4">
				<div class="eyebrow mb-1.5" style="font-size: 9.5px; letter-spacing: 1.3px;">WYSZUKIWAN {tile.label}</div>
				<div class="font-serif leading-none" style="font-size: 36px; font-weight: 500; letter-spacing: -1.5px;">{tile.value}</div>
			</div>
		{/each}
	</div>

	<!-- Per-user breakdown -->
	<div class="glass-card mb-6 px-6 py-5">
		<div class="eyebrow mb-3" style="letter-spacing: 1.5px;">&mdash; WYSZUKIWANIA PER UZYTKOWNIK</div>
		{#if stats.users.length === 0}
			<p class="text-sm text-[var(--color-mute)]">Brak uzytkownikow</p>
		{:else}
			<div class="overflow-hidden rounded-xl border border-[var(--color-glass-border)]">
				<div class="grid items-center bg-[var(--color-glass)] px-4 py-2.5 font-mono text-[9.5px] text-[var(--color-mute)]" style="grid-template-columns: 1.5fr 1.5fr 80px 80px 80px; letter-spacing: 1.2px;">
					<div>NAZWA</div><div>EMAIL</div><div class="text-right">DZIS</div><div class="text-right">TYDZIEN</div><div class="text-right">MIESIAC</div>
				</div>
				{#each stats.users as u}
					<div class="grid items-center border-t border-[var(--color-faint)] px-4 py-2.5 text-xs" style="grid-template-columns: 1.5fr 1.5fr 80px 80px 80px;">
						<div class="font-medium">{u.display_name}</div>
						<div class="font-mono text-[11px] text-[var(--color-mute)]">{u.email}</div>
						<div class="text-right font-mono">{u.searches_today}</div>
						<div class="text-right font-mono">{u.searches_week}</div>
						<div class="text-right font-mono font-medium">{u.searches_month}</div>
					</div>
				{/each}
			</div>
		{/if}
	</div>

	<!-- Top searched plots -->
	<div class="glass-card px-6 py-5">
		<div class="eyebrow mb-3" style="letter-spacing: 1.5px;">&mdash; NAJCZESCIEJ WYSZUKIWANE (30 DNI)</div>
		{#if stats.top_plots.length === 0}
			<p class="text-sm text-[var(--color-mute)]">Brak danych</p>
		{:else}
			<div class="space-y-1.5">
				{#each stats.top_plots as plot, i}
					<div class="flex items-center gap-3 rounded-[var(--r-sm)] px-3 py-2 {i === 0 ? 'bg-[rgba(61,90,42,0.06)]' : ''}">
						<span class="font-mono text-[10px] text-[var(--color-mute)]">{String(i + 1).padStart(2, '0')}</span>
						<span class="flex-1 font-mono text-[11px] font-medium">{plot.query_text}</span>
						<span class="font-mono text-[11px] text-[var(--color-mute)]">{plot.count}x</span>
					</div>
				{/each}
			</div>
		{/if}
	</div>
{/if}
