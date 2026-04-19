<script lang="ts">
	import { onMount } from 'svelte';
	import { apiGet, apiDelete, apiFetch } from '$lib/api/client';

	type Admin = {
		id: string;
		email: string;
		display_name: string;
		is_active: boolean;
		organization_id: string | null;
		organization_name: string | null;
		created_at: string;
	};

	type Org = { id: string; name: string; slug: string };

	let admins: Admin[] = $state([]);
	let orgs: Org[] = $state([]);
	let loading = $state(true);
	let error: string | null = $state(null);

	let showModal = $state(false);
	let formEmail = $state('');
	let formName = $state('');
	let formPassword = $state('');
	let formOrgId = $state('');
	let formError: string | null = $state(null);
	let saving = $state(false);

	let pwAdmin: Admin | null = $state(null);
	let pwValue = $state('');
	let pwError: string | null = $state(null);
	let pwSaving = $state(false);

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
			const [a, o] = await Promise.all([
				apiGet<Admin[]>('/api/super-admin/admins'),
				apiGet<Org[]>('/api/super-admin/organizations')
			]);
			admins = a;
			orgs = o;
			if (!formOrgId && o.length > 0) formOrgId = o[0].id;
		} catch {
			error = 'Nie udało się pobrać listy administratorów';
		} finally {
			loading = false;
		}
	}

	async function createAdmin(e: Event) {
		e.preventDefault();
		saving = true;
		formError = null;
		try {
			const res = await apiFetch('/api/super-admin/admins', {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					'X-CSRF-Token': getCsrfToken()
				},
				body: JSON.stringify({
					email: formEmail,
					display_name: formName,
					password: formPassword,
					organization_id: formOrgId
				})
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
			formEmail = '';
			formName = '';
			formPassword = '';
			await load();
		} catch {
			formError = 'Błąd sieci';
		} finally {
			saving = false;
		}
	}

	async function changeAdminPassword(e: Event) {
		e.preventDefault();
		if (!pwAdmin) return;
		pwSaving = true;
		pwError = null;
		try {
			const res = await apiFetch(`/api/super-admin/admins/${pwAdmin.id}/password`, {
				method: 'PUT',
				headers: {
					'Content-Type': 'application/json',
					'X-CSRF-Token': getCsrfToken()
				},
				body: JSON.stringify({ password: pwValue })
			});
			if (!res.ok) {
				let detail = `Błąd (${res.status})`;
				try {
					const body = await res.json();
					if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
				} catch {}
				pwError = detail;
				return;
			}
			pwAdmin = null;
			pwValue = '';
		} catch {
			pwError = 'Błąd sieci';
		} finally {
			pwSaving = false;
		}
	}

	async function deactivate(a: Admin) {
		if (!confirm(`Dezaktywować admina ${a.email}?`)) return;
		try {
			await apiDelete(`/api/super-admin/admins/${a.id}`);
			await load();
		} catch {
			alert('Nie udało się dezaktywować admina');
		}
	}

	function formatDate(iso: string): string {
		return new Date(iso).toLocaleDateString('pl-PL', { dateStyle: 'short' });
	}

	onMount(load);
</script>

<div class="mb-6 flex items-center justify-between">
	<h1 class="text-xl font-semibold text-[var(--color-primary)]">Administratorzy</h1>
	<button
		class="rounded-md bg-[var(--color-primary)] px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
		disabled={orgs.length === 0}
		onclick={() => (showModal = true)}
	>
		+ Nowy admin
	</button>
</div>

{#if loading}
	<p class="text-sm text-[var(--color-text-muted)]">Ładowanie...</p>
{:else if error}
	<p class="text-sm text-red-600">{error}</p>
{:else if admins.length === 0}
	<p class="text-sm text-[var(--color-text-muted)]">Brak administratorów.</p>
{:else}
	<div class="overflow-x-auto rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]">
		<table class="w-full text-sm">
			<thead class="bg-gray-50 text-xs uppercase tracking-wider text-[var(--color-text-muted)]">
				<tr>
					<th class="px-4 py-2 text-left">Nazwa</th>
					<th class="px-4 py-2 text-left">Email</th>
					<th class="px-4 py-2 text-left">Organizacja</th>
					<th class="px-4 py-2 text-left">Status</th>
					<th class="px-4 py-2 text-left">Utworzono</th>
					<th class="px-4 py-2"></th>
				</tr>
			</thead>
			<tbody class="divide-y divide-[var(--color-border)]">
				{#each admins as a (a.id)}
					<tr>
						<td class="px-4 py-2 font-medium">{a.display_name}</td>
						<td class="px-4 py-2 text-[var(--color-text-muted)]">{a.email}</td>
						<td class="px-4 py-2">{a.organization_name ?? '—'}</td>
						<td class="px-4 py-2">
							{#if a.is_active}
								<span class="rounded bg-green-100 px-2 py-0.5 text-xs text-green-800">aktywny</span>
							{:else}
								<span class="rounded bg-gray-200 px-2 py-0.5 text-xs text-gray-700">nieaktywny</span>
							{/if}
						</td>
						<td class="px-4 py-2 text-[var(--color-text-muted)]">{formatDate(a.created_at)}</td>
						<td class="px-4 py-2 text-right space-x-2">
							<button class="text-xs text-[var(--color-primary)] hover:underline" onclick={() => { pwAdmin = a; pwValue = ''; pwError = null; }}>Zmień hasło</button>
							{#if a.is_active}
								<button class="text-xs text-red-600 hover:underline" onclick={() => deactivate(a)}>Dezaktywuj</button>
							{/if}
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
{/if}

{#if orgs.length === 0 && !loading}
	<p class="mt-3 text-sm text-[var(--color-text-muted)]">Najpierw utwórz organizację w zakładce „Organizacje”.</p>
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
			<h2 class="mb-4 text-lg font-semibold">Nowy administrator</h2>
			<form onsubmit={createAdmin} class="space-y-3">
				<div>
					<label class="mb-1 block text-xs uppercase tracking-wider text-[var(--color-text-muted)]" for="admin-email">Email (login)</label>
					<input id="admin-email" type="email" bind:value={formEmail} required class="w-full rounded border border-[var(--color-border)] px-3 py-2 text-sm" />
				</div>
				<div>
					<label class="mb-1 block text-xs uppercase tracking-wider text-[var(--color-text-muted)]" for="admin-name">Nazwa wyświetlana</label>
					<input id="admin-name" type="text" bind:value={formName} required minlength="2" class="w-full rounded border border-[var(--color-border)] px-3 py-2 text-sm" />
				</div>
				<div>
					<label class="mb-1 block text-xs uppercase tracking-wider text-[var(--color-text-muted)]" for="admin-org">Organizacja</label>
					<select id="admin-org" bind:value={formOrgId} required class="w-full rounded border border-[var(--color-border)] px-3 py-2 text-sm">
						{#each orgs as o (o.id)}
							<option value={o.id}>{o.name} ({o.slug})</option>
						{/each}
					</select>
				</div>
				<div>
					<label class="mb-1 block text-xs uppercase tracking-wider text-[var(--color-text-muted)]" for="admin-pw">Hasło</label>
					<input id="admin-pw" type="text" bind:value={formPassword} required class="w-full rounded border border-[var(--color-border)] px-3 py-2 font-mono text-sm" />
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

{#if pwAdmin}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
		role="presentation"
		onclick={() => (pwAdmin = null)}
		onkeydown={(e) => e.key === 'Escape' && (pwAdmin = null)}
	>
		<!-- svelte-ignore a11y_click_events_have_key_events -->
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div role="dialog" aria-modal="true" tabindex="-1" class="w-full max-w-sm rounded-lg bg-[var(--color-surface)] p-6 shadow-xl" onclick={(e) => e.stopPropagation()}>
			<h2 class="mb-1 text-lg font-semibold">Zmień hasło</h2>
			<p class="mb-4 text-sm text-[var(--color-text-muted)]">{pwAdmin.display_name} ({pwAdmin.email})</p>
			<form onsubmit={changeAdminPassword}>
				<input
					type="text"
					bind:value={pwValue}
					required
					minlength="6"
					placeholder="Nowe hasło"
					class="w-full rounded border border-[var(--color-border)] px-3 py-2 font-mono text-sm"
				/>
				{#if pwError}
					<p class="mt-2 text-sm text-red-600">{pwError}</p>
				{/if}
				<div class="mt-4 flex justify-end gap-2">
					<button type="button" class="rounded px-4 py-2 text-sm text-[var(--color-text-muted)] hover:bg-gray-100" onclick={() => (pwAdmin = null)}>Anuluj</button>
					<button type="submit" disabled={pwSaving} class="rounded bg-[var(--color-primary)] px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50">
						{pwSaving ? 'Zapisywanie...' : 'Zapisz'}
					</button>
				</div>
			</form>
		</div>
	</div>
{/if}
