<script lang="ts">
	import { onMount } from 'svelte';
	import { apiGet } from '$lib/api/client';

	type ActivityRow = {
		id: string;
		user_id: string;
		user_email: string;
		organization_id: string | null;
		organization_name: string | null;
		action_type: string;
		target_id: string | null;
		query_text: string | null;
		ip_address: string | null;
		created_at: string;
	};

	type ActivityPage = {
		items: ActivityRow[];
		total: number;
	};

	type Org = { id: string; name: string };

	const PAGE_SIZE = 50;

	let orgs: Org[] = $state([]);
	let activity: ActivityPage = $state({ items: [], total: 0 });
	let loading = $state(true);
	let error: string | null = $state(null);
	let offset = $state(0);
	let orgFilter = $state('');

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

	function formatDate(iso: string): string {
		return new Date(iso).toLocaleString('pl-PL', { dateStyle: 'short', timeStyle: 'medium' });
	}

	async function loadOrgs() {
		try {
			orgs = await apiGet<Org[]>('/api/super-admin/organizations');
		} catch {}
	}

	async function loadActivity() {
		loading = true;
		error = null;
		try {
			const params = new URLSearchParams();
			params.set('limit', String(PAGE_SIZE));
			params.set('offset', String(offset));
			if (orgFilter) params.set('organization_id', orgFilter);
			activity = await apiGet<ActivityPage>(`/api/super-admin/activity?${params.toString()}`);
		} catch {
			error = 'Nie udało się pobrać dziennika aktywności';
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		void offset;
		void orgFilter;
		loadActivity();
	});

	onMount(loadOrgs);

	function changeFilter(value: string) {
		orgFilter = value;
		offset = 0;
	}
</script>

<h1 class="mb-4 text-xl font-semibold text-[var(--color-primary)]">Aktywność globalna</h1>

<div class="mb-4 flex items-center gap-3">
	<label class="text-xs uppercase tracking-wider text-[var(--color-text-muted)]" for="org-filter">Organizacja:</label>
	<select
		id="org-filter"
		value={orgFilter}
		onchange={(e) => changeFilter((e.target as HTMLSelectElement).value)}
		class="rounded border border-[var(--color-border)] px-3 py-1 text-sm"
	>
		<option value="">Wszystkie</option>
		{#each orgs as o (o.id)}
			<option value={o.id}>{o.name}</option>
		{/each}
	</select>
</div>

{#if loading && activity.items.length === 0}
	<p class="text-sm text-[var(--color-text-muted)]">Ładowanie...</p>
{:else if error}
	<p class="text-sm text-red-600">{error}</p>
{:else}
	<div class="overflow-x-auto rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]">
		<table class="w-full text-sm">
			<thead class="bg-gray-50 text-xs uppercase tracking-wider text-[var(--color-text-muted)]">
				<tr>
					<th class="px-4 py-2 text-left">Czas</th>
					<th class="px-4 py-2 text-left">Użytkownik</th>
					<th class="px-4 py-2 text-left">Organizacja</th>
					<th class="px-4 py-2 text-left">Akcja</th>
					<th class="px-4 py-2 text-left">Cel / zapytanie</th>
					<th class="px-4 py-2 text-left">IP</th>
				</tr>
			</thead>
			<tbody class="divide-y divide-[var(--color-border)]">
				{#each activity.items as row (row.id)}
					<tr>
						<td class="px-4 py-2 whitespace-nowrap text-[var(--color-text-muted)]">{formatDate(row.created_at)}</td>
						<td class="px-4 py-2 text-xs">{row.user_email}</td>
						<td class="px-4 py-2 text-xs">{row.organization_name ?? '—'}</td>
						<td class="px-4 py-2">{actionLabel(row.action_type)}</td>
						<td class="px-4 py-2 font-mono text-xs">{row.query_text ?? row.target_id ?? '—'}</td>
						<td class="px-4 py-2 font-mono text-xs text-[var(--color-text-muted)]">{row.ip_address ?? '—'}</td>
					</tr>
				{/each}
				{#if activity.items.length === 0}
					<tr>
						<td colspan="6" class="px-4 py-6 text-center text-sm text-[var(--color-text-muted)]">Brak zdarzeń</td>
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
