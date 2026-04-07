<script lang="ts">
	import '../app.css';
	import Sidebar from '$lib/components/Sidebar.svelte';
	import { hasSearched } from '$lib/stores/search';
	import { user, authStatus } from '$lib/stores/auth';
	import type { Snippet } from 'svelte';

	let { data, children }: { data: any; children: Snippet } = $props();

	$effect(() => {
		if (data.user) {
			user.set(data.user);
			authStatus.set('authenticated');
		} else {
			user.set(null);
			authStatus.set('unauthenticated');
		}
	});
</script>

<div class="flex h-screen">
	{#if $hasSearched && $authStatus === 'authenticated'}
		<Sidebar />
	{/if}

	<main class="flex flex-1 flex-col overflow-y-auto">
		{#if $authStatus === 'authenticated' && $user}
			<header class="flex items-center justify-end px-6 py-3">
				<span class="text-sm text-[var(--color-text-muted)]">{$user.display_name}</span>
			</header>
		{/if}

		{@render children()}
	</main>
</div>
