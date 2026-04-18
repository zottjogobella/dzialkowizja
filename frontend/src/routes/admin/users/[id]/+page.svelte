<script lang="ts">
	import { page } from '$app/stores';
	import { apiGet } from '$lib/api/client';

	type ActivityRow = {
		id: string;
		action_type: string;
		target_id: string | null;
		query_text: string | null;
		ip_address: string | null;
		user_agent: string | null;
		created_at: string;
	};

	type ActivityPage = {
		items: ActivityRow[];
		total: number;
	};

	type AdminUser = {
		id: string;
		email: string;
		display_name: string;
		is_active: boolean;
		role: string;
		organization_id: string | null;
		created_at: string;
		last_active_at: string | null;
		search_count_7d: number;
	};

	const userId = $derived($page.params.id);
	const PAGE_SIZE = 50;

	let userInfo: AdminUser | null = $state(null);
	let activity: ActivityPage = $state({ items: [], total: 0 });
	let loading = $state(true);
	let error: string | null = $state(null);
	let offset = $state(0);

	async function load() {
		loading = true;
		error = null;
		try {
			const [users, page] = await Promise.all([
				apiGet<AdminUser[]>('/api/admin/users'),
				apiGet<ActivityPage>(`/api/admin/users/${userId}/activity?limit=${PAGE_SIZE}&offset=${offset}`)
			]);
			userInfo = users.find((u) => u.id === userId) ?? null;
			activity = page;
		} catch {
			error = 'Nie udało się pobrać aktywności użytkownika';
		} finally {
			loading = false;
		}
	}

	function formatDate(iso: string): string {
		return new Date(iso).toLocaleString('pl-PL', { dateStyle: 'short', timeStyle: 'medium' });
	}

	const actionLabels: Record<string, string> = {
		search: 'Wyszukiwanie',
		plot_view: 'Otwarcie działki',
		roszczenie_fetch: 'Pobranie roszczenia',
		mpzp_fetch: 'Pobranie MPZP',
		investment_fetch: 'Pobranie inwestycji'
	};

	function actionLabel(t: string): string {
		return actionLabels[t] ?? t;
	}

	const aggregates = $derived.by(() => {
		const byAction: Record<string, number> = {};
		const byIp: Record<string, number> = {};
		for (const row of activity.items) {
			byAction[row.action_type] = (byAction[row.action_type] ?? 0) + 1;
			if (row.ip_address) byIp[row.ip_address] = (byIp[row.ip_address] ?? 0) + 1;
		}
		return { byAction, byIp };
	});

	$effect(() => {
		void userId;
		void offset;
		load();
	});
</script>

<a href="/admin/users" class="mb-4 inline-block text-sm text-[var(--color-text-muted)] hover:underline">← Wróć do listy</a>

{#if loading && !userInfo}
	<p class="text-sm text-[var(--color-text-muted)]">Ładowanie...</p>
{:else if error}
	<p class="text-sm text-red-600">{error}</p>
{:else}
	{#if userInfo}
		<div class="mb-6">
			<h1 class="text-xl font-semibold text-[var(--color-primary)]">{userInfo.display_name}</h1>
			<p class="text-sm text-[var(--color-text-muted)]">{userInfo.email}</p>
		</div>
	{/if}

	<div class="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
		<div class="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-3">
			<div class="text-xs uppercase tracking-wider text-[var(--color-text-muted)]">Łącznie zdarzeń</div>
			<div class="mt-1 text-2xl font-semibold tabular-nums">{activity.total}</div>
		</div>
		{#each Object.entries(aggregates.byAction) as [action, count] (action)}
			<div class="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-3">
				<div class="text-xs uppercase tracking-wider text-[var(--color-text-muted)]">{actionLabel(action)}</div>
				<div class="mt-1 text-2xl font-semibold tabular-nums">{count}</div>
				<div class="text-[11px] text-[var(--color-text-muted)]">w bieżącej stronie</div>
			</div>
		{/each}
	</div>

	{#if Object.keys(aggregates.byIp).length > 0}
		<div class="mb-6 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
			<h3 class="mb-2 text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">Adresy IP (bieżąca strona)</h3>
			<div class="flex flex-wrap gap-2 text-xs">
				{#each Object.entries(aggregates.byIp).sort((a, b) => b[1] - a[1]) as [ip, count] (ip)}
					<span class="rounded bg-gray-100 px-2 py-1 font-mono">{ip} <span class="text-[var(--color-text-muted)]">×{count}</span></span>
				{/each}
			</div>
		</div>
	{/if}

	<div class="overflow-x-auto rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]">
		<table class="w-full text-sm">
			<thead class="bg-gray-50 text-xs uppercase tracking-wider text-[var(--color-text-muted)]">
				<tr>
					<th class="px-4 py-2 text-left">Czas</th>
					<th class="px-4 py-2 text-left">Akcja</th>
					<th class="px-4 py-2 text-left">Cel / zapytanie</th>
					<th class="px-4 py-2 text-left">IP</th>
				</tr>
			</thead>
			<tbody class="divide-y divide-[var(--color-border)]">
				{#each activity.items as row (row.id)}
					<tr>
						<td class="px-4 py-2 whitespace-nowrap text-[var(--color-text-muted)]">{formatDate(row.created_at)}</td>
						<td class="px-4 py-2">{actionLabel(row.action_type)}</td>
						<td class="px-4 py-2 font-mono text-xs">
							{row.query_text ?? row.target_id ?? '—'}
						</td>
						<td class="px-4 py-2 font-mono text-xs text-[var(--color-text-muted)]">{row.ip_address ?? '—'}</td>
					</tr>
				{/each}
				{#if activity.items.length === 0}
					<tr>
						<td colspan="4" class="px-4 py-6 text-center text-sm text-[var(--color-text-muted)]">Brak zdarzeń</td>
					</tr>
				{/if}
			</tbody>
		</table>
	</div>

	{#if activity.total > PAGE_SIZE}
		<div class="mt-4 flex items-center justify-between text-sm">
			<button
				class="rounded border border-[var(--color-border)] px-3 py-1 disabled:opacity-50"
				disabled={offset === 0}
				onclick={() => (offset = Math.max(0, offset - PAGE_SIZE))}
			>
				← Poprzednia
			</button>
			<span class="text-[var(--color-text-muted)]">
				{offset + 1}–{Math.min(offset + PAGE_SIZE, activity.total)} z {activity.total}
			</span>
			<button
				class="rounded border border-[var(--color-border)] px-3 py-1 disabled:opacity-50"
				disabled={offset + PAGE_SIZE >= activity.total}
				onclick={() => (offset = offset + PAGE_SIZE)}
			>
				Następna →
			</button>
		</div>
	{/if}
{/if}
