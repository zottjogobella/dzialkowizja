<script lang="ts">
	import { onMount } from 'svelte';
	import { apiGet, apiPut, ApiError } from '$lib/api/client';

	type Field = {
		key: string;
		label: string;
		description: string;
		group: string;
		is_restricted: boolean;
	};

	type Response = { role: Role; fields: Field[] };
	type Role = 'handlowiec' | 'prawnik';

	const ROLES: { value: Role; label: string }[] = [
		{ value: 'handlowiec', label: 'Handlowiec' },
		{ value: 'prawnik', label: 'Prawnik' },
	];

	let role: Role = $state('handlowiec');
	let fields: Field[] = $state([]);
	let loading = $state(true);
	let saving = $state(false);
	let error: string | null = $state(null);
	let savedAt: number | null = $state(null);
	let noOrg = $state(false);
	// Group keys (heading text) collapsed by the admin. Default: all open.
	let collapsed: Set<string> = $state(new Set());

	// Group → fields, preserving the order keys were registered in on the backend.
	const groups = $derived.by(() => {
		const map = new Map<string, Field[]>();
		for (const f of fields) {
			const g = f.group ?? 'Inne';
			if (!map.has(g)) map.set(g, []);
			map.get(g)!.push(f);
		}
		return Array.from(map.entries());
	});

	const totalHidden = $derived(fields.filter(f => f.is_restricted).length);

	async function load(target: Role = role) {
		loading = true;
		noOrg = false;
		error = null;
		try {
			const res = await apiGet<Response>(`/api/admin/restrictions?role=${target}`);
			fields = res.fields;
			role = res.role;
		} catch (e) {
			if (e instanceof ApiError && e.status === 400) {
				noOrg = true;
			} else {
				error = 'Nie udało się pobrać listy pól';
			}
		} finally {
			loading = false;
		}
	}

	async function toggle(field: Field) {
		const previous = field.is_restricted;
		field.is_restricted = !previous;
		saving = true;
		error = null;
		try {
			const res = await apiPut<Response>('/api/admin/restrictions', {
				role,
				updates: { [field.key]: field.is_restricted },
			});
			fields = res.fields;
			savedAt = Date.now();
		} catch {
			field.is_restricted = previous;
			error = 'Nie udało się zapisać zmiany';
		} finally {
			saving = false;
		}
	}

	async function bulkSetGroup(group: string, hide: boolean) {
		const targets = fields.filter(f => f.group === group && f.is_restricted !== hide);
		if (targets.length === 0) return;
		// Optimistic: update locally, fall back if the request fails.
		const previous = targets.map(f => ({ key: f.key, was: f.is_restricted }));
		for (const f of targets) f.is_restricted = hide;
		saving = true;
		error = null;
		try {
			const res = await apiPut<Response>('/api/admin/restrictions', {
				role,
				updates: Object.fromEntries(targets.map(f => [f.key, hide])),
			});
			fields = res.fields;
			savedAt = Date.now();
		} catch {
			for (const p of previous) {
				const f = fields.find(x => x.key === p.key);
				if (f) f.is_restricted = p.was;
			}
			error = 'Nie udało się zapisać zmian zbiorczych';
		} finally {
			saving = false;
		}
	}

	function toggleGroup(g: string) {
		const next = new Set(collapsed);
		if (next.has(g)) next.delete(g);
		else next.add(g);
		collapsed = next;
	}

	async function switchRole(next: Role) {
		if (next === role) return;
		await load(next);
	}

	onMount(() => load());
</script>

<h1 class="mb-2 text-xl font-semibold text-[var(--color-primary)]">Ukryte pola</h1>
<p class="mb-4 max-w-2xl text-sm text-[var(--color-text-muted)]">
	Zaznacz pola, które mają być ukryte przed wybraną rolą w Twojej organizacji. Administratorzy widzą wszystko.
</p>

<!-- Role tabs: per-tier restrictions are independent (handlowiec vs prawnik). -->
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
	<div class="ml-auto self-center text-xs text-[var(--color-text-muted)]">
		{#if !loading && !noOrg}
			Ukryte: <span class="font-mono">{totalHidden}</span> / {fields.length}
		{/if}
	</div>
</div>

{#if loading}
	<p class="text-sm text-[var(--color-text-muted)]">Ładowanie...</p>
{:else if noOrg}
	<div class="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-8 text-center">
		<p class="text-sm text-[var(--color-text-muted)]">
			Konto super admina nie jest przypisane do organizacji.
		</p>
		<p class="mt-2 text-sm text-[var(--color-text-muted)]">
			Zarządzaj organizacjami przez
			<a href="/super-admin/organizations" class="font-medium text-[var(--color-primary)] hover:underline">panel super admina</a>.
		</p>
	</div>
{:else if error && fields.length === 0}
	<p class="text-sm text-red-600">{error}</p>
{:else}
	{#if error}
		<p class="mb-3 text-sm text-red-600">{error}</p>
	{/if}

	<div class="space-y-3">
		{#each groups as [groupName, groupFields] (groupName)}
			{@const hiddenInGroup = groupFields.filter(f => f.is_restricted).length}
			{@const open = !collapsed.has(groupName)}
			<section class="overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]">
				<header class="flex items-center gap-3 border-b border-[var(--color-border)] bg-gray-50 px-4 py-2.5">
					<button
						type="button"
						onclick={() => toggleGroup(groupName)}
						class="flex flex-1 cursor-pointer items-center gap-2 text-left"
						aria-expanded={open}
					>
						<span class="text-xs text-[var(--color-text-muted)] transition-transform {open ? 'rotate-90' : ''}">▶</span>
						<span class="text-sm font-semibold text-[var(--color-primary)]">{groupName}</span>
						<span class="text-xs text-[var(--color-text-muted)]">
							{hiddenInGroup}/{groupFields.length} ukrytych
						</span>
					</button>
					<button
						type="button"
						onclick={() => bulkSetGroup(groupName, true)}
						disabled={saving || hiddenInGroup === groupFields.length}
						class="cursor-pointer rounded border border-[var(--color-border)] bg-white px-2 py-0.5 text-[11px] font-medium text-[var(--color-text-muted)] hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
					>Ukryj wszystko</button>
					<button
						type="button"
						onclick={() => bulkSetGroup(groupName, false)}
						disabled={saving || hiddenInGroup === 0}
						class="cursor-pointer rounded border border-[var(--color-border)] bg-white px-2 py-0.5 text-[11px] font-medium text-[var(--color-text-muted)] hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
					>Pokaż wszystko</button>
				</header>
				{#if open}
					<div class="divide-y divide-[var(--color-border)]">
						{#each groupFields as field (field.key)}
							<label class="flex cursor-pointer items-start gap-3 px-4 py-3 transition-colors hover:bg-gray-50">
								<input
									type="checkbox"
									class="mt-1 h-4 w-4"
									checked={field.is_restricted}
									disabled={saving}
									onchange={() => toggle(field)}
								/>
								<div class="flex-1">
									<div class="text-sm font-medium text-[var(--color-primary)]">{field.label}</div>
									<div class="text-xs text-[var(--color-text-muted)]">{field.description}</div>
									<div class="mt-1 font-mono text-[10px] text-[var(--color-text-muted)]">{field.key}</div>
								</div>
								{#if field.is_restricted}
									<span class="rounded bg-red-100 px-2 py-0.5 text-xs text-red-800">ukryte</span>
								{:else}
									<span class="rounded bg-green-100 px-2 py-0.5 text-xs text-green-800">widoczne</span>
								{/if}
							</label>
						{/each}
					</div>
				{/if}
			</section>
		{/each}
	</div>

	{#if savedAt}
		<p class="mt-3 text-xs text-[var(--color-text-muted)]">Zapisano</p>
	{/if}
{/if}
