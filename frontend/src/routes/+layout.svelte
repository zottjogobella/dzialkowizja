<script lang="ts">
	import '../app.css';
	import Sidebar from '$lib/components/Sidebar.svelte';
	import { hasSearched } from '$lib/stores/search';
	import { user, authStatus } from '$lib/stores/auth';
	import type { Snippet } from 'svelte';

	let { children }: { children: Snippet } = $props();
</script>

<div class="flex h-screen">
	{#if $hasSearched && $authStatus === 'authenticated'}
		<Sidebar />
	{/if}

	<main class="flex flex-1 flex-col overflow-y-auto">
		<!-- Top bar -->
		<header class="flex items-center justify-end px-6 py-3">
			{#if $authStatus === 'authenticated' && $user}
				<div class="flex items-center gap-3">
					{#if $user.avatar_url}
						<img src={$user.avatar_url} alt="" class="h-8 w-8 rounded-full" />
					{/if}
					<span class="text-sm text-[var(--color-text-muted)]">{$user.display_name}</span>
				</div>
			{:else if $authStatus === 'unauthenticated'}
				<a
					href="/auth/login"
					class="rounded-lg bg-[var(--color-primary)] px-4 py-2 text-sm text-white transition-colors hover:opacity-90"
				>
					Zaloguj się
				</a>
			{/if}
		</header>

		{@render children()}
	</main>
</div>
