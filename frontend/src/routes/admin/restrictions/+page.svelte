<script lang="ts">
	import { onMount } from 'svelte';
	import { apiGet, apiPut } from '$lib/api/client';

	type Field = {
		key: string;
		label: string;
		description: string;
		is_restricted: boolean;
	};

	type Response = { fields: Field[] };

	let fields: Field[] = $state([]);
	let loading = $state(true);
	let saving = $state(false);
	let error: string | null = $state(null);
	let savedAt: number | null = $state(null);

	async function load() {
		loading = true;
		try {
			const res = await apiGet<Response>('/api/admin/restrictions');
			fields = res.fields;
		} catch {
			error = 'Nie udało się pobrać listy pól';
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
				updates: { [field.key]: field.is_restricted }
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

	onMount(load);
</script>

<h1 class="mb-2 text-xl font-semibold text-[var(--color-primary)]">Ukryte pola</h1>
<p class="mb-6 max-w-2xl text-sm text-[var(--color-text-muted)]">
	Zaznacz pola, które mają być ukryte przed zwykłymi użytkownikami w Twojej organizacji. Administratorzy widzą wszystko.
</p>

{#if loading}
	<p class="text-sm text-[var(--color-text-muted)]">Ładowanie...</p>
{:else if error && fields.length === 0}
	<p class="text-sm text-red-600">{error}</p>
{:else}
	{#if error}
		<p class="mb-3 text-sm text-red-600">{error}</p>
	{/if}
	<div class="space-y-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-2">
		{#each fields as field (field.key)}
			<label class="flex cursor-pointer items-start gap-3 rounded-md p-3 transition-colors hover:bg-gray-50">
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
	{#if savedAt}
		<p class="mt-3 text-xs text-[var(--color-text-muted)]">Zapisano</p>
	{/if}
{/if}
