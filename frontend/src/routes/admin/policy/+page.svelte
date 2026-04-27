<script lang="ts">
	import { onMount } from 'svelte';
	import { apiGet, apiPut, ApiError } from '$lib/api/client';

	type Day = {
		day_of_week: number;
		closed: boolean;
		start_time: string | null;
		end_time: string | null;
	};

	type Role = 'handlowiec' | 'prawnik';

	type Policy = {
		role: Role;
		login_hours_enabled: boolean;
		daily_search_limit_enabled: boolean;
		daily_search_limit: number;
		days: Day[];
	};

	const ROLES: { value: Role; label: string }[] = [
		{ value: 'handlowiec', label: 'Handlowiec' },
		{ value: 'prawnik', label: 'Prawnik' },
	];

	const DAY_LABELS = [
		'Poniedziałek',
		'Wtorek',
		'Środa',
		'Czwartek',
		'Piątek',
		'Sobota',
		'Niedziela'
	];

	let role: Role = $state('handlowiec');
	let policy: Policy | null = $state(null);
	let loading = $state(true);
	let saving = $state(false);
	let error: string | null = $state(null);
	let savedAt: number | null = $state(null);
	let noOrg = $state(false);

	async function load(target: Role = role) {
		loading = true;
		noOrg = false;
		error = null;
		try {
			policy = await apiGet<Policy>(`/api/admin/policy?role=${target}`);
			role = policy.role;
		} catch (e) {
			if (e instanceof ApiError && e.status === 400) {
				noOrg = true;
			} else {
				error = 'Nie udało się pobrać polityki';
			}
		} finally {
			loading = false;
		}
	}

	async function switchRole(next: Role) {
		if (next === role || saving || loading) return;
		await load(next);
	}

	function setDayClosed(dow: number, closed: boolean) {
		if (!policy) return;
		const day = policy.days.find((d) => d.day_of_week === dow);
		if (!day) return;
		day.closed = closed;
		if (closed) {
			day.start_time = null;
			day.end_time = null;
		} else {
			day.start_time = day.start_time ?? '09:00';
			day.end_time = day.end_time ?? '18:00';
		}
	}

	async function save() {
		if (!policy) return;
		error = null;
		saving = true;
		try {
			policy = await apiPut<Policy>('/api/admin/policy', { ...policy, role });
			savedAt = Date.now();
		} catch (e) {
			if (e instanceof ApiError) {
				const detail = typeof e.detail === 'object' && e.detail ? e.detail : null;
				const msg = detail && typeof (detail as { message?: string }).message === 'string'
					? (detail as { message: string }).message
					: null;
				error = msg ?? 'Nie udało się zapisać zmian';
			} else {
				error = 'Nie udało się zapisać zmian';
			}
		} finally {
			saving = false;
		}
	}

	onMount(() => load());
</script>

<h1 class="mb-2 text-xl font-semibold text-[var(--color-primary)]">Limity</h1>
<p class="mb-4 max-w-2xl text-sm text-[var(--color-text-muted)]">
	Ustaw godziny logowania i dzienny limit wyszukiwań osobno dla każdej roli w Twojej organizacji. Administratorzy nie podlegają tym ograniczeniom.
</p>

<!-- Role tabs: per-tier limits are independent (handlowiec vs prawnik). -->
<div class="mb-5 flex gap-1 border-b border-[var(--color-border)]">
	{#each ROLES as r}
		<button
			type="button"
			onclick={() => switchRole(r.value)}
			disabled={saving || loading}
			class="-mb-px cursor-pointer border-b-2 px-4 py-2 text-sm font-medium transition-colors
				{role === r.value
					? 'border-[var(--color-primary)] text-[var(--color-primary)]'
					: 'border-transparent text-[var(--color-text-muted)] hover:text-[var(--color-primary)]'}"
		>
			{r.label}
		</button>
	{/each}
</div>

{#if loading}
	<p class="text-sm text-[var(--color-text-muted)]">Ładowanie...</p>
{:else if noOrg}
	<div class="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-8 text-center">
		<p class="text-sm text-[var(--color-text-muted)]">
			Konto super admina nie jest przypisane do organizacji.
		</p>
	</div>
{:else if !policy}
	<p class="text-sm text-red-600">{error ?? 'Nie udało się pobrać polityki'}</p>
{:else}
	{#if error}
		<p class="mb-3 text-sm text-red-600">{error}</p>
	{/if}

	<section class="mb-8 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
		<label class="mb-3 flex items-center gap-2 text-sm font-medium">
			<input type="checkbox" class="h-4 w-4" bind:checked={policy.login_hours_enabled} />
			Godziny logowania aktywne
		</label>
		<p class="mb-4 text-xs text-[var(--color-text-muted)]">
			Gdy wyłączone — użytkownicy tej roli mogą logować się 24/7.
		</p>

		<div class="space-y-2" class:opacity-50={!policy.login_hours_enabled}>
			{#each policy.days as day (day.day_of_week)}
				<div class="flex items-center gap-3 rounded-md border border-[var(--color-border)] p-3">
					<div class="w-28 text-sm">{DAY_LABELS[day.day_of_week]}</div>
					<label class="flex items-center gap-2 text-sm">
						<input
							type="checkbox"
							class="h-4 w-4"
							checked={day.closed}
							disabled={!policy.login_hours_enabled}
							onchange={(e) => setDayClosed(day.day_of_week, (e.currentTarget as HTMLInputElement).checked)}
						/>
						zamknięte
					</label>
					<input
						type="time"
						class="rounded border border-[var(--color-border)] px-2 py-1 text-sm"
						value={day.start_time ?? ''}
						disabled={!policy.login_hours_enabled || day.closed}
						oninput={(e) => (day.start_time = (e.currentTarget as HTMLInputElement).value)}
					/>
					<span class="text-sm text-[var(--color-text-muted)]">–</span>
					<input
						type="time"
						class="rounded border border-[var(--color-border)] px-2 py-1 text-sm"
						value={day.end_time ?? ''}
						disabled={!policy.login_hours_enabled || day.closed}
						oninput={(e) => (day.end_time = (e.currentTarget as HTMLInputElement).value)}
					/>
				</div>
			{/each}
		</div>
	</section>

	<section class="mb-8 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
		<label class="mb-3 flex items-center gap-2 text-sm font-medium">
			<input type="checkbox" class="h-4 w-4" bind:checked={policy.daily_search_limit_enabled} />
			Dzienny limit wyszukiwań aktywny
		</label>
		<p class="mb-4 text-xs text-[var(--color-text-muted)]">
			Reset o 00:00 czasu środkowoeuropejskiego. Gdy wyłączone — brak limitu.
		</p>
		<label class="flex items-center gap-2 text-sm">
			Limit na użytkownika / dzień
			<input
				type="number"
				min="1"
				class="w-24 rounded border border-[var(--color-border)] px-2 py-1 text-sm"
				bind:value={policy.daily_search_limit}
				disabled={!policy.daily_search_limit_enabled}
			/>
		</label>
	</section>

	<button
		type="button"
		class="rounded bg-[var(--color-accent)] px-4 py-2 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50"
		disabled={saving}
		onclick={save}
	>
		{saving ? 'Zapisywanie…' : 'Zapisz'}
	</button>

	{#if savedAt}
		<p class="mt-3 text-xs text-[var(--color-text-muted)]">Zapisano</p>
	{/if}
{/if}
