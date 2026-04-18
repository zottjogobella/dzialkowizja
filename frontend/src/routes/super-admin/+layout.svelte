<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { user, authStatus } from '$lib/stores/auth';
	import type { Snippet } from 'svelte';

	let { children }: { children: Snippet } = $props();

	$effect(() => {
		if ($authStatus !== 'loading' && (!$user || $user.role !== 'super_admin')) {
			goto('/');
		}
	});

	const links = [
		{ href: '/super-admin/organizations', label: 'Organizacje' },
		{ href: '/super-admin/admins', label: 'Administratorzy' },
		{ href: '/super-admin/activity', label: 'Aktywność globalna' }
	];
</script>

<div class="flex min-h-screen w-full">
	<aside class="w-56 shrink-0 border-r border-[var(--color-border)] bg-[var(--color-surface)] p-4">
		<h1 class="mb-4 text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">Super admin</h1>
		<nav class="space-y-1">
			{#each links as link (link.href)}
				<a
					href={link.href}
					class="block rounded-md px-3 py-2 text-sm transition-colors {$page.url.pathname.startsWith(link.href) ? 'bg-[var(--color-primary)] text-white' : 'text-[var(--color-primary)] hover:bg-gray-100'}"
				>
					{link.label}
				</a>
			{/each}
			<a href="/" class="mt-4 block rounded-md px-3 py-2 text-sm text-[var(--color-text-muted)] hover:bg-gray-100">← Wróć do mapy</a>
		</nav>
	</aside>
	<main class="flex-1 overflow-y-auto p-6">
		{@render children()}
	</main>
</div>
