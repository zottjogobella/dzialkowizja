<script lang="ts">
	import { onMount } from 'svelte';
	import { apiGet, apiDelete, apiFetch } from '$lib/api/client';

	type Org = {
		id: string;
		name: string;
		slug: string;
		created_at: string;
		user_count: number;
		activity_count_30d: number;
		stats_enabled: boolean;
	};

	let orgs: Org[] = $state([]);
	let loading = $state(true);
	let error: string | null = $state(null);

	let showModal = $state(false);
	let formName = $state('');
	let formSlug = $state('');
	let formError: string | null = $state(null);
	let saving = $state(false);

	function getCsrfToken(): string {
		return (
			document.cookie
				.split('; ')
				.find((c) => c.startsWith('dzialkowizja_csrf='))
				?.split('=')[1] ?? ''
		);
	}

	async function load() {
		loading = true;
		error = null;
		try {
			orgs = await apiGet<Org[]>('/api/super-admin/organizations');
		} catch {
			error = 'Nie udało się pobrać organizacji';
		} finally {
			loading = false;
		}
	}

	async function createOrg(e: Event) {
		e.preventDefault();
		saving = true;
		formError = null;
		try {
			const res = await apiFetch('/api/super-admin/organizations', {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					'X-CSRF-Token': getCsrfToken()
				},
				body: JSON.stringify({ name: formName, slug: formSlug })
			});
			if (!res.ok) {
				let detail = `Błąd zapisu (${res.status})`;
				try {
					const body = await res.json();
					if (body?.detail) {
						detail = typeof body.detail === 'string'
							? body.detail
							: Array.isArray(body.detail)
								? body.detail.map((d: any) => d.msg ?? JSON.stringify(d)).join('; ')
								: JSON.stringify(body.detail);
					}
				} catch {}
				formError = detail;
				return;
			}
			showModal = false;
			formName = '';
			formSlug = '';
			await load();
		} catch {
			formError = 'Błąd sieci';
		} finally {
			saving = false;
		}
	}

	async function removeOrg(o: Org) {
		if (o.user_count > 0) {
			alert('Organizacja ma członków — najpierw ich usuń');
			return;
		}
		if (!confirm(`Usunąć organizację "${o.name}"?`)) return;
		try {
			await apiDelete(`/api/super-admin/organizations/${o.id}`);
			await load();
		} catch {
			alert('Nie udało się usunąć organizacji');
		}
	}

	async function toggleStats(o: Org) {
		try {
			const res = await apiFetch(`/api/super-admin/organizations/${o.id}/stats`, {
				method: 'PUT',
				headers: {
					'Content-Type': 'application/json',
					'X-CSRF-Token': getCsrfToken()
				},
				body: JSON.stringify({ stats_enabled: !o.stats_enabled })
			});
			if (res.ok) {
				o.stats_enabled = !o.stats_enabled;
				orgs = [...orgs]; // trigger reactivity
			}
		} catch {
			alert('Nie udalo sie zmienic ustawienia');
		}
	}

	function formatDate(iso: string): string {
		return new Date(iso).toLocaleDateString('pl-PL', { dateStyle: 'short' });
	}

	onMount(load);
</script>

<div class="mb-6 flex items-center justify-between">
	<h1 class="text-xl font-semibold text-[var(--color-primary)]">Organizacje</h1>
	<button
		class="rounded-md bg-[var(--color-primary)] px-4 py-2 text-sm font-medium text-white hover:opacity-90"
		onclick={() => (showModal = true)}
	>
		+ Nowa organizacja
	</button>
</div>

{#if loading}
	<p class="text-sm text-[var(--color-text-muted)]">Ładowanie...</p>
{:else if error}
	<p class="text-sm text-red-600">{error}</p>
{:else if orgs.length === 0}
	<p class="text-sm text-[var(--color-text-muted)]">Brak organizacji.</p>
{:else}
	<div class="overflow-x-auto rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]">
		<table class="w-full text-sm">
			<thead class="bg-gray-50 text-xs uppercase tracking-wider text-[var(--color-text-muted)]">
				<tr>
					<th class="px-4 py-2 text-left">Nazwa</th>
					<th class="px-4 py-2 text-left">Slug</th>
					<th class="px-4 py-2 text-right">Użytkowników</th>
					<th class="px-4 py-2 text-right">Aktywność (30d)</th>
					<th class="px-4 py-2 text-center">Statystyki</th>
					<th class="px-4 py-2 text-left">Utworzono</th>
					<th class="px-4 py-2"></th>
				</tr>
			</thead>
			<tbody class="divide-y divide-[var(--color-border)]">
				{#each orgs as o (o.id)}
					<tr>
						<td class="px-4 py-2 font-medium">{o.name}</td>
						<td class="px-4 py-2 font-mono text-xs text-[var(--color-text-muted)]">{o.slug}</td>
						<td class="px-4 py-2 text-right tabular-nums">{o.user_count}</td>
						<td class="px-4 py-2 text-right tabular-nums">{o.activity_count_30d}</td>
						<td class="px-4 py-2 text-center">
							<button
								class="cursor-pointer rounded-full px-2.5 py-0.5 text-[10px] font-semibold transition-colors {o.stats_enabled ? 'bg-green-100 text-green-800' : 'bg-gray-200 text-gray-600'}"
								onclick={() => toggleStats(o)}
							>
								{o.stats_enabled ? 'ON' : 'OFF'}
							</button>
						</td>
						<td class="px-4 py-2 text-[var(--color-text-muted)]">{formatDate(o.created_at)}</td>
						<td class="px-4 py-2 text-right">
							<button class="text-xs text-red-600 hover:underline" onclick={() => removeOrg(o)}>Usuń</button>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
{/if}

{#if showModal}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
		role="presentation"
		onclick={() => (showModal = false)}
		onkeydown={(e) => e.key === 'Escape' && (showModal = false)}
	>
		<!-- svelte-ignore a11y_click_events_have_key_events -->
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div role="dialog" aria-modal="true" tabindex="-1" class="w-full max-w-md rounded-lg bg-[var(--color-surface)] p-6 shadow-xl" onclick={(e) => e.stopPropagation()}>
			<h2 class="mb-4 text-lg font-semibold">Nowa organizacja</h2>
			<form onsubmit={createOrg} class="space-y-3">
				<div>
					<label class="mb-1 block text-xs uppercase tracking-wider text-[var(--color-text-muted)]" for="org-name">Nazwa</label>
					<input id="org-name" type="text" bind:value={formName} required minlength="2" class="w-full rounded border border-[var(--color-border)] px-3 py-2 text-sm" />
				</div>
				<div>
					<label class="mb-1 block text-xs uppercase tracking-wider text-[var(--color-text-muted)]" for="org-slug">Slug</label>
					<input id="org-slug" type="text" bind:value={formSlug} required pattern="[a-z0-9-]{'{2,64}'}" class="w-full rounded border border-[var(--color-border)] px-3 py-2 font-mono text-sm" />
					<p class="mt-1 text-xs text-[var(--color-text-muted)]">a-z, 0-9 i myślnik, 2–64 znaki</p>
				</div>
				{#if formError}
					<p class="text-sm text-red-600">{formError}</p>
				{/if}
				<div class="mt-4 flex justify-end gap-2">
					<button type="button" class="rounded px-4 py-2 text-sm text-[var(--color-text-muted)] hover:bg-gray-100" onclick={() => (showModal = false)}>Anuluj</button>
					<button type="submit" disabled={saving} class="rounded bg-[var(--color-primary)] px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50">
						{saving ? 'Zapisywanie...' : 'Zapisz'}
					</button>
				</div>
			</form>
		</div>
	</div>
{/if}
