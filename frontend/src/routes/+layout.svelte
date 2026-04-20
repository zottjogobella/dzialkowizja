<script lang="ts">
	import '../app.css';
	import Sidebar from '$lib/components/Sidebar.svelte';
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

<div class="relative flex h-screen overflow-hidden" style="background: var(--color-bg);">
	{#if $authStatus === 'authenticated'}
		<!-- Ambient glow blobs -->
		<div aria-hidden="true" class="pointer-events-none absolute -top-[120px] left-[180px] h-[520px] w-[520px] rounded-full opacity-100" style="background: radial-gradient(circle, rgba(120,160,100,0.16), transparent 70%); filter: blur(60px);"></div>
		<div aria-hidden="true" class="pointer-events-none absolute top-[260px] -right-[120px] h-[480px] w-[480px] rounded-full opacity-100" style="background: radial-gradient(circle, rgba(180,160,220,0.14), transparent 70%); filter: blur(60px);"></div>

		<Sidebar />
	{/if}

	<main class="relative z-[1] flex flex-1 flex-col overflow-y-auto {$authStatus === 'authenticated' ? 'pr-[14px] py-[14px]' : ''}">
		{@render children()}
	</main>
</div>
