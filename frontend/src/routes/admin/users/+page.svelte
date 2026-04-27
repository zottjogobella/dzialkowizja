<script lang="ts">
	import { onMount } from 'svelte';
	import { apiGet, apiDelete, apiFetch, ApiError } from '$lib/api/client';
	import { user as currentUser } from '$lib/stores/auth';

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

	let users: AdminUser[] = $state([]);
	let loading = $state(true);
	let error: string | null = $state(null);
	let noOrg = $state(false);

	type UserRole = 'handlowiec' | 'prawnik';

	let showModal = $state(false);
	let formEmail = $state('');
	let formPassword = $state('');
	let formName = $state('');
	let formRole: UserRole = $state('handlowiec');
	let formError: string | null = $state(null);
	let saving = $state(false);

	let pwUser: AdminUser | null = $state(null);
	let pwValue = $state('');
	let pwError: string | null = $state(null);
	let pwSaving = $state(false);

	let editUser: AdminUser | null = $state(null);
	let editEmail = $state('');
	let editName = $state('');
	let editRole: UserRole = $state('handlowiec');
	let editError: string | null = $state(null);
	let editSaving = $state(false);

	function openEdit(u: AdminUser) {
		editUser = u;
		editEmail = u.email;
		editName = u.display_name;
		editRole = (u.role === 'prawnik' ? 'prawnik' : 'handlowiec') as UserRole;
		editError = null;
	}

	async function load() {
		loading = true;
		error = null;
		noOrg = false;
		try {
			users = await apiGet<AdminUser[]>('/api/admin/users');
		} catch (e) {
			if (e instanceof ApiError && e.status === 400) {
				noOrg = true;
			} else {
				error = 'Nie udało się pobrać listy użytkowników';
			}
		} finally {
			loading = false;
		}
	}

	function getCsrfToken(): string {
		return (
			document.cookie
				.split('; ')
				.find((c) => c.startsWith('dzialkowizja_csrf='))
				?.split('=')[1] ?? ''
		);
	}

	async function createUser(e: Event) {
		e.preventDefault();
		saving = true;
		formError = null;
		try {
			const res = await apiFetch('/api/admin/users', {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					'X-CSRF-Token': getCsrfToken()
				},
				body: JSON.stringify({
					email: formEmail,
					password: formPassword,
					display_name: formName,
					role: formRole
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
			formPassword = '';
			formName = '';
			formRole = 'handlowiec';
			await load();
		} catch {
			formError = 'Błąd sieci';
		} finally {
			saving = false;
		}
	}

	async function deactivate(u: AdminUser) {
		if (!confirm(`Dezaktywować użytkownika ${u.email}?`)) return;
		try {
			await apiDelete(`/api/admin/users/${u.id}`);
			await load();
		} catch {
			alert('Nie udało się dezaktywować użytkownika');
		}
	}

	async function activate(u: AdminUser) {
		if (!confirm(`Aktywować użytkownika ${u.email}?`)) return;
		try {
			const res = await apiFetch(`/api/admin/users/${u.id}/activate`, {
				method: 'POST',
				headers: { 'X-CSRF-Token': getCsrfToken() }
			});
			if (!res.ok) {
				alert('Nie udało się aktywować użytkownika');
				return;
			}
			await load();
		} catch {
			alert('Nie udało się aktywować użytkownika');
		}
	}

	async function saveEdit(e: Event) {
		e.preventDefault();
		if (!editUser) return;
		editSaving = true;
		editError = null;
		try {
			const body: Record<string, string> = {};
			if (editEmail !== editUser.email) body.email = editEmail;
			if (editName !== editUser.display_name) body.display_name = editName;
			if (editRole !== editUser.role) body.role = editRole;
			if (Object.keys(body).length === 0) {
				editUser = null;
				return;
			}
			const res = await apiFetch(`/api/admin/users/${editUser.id}`, {
				method: 'PATCH',
				headers: {
					'Content-Type': 'application/json',
					'X-CSRF-Token': getCsrfToken()
				},
				body: JSON.stringify(body)
			});
			if (!res.ok) {
				let detail = `Błąd (${res.status})`;
				try {
					const b = await res.json();
					if (b?.detail) {
						detail = typeof b.detail === 'string'
							? b.detail
							: Array.isArray(b.detail)
								? b.detail.map((d: any) => d.msg ?? JSON.stringify(d)).join('; ')
								: JSON.stringify(b.detail);
					}
				} catch {}
				editError = detail;
				return;
			}
			editUser = null;
			await load();
		} catch {
			editError = 'Błąd sieci';
		} finally {
			editSaving = false;
		}
	}

	async function changePassword(e: Event) {
		e.preventDefault();
		if (!pwUser) return;
		pwSaving = true;
		pwError = null;
		try {
			const res = await apiFetch(`/api/admin/users/${pwUser.id}/password`, {
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
			pwUser = null;
			pwValue = '';
		} catch {
			pwError = 'Błąd sieci';
		} finally {
			pwSaving = false;
		}
	}

	function formatDate(iso: string | null): string {
		if (!iso) return '—';
		return new Date(iso).toLocaleString('pl-PL', { dateStyle: 'short', timeStyle: 'short' });
	}

	onMount(load);
</script>

<div class="mb-6 flex items-center justify-between">
	<h1 class="text-xl font-semibold text-[var(--color-primary)]">Użytkownicy</h1>
	<button
		class="rounded-md bg-[var(--color-primary)] px-4 py-2 text-sm font-medium text-white transition-colors hover:opacity-90"
		onclick={() => (showModal = true)}
	>
		+ Dodaj użytkownika
	</button>
</div>

{#if loading}
	<p class="text-sm text-[var(--color-text-muted)]">Ładowanie...</p>
{:else if noOrg}
	<div class="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-8 text-center">
		<p class="text-sm text-[var(--color-text-muted)]">
			Konto super admina nie jest przypisane do organizacji.
		</p>
		<p class="mt-2 text-sm text-[var(--color-text-muted)]">
			Zarządzaj użytkownikami i organizacjami przez
			<a href="/super-admin/organizations" class="font-medium text-[var(--color-primary)] hover:underline">panel super admina</a>.
		</p>
	</div>
{:else if error}
	<p class="text-sm text-red-600">{error}</p>
{:else if users.length === 0}
	<p class="text-sm text-[var(--color-text-muted)]">Brak użytkowników. Dodaj pierwszego.</p>
{:else}
	<div class="overflow-x-auto rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]">
		<table class="w-full text-sm">
			<thead class="bg-gray-50 text-xs uppercase tracking-wider text-[var(--color-text-muted)]">
				<tr>
					<th class="px-4 py-2 text-left">Nazwa</th>
					<th class="px-4 py-2 text-left">Email</th>
					<th class="px-4 py-2 text-left">Rola</th>
					<th class="px-4 py-2 text-left">Status</th>
					<th class="px-4 py-2 text-right">Wyszukiwań (7d)</th>
					<th class="px-4 py-2 text-left">Ostatnia aktywność</th>
					<th class="px-4 py-2"></th>
				</tr>
			</thead>
			<tbody class="divide-y divide-[var(--color-border)]">
				{#each users as u (u.id)}
					<tr>
						<td class="px-4 py-2">
							<a href="/admin/users/{u.id}" class="font-medium text-[var(--color-primary)] hover:underline">{u.display_name}</a>
						</td>
						<td class="px-4 py-2 text-[var(--color-text-muted)]">{u.email}</td>
						<td class="px-4 py-2">
							{#if u.role === 'prawnik'}
								<span class="rounded bg-violet-100 px-2 py-0.5 text-xs text-violet-800">Prawnik</span>
							{:else if u.role === 'handlowiec'}
								<span class="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-800">Handlowiec</span>
							{:else}
								<span class="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-700">{u.role}</span>
							{/if}
						</td>
						<td class="px-4 py-2">
							{#if u.is_active}
								<span class="rounded bg-green-100 px-2 py-0.5 text-xs text-green-800">aktywny</span>
							{:else}
								<span class="rounded bg-gray-200 px-2 py-0.5 text-xs text-gray-700">nieaktywny</span>
							{/if}
						</td>
						<td class="px-4 py-2 text-right tabular-nums">{u.search_count_7d}</td>
						<td class="px-4 py-2 text-[var(--color-text-muted)]">{formatDate(u.last_active_at)}</td>
						<td class="px-4 py-2">
							<div class="flex flex-col items-end gap-1">
								<button class="text-xs text-[var(--color-primary)] hover:underline" onclick={() => openEdit(u)}>Edytuj</button>
								<button class="text-xs text-[var(--color-primary)] hover:underline" onclick={() => { pwUser = u; pwValue = ''; pwError = null; }}>Zmień hasło</button>
								{#if u.is_active}
									<button class="text-xs text-red-600 hover:underline" onclick={() => deactivate(u)}>Dezaktywuj</button>
								{:else}
									<button class="text-xs text-green-700 hover:underline" onclick={() => activate(u)}>Aktywuj</button>
								{/if}
							</div>
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
			<h2 class="mb-4 text-lg font-semibold">Nowy użytkownik</h2>
			<form onsubmit={createUser} class="space-y-3">
				<div>
					<label class="mb-1 block text-xs uppercase tracking-wider text-[var(--color-text-muted)]" for="email">Login</label>
					<input id="email" type="text" bind:value={formEmail} required class="w-full rounded border border-[var(--color-border)] px-3 py-2 text-sm" />
				</div>
				<div>
					<label class="mb-1 block text-xs uppercase tracking-wider text-[var(--color-text-muted)]" for="name">Nazwa wyświetlana</label>
					<input id="name" type="text" bind:value={formName} required minlength="2" class="w-full rounded border border-[var(--color-border)] px-3 py-2 text-sm" />
				</div>
				<div>
					<label class="mb-1 block text-xs uppercase tracking-wider text-[var(--color-text-muted)]" for="password">Hasło</label>
					<input id="password" type="text" bind:value={formPassword} required class="w-full rounded border border-[var(--color-border)] px-3 py-2 font-mono text-sm" />
					<p class="mt-1 text-xs text-[var(--color-text-muted)]">Minimum 6 znaków.</p>
				</div>
				<div>
					<label class="mb-1 block text-xs uppercase tracking-wider text-[var(--color-text-muted)]" for="role">Rola</label>
					<select id="role" bind:value={formRole} class="w-full rounded border border-[var(--color-border)] px-3 py-2 text-sm">
						<option value="handlowiec">Handlowiec</option>
						<option value="prawnik">Prawnik</option>
					</select>
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

{#if pwUser}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
		role="presentation"
		onclick={() => (pwUser = null)}
		onkeydown={(e) => e.key === 'Escape' && (pwUser = null)}
	>
		<!-- svelte-ignore a11y_click_events_have_key_events -->
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div role="dialog" aria-modal="true" tabindex="-1" class="w-full max-w-sm rounded-lg bg-[var(--color-surface)] p-6 shadow-xl" onclick={(e) => e.stopPropagation()}>
			<h2 class="mb-1 text-lg font-semibold">Zmień hasło</h2>
			<p class="mb-4 text-sm text-[var(--color-text-muted)]">{pwUser.display_name} ({pwUser.email})</p>
			<form onsubmit={changePassword}>
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
					<button type="button" class="rounded px-4 py-2 text-sm text-[var(--color-text-muted)] hover:bg-gray-100" onclick={() => (pwUser = null)}>Anuluj</button>
					<button type="submit" disabled={pwSaving} class="rounded bg-[var(--color-primary)] px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50">
						{pwSaving ? 'Zapisywanie...' : 'Zapisz'}
					</button>
				</div>
			</form>
		</div>
	</div>
{/if}

{#if editUser}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
		role="presentation"
		onclick={() => (editUser = null)}
		onkeydown={(e) => e.key === 'Escape' && (editUser = null)}
	>
		<!-- svelte-ignore a11y_click_events_have_key_events -->
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div role="dialog" aria-modal="true" tabindex="-1" class="w-full max-w-md rounded-lg bg-[var(--color-surface)] p-6 shadow-xl" onclick={(e) => e.stopPropagation()}>
			<h2 class="mb-4 text-lg font-semibold">Edytuj użytkownika</h2>
			<form onsubmit={saveEdit} class="space-y-3">
				<div>
					<label class="mb-1 block text-xs uppercase tracking-wider text-[var(--color-text-muted)]" for="edit-email">Login (email)</label>
					<input id="edit-email" type="text" bind:value={editEmail} required class="w-full rounded border border-[var(--color-border)] px-3 py-2 text-sm" />
				</div>
				<div>
					<label class="mb-1 block text-xs uppercase tracking-wider text-[var(--color-text-muted)]" for="edit-name">Nazwa wyświetlana</label>
					<input id="edit-name" type="text" bind:value={editName} required minlength="2" class="w-full rounded border border-[var(--color-border)] px-3 py-2 text-sm" />
				</div>
				<div>
					<label class="mb-1 block text-xs uppercase tracking-wider text-[var(--color-text-muted)]" for="edit-role">Rola</label>
					<select id="edit-role" bind:value={editRole} class="w-full rounded border border-[var(--color-border)] px-3 py-2 text-sm">
						<option value="handlowiec">Handlowiec</option>
						<option value="prawnik">Prawnik</option>
					</select>
				</div>
				{#if editError}
					<p class="text-sm text-red-600">{editError}</p>
				{/if}
				<div class="mt-4 flex justify-end gap-2">
					<button type="button" class="rounded px-4 py-2 text-sm text-[var(--color-text-muted)] hover:bg-gray-100" onclick={() => (editUser = null)}>Anuluj</button>
					<button type="submit" disabled={editSaving} class="rounded bg-[var(--color-primary)] px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50">
						{editSaving ? 'Zapisywanie...' : 'Zapisz'}
					</button>
				</div>
			</form>
		</div>
	</div>
{/if}
