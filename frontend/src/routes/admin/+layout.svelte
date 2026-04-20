<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { user, authStatus } from '$lib/stores/auth';
	import type { Snippet } from 'svelte';

	let { children }: { children: Snippet } = $props();

	$effect(() => {
		if ($authStatus !== 'loading' && (!$user || ($user.role !== 'admin' && $user.role !== 'super_admin'))) {
			goto('/');
		}
	});

	const links = [
		{ href: '/admin/users', label: 'Uzytkownicy' },
		{ href: '/admin/stats', label: 'Statystyki' },
		{ href: '/admin/restrictions', label: 'Ukryte pola' }
	];
</script>

<div class="flex min-h-0 w-full flex-1">
	<aside class="glass-card m-0 w-56 shrink-0 rounded-none p-4">
		<h1 class="eyebrow mb-4">PANEL ORGANIZACJI</h1>
		<nav class="space-y-1">
			{#each links as link (link.href)}
				<a
					href={link.href}
					class="block rounded-[var(--r-sm)] px-3 py-2 font-mono text-[11px] transition-colors {$page.url.pathname.startsWith(link.href) ? 'bg-[rgba(61,90,42,0.08)] font-medium text-[var(--color-accent)]' : 'text-[var(--color-mute)] hover:text-[var(--color-ink)]'}"
				>
					{link.label}
				</a>
			{/each}
			<a href="/" class="mt-4 block rounded-[var(--r-sm)] px-3 py-2 font-mono text-[11px] text-[var(--color-mute)] hover:text-[var(--color-ink)]">&larr; Wroc do mapy</a>
		</nav>
	</aside>
	<main class="flex-1 overflow-y-auto p-6">
		{@render children()}
	</main>
</div>
