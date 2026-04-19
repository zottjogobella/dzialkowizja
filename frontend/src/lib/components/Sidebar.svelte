<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { historyItems, historyLoaded, loadHistory } from '$lib/stores/history';
	import { searchQuery, hasSearched } from '$lib/stores/search';
	import { user } from '$lib/stores/auth';
	import { onMount } from 'svelte';

	onMount(() => {
		if (!$historyLoaded) {
			loadHistory();
		}
	});

	function formatDate(iso: string): string {
		const d = new Date(iso);
		return d.toLocaleDateString('pl-PL', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
	}

	function rerunSearch(item: { query_text: string; query_type: string; top_result_id?: string | null }) {
		searchQuery.set(item.query_text);
		hasSearched.set(true);
		if (item.top_result_id) {
			goto(`/plot/${encodeURIComponent(item.top_result_id)}`);
		}
	}

	const ROLE_LABELS: Record<string, string> = {
		super_admin: 'Super Admin',
		admin: 'Admin',
		user: 'Użytkownik',
	};
</script>

<aside class="flex h-full w-72 shrink-0 flex-col border-r border-[var(--color-border)] bg-[var(--color-surface)]">
	<!-- Logo -->
	<a href="/" class="flex items-center gap-2.5 border-b border-[var(--color-border)] px-5 py-4">
		<div class="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--color-primary)] text-white text-sm font-bold">G</div>
		<span class="text-lg font-bold text-[var(--color-primary)]">Gruntify</span>
	</a>

	<!-- Nav links -->
	{#if $user && ($user.role === 'admin' || $user.role === 'super_admin')}
		<nav class="border-b border-[var(--color-border)] px-3 py-2.5">
			<a
				href="/admin/users"
				class="flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors {$page.url.pathname.startsWith('/admin') ? 'bg-[var(--color-primary)]/5 font-medium text-[var(--color-primary)]' : 'text-[var(--color-text-muted)] hover:bg-gray-50 hover:text-[var(--color-primary)]'}"
			>
				<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
				Panel admina
			</a>
			{#if $user.role === 'super_admin'}
				<a
					href="/super-admin/organizations"
					class="flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors {$page.url.pathname.startsWith('/super-admin') ? 'bg-[var(--color-primary)]/5 font-medium text-[var(--color-primary)]' : 'text-[var(--color-text-muted)] hover:bg-gray-50 hover:text-[var(--color-primary)]'}"
				>
					<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg>
					Super admin
				</a>
			{/if}
		</nav>
	{/if}

	<!-- History -->
	<div class="flex items-center gap-2 px-5 pt-4 pb-2">
		<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="text-[var(--color-text-muted)]">
			<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
		</svg>
		<h2 class="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">Historia wyszukiwań</h2>
	</div>

	<nav class="flex-1 overflow-y-auto px-3 pb-3">
		{#if $historyItems.length === 0}
			<p class="px-3 py-8 text-center text-sm text-[var(--color-text-muted)]">Brak historii</p>
		{:else}
			<div class="space-y-0.5">
				{#each $historyItems as item (item.id)}
					<button
						class="w-full rounded-lg px-3 py-2 text-left text-sm transition-colors hover:bg-gray-50"
						onclick={() => rerunSearch(item)}
					>
						<div class="truncate font-medium text-[var(--color-primary)]">{item.query_text}</div>
						<div class="mt-0.5 flex items-center gap-1.5 text-[11px] text-[var(--color-text-muted)]">
							<span>{item.result_count} wyników</span>
							<span>&middot;</span>
							<span>{formatDate(item.created_at)}</span>
						</div>
					</button>
				{/each}
			</div>
		{/if}
	</nav>

	<!-- User footer -->
	{#if $user}
		<div class="border-t border-[var(--color-border)] px-4 py-3">
			<div class="flex items-center gap-3">
				<div class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[var(--color-primary)]/10 text-sm font-semibold text-[var(--color-primary)]">
					{($user.display_name ?? $user.email ?? '?').charAt(0).toUpperCase()}
				</div>
				<div class="min-w-0 flex-1">
					<div class="truncate text-sm font-medium text-[var(--color-primary)]">{$user.display_name}</div>
					<div class="text-[11px] text-[var(--color-text-muted)]">{ROLE_LABELS[$user.role] ?? $user.role}</div>
				</div>
			</div>
		</div>
	{/if}
</aside>
