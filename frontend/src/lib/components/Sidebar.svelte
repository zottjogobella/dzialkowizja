<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { historyItems, historyLoaded, loadHistory } from '$lib/stores/history';
	import { searchQuery, hasSearched } from '$lib/stores/search';
	import { user } from '$lib/stores/auth';
	import { apiFetch } from '$lib/api/client';
	import { onMount } from 'svelte';

	let loggingOut = $state(false);
	let menuOpen = $state(false);
	let clickedItemId = $state<number | null>(null);

	onMount(() => {
		if (!$historyLoaded) {
			loadHistory();
		}
	});

	function formatTime(iso: string): string {
		const d = new Date(iso);
		return d.toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit' });
	}

	function formatDate(iso: string): string {
		const d = new Date(iso);
		return d.toLocaleDateString('pl-PL', { day: 'numeric', month: 'short' });
	}

	function rerunSearch(item: { id: number; query_text: string; query_type: string; top_result_id?: string | null }) {
		clickedItemId = item.id;
		searchQuery.set(item.query_text);
		hasSearched.set(true);
		if (item.top_result_id) {
			goto(`/plot/${encodeURIComponent(item.top_result_id)}`);
		}
	}

	async function logout() {
		loggingOut = true;
		try {
			await apiFetch('/api/auth/logout', { method: 'POST' });
		} catch {
			// ignore
		}
		user.set(null);
		window.location.href = '/auth/login';
	}

	function isOnPlotPage(item: { top_result_id?: string | null }): boolean {
		if (!item.top_result_id) return false;
		return $page.url.pathname === `/plot/${encodeURIComponent(item.top_result_id)}`;
	}

	const activeItemId = $derived.by(() => {
		const matching = $historyItems.filter(isOnPlotPage);
		if (matching.length === 0) return null;
		if (clickedItemId !== null && matching.some((i) => i.id === clickedItemId)) {
			return clickedItemId;
		}
		return matching[0].id;
	});

	const ROLE_LABELS: Record<string, string> = {
		super_admin: 'Super Admin',
		admin: 'Org Admin',
		user: 'Użytkownik',
	};
</script>

<aside class="glass-card-lg relative z-[1] m-[14px] mr-0 flex w-64 shrink-0 flex-col">
	<!-- Logo -->
	<a href="/" class="flex items-center gap-2.5 border-b border-[var(--color-faint)] px-5 py-[18px]">
		<div class="grid h-6 w-6 place-items-center rounded-[7px] bg-[var(--color-ink)] font-mono text-xs font-semibold text-white">G</div>
		<span class="font-serif text-lg font-medium" style="letter-spacing: -0.3px;">Gruntify</span>
	</a>

	<!-- Nav links for admin -->
	{#if $user && ($user.role === 'admin' || $user.role === 'super_admin')}
		<nav class="border-b border-[var(--color-faint)] px-3 py-2">
			<a
				href="/admin/users"
				class="flex items-center gap-2 rounded-[var(--r-sm)] px-3 py-2 font-mono text-[11px] transition-colors {$page.url.pathname.startsWith('/admin') ? 'bg-[rgba(61,90,42,0.08)] text-[var(--color-accent)]' : 'text-[var(--color-mute)] hover:text-[var(--color-ink)]'}"
			>
				Panel organizacji
			</a>
			{#if $user.role === 'super_admin'}
				<a
					href="/super-admin/organizations"
					class="flex items-center gap-2 rounded-[var(--r-sm)] px-3 py-2 font-mono text-[11px] transition-colors {$page.url.pathname.startsWith('/super-admin') ? 'bg-[rgba(61,90,42,0.08)] text-[var(--color-accent)]' : 'text-[var(--color-mute)] hover:text-[var(--color-ink)]'}"
				>
					Super admin
				</a>
			{/if}
		</nav>
	{/if}

	<!-- History header -->
	<div class="flex justify-between px-5 pt-3 pb-1.5">
		<span class="eyebrow">HISTORIA</span>
		<span class="eyebrow">{$historyItems.length}</span>
	</div>

	<!-- History list -->
	<nav class="flex-1 overflow-y-auto px-2 pb-2">
		{#if $historyItems.length === 0}
			<p class="px-3 py-8 text-center font-mono text-[11px] text-[var(--color-mute)]">Brak historii</p>
		{:else}
			{#each $historyItems as item (item.id)}
				{@const active = item.id === activeItemId}
				<button
					class="mb-0.5 grid w-full cursor-pointer grid-cols-[1fr_auto] gap-1 rounded-[var(--r-sm)] px-3 py-[7px] text-left transition-colors
						{active ? 'border border-[rgba(61,90,42,0.2)] bg-[rgba(61,90,42,0.08)]' : 'border border-transparent hover:bg-[var(--color-glass)]'}"
					onclick={() => rerunSearch(item)}
				>
					<div class="truncate font-mono text-[11px] font-medium {active ? 'text-[var(--color-accent)]' : 'text-[var(--color-ink)]'}">
						{item.query_text}
					</div>
					<div class="font-mono text-[10px] text-[var(--color-mute)]">{formatTime(item.created_at)}</div>
				</button>
			{/each}
		{/if}
	</nav>

	<!-- User footer -->
	{#if $user}
		<div class="relative mx-1.5 mb-1.5 border-t border-[var(--color-faint)] px-4 py-3">
			<button
				class="flex w-full items-center gap-2.5"
				onclick={() => menuOpen = !menuOpen}
			>
				<div class="grid h-[26px] w-[26px] shrink-0 place-items-center rounded-full bg-[var(--color-accent)] font-mono text-[11px] font-semibold text-white">
					{($user.display_name ?? $user.email ?? '?').charAt(0).toUpperCase()}
				</div>
				<div class="min-w-0 flex-1 text-left">
					<div class="truncate text-xs font-medium">{$user.display_name}</div>
				</div>
				<div class="glass-chip px-[7px] py-[3px] font-mono text-[10px] text-[var(--color-mute)]">
					{ROLE_LABELS[$user.role] ?? $user.role}
				</div>
			</button>

			{#if menuOpen}
				<div
					class="glass-card absolute bottom-full left-2 right-2 mb-2 py-1.5"
					style="background: var(--color-surface); backdrop-filter: none; -webkit-backdrop-filter: none;"
				>
					<div class="border-b border-[var(--color-faint)] px-4 py-2.5">
						<div class="text-xs font-medium">{$user.display_name}</div>
						<div class="text-[10px] text-[var(--color-mute)]">{$user.email ?? ''}</div>
					</div>
					<button
						class="flex w-full items-center gap-2 px-4 py-2 text-left text-xs text-red-600 transition-colors hover:bg-red-50"
						onclick={logout}
						disabled={loggingOut}
					>
						{loggingOut ? 'Wylogowywanie...' : 'Wyloguj się'}
					</button>
				</div>
			{/if}
		</div>
	{/if}
</aside>
