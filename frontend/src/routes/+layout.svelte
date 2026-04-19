<script lang="ts">
	import '../app.css';
	import Sidebar from '$lib/components/Sidebar.svelte';
	import { user, authStatus } from '$lib/stores/auth';
	import { apiFetch } from '$lib/api/client';
	import type { Snippet } from 'svelte';

	let { data, children }: { data: any; children: Snippet } = $props();
	let menuOpen = $state(false);
	let loggingOut = $state(false);

	$effect(() => {
		if (data.user) {
			user.set(data.user);
			authStatus.set('authenticated');
		} else {
			user.set(null);
			authStatus.set('unauthenticated');
		}
	});

	async function logout() {
		loggingOut = true;
		try {
			await apiFetch('/api/auth/logout', { method: 'POST' });
		} catch {
			// ignore
		}
		user.set(null);
		authStatus.set('unauthenticated');
		window.location.href = '/auth/login';
	}

	function handleClickOutside(e: MouseEvent) {
		const target = e.target as HTMLElement;
		if (!target.closest('[data-user-menu]')) {
			menuOpen = false;
		}
	}

	const ROLE_LABELS: Record<string, string> = {
		super_admin: 'Super Admin',
		admin: 'Admin',
		user: 'Użytkownik',
	};
</script>

<svelte:window onclick={handleClickOutside} />

<div class="flex h-screen">
	{#if $authStatus === 'authenticated'}
		<Sidebar />
	{/if}

	<main class="flex flex-1 flex-col overflow-y-auto">
		{#if $authStatus === 'authenticated' && $user}
			<header class="flex items-center justify-end border-b border-[var(--color-border)] px-6 py-2.5">
				<div class="relative" data-user-menu>
					<button
						class="flex items-center gap-2.5 rounded-lg px-3 py-1.5 transition-colors hover:bg-gray-50"
						onclick={() => (menuOpen = !menuOpen)}
					>
						<div class="text-right">
							<div class="text-sm font-medium text-[var(--color-primary)]">{$user.display_name}</div>
							<div class="text-[11px] text-[var(--color-text-muted)]">{ROLE_LABELS[$user.role] ?? $user.role}</div>
						</div>
						<!-- Person icon -->
						<div class="flex h-8 w-8 items-center justify-center rounded-full bg-[var(--color-primary)]/10 text-[var(--color-primary)]">
							<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
								<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/>
								<circle cx="12" cy="7" r="4"/>
							</svg>
						</div>
					</button>

					{#if menuOpen}
						<div class="absolute right-0 top-full z-50 mt-1 w-56 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] py-1.5 shadow-lg">
							<div class="border-b border-[var(--color-border)] px-4 py-2.5">
								<div class="text-sm font-medium text-[var(--color-primary)]">{$user.display_name}</div>
								<div class="text-xs text-[var(--color-text-muted)]">{$user.email ?? ''}</div>
							</div>
							<div class="py-1">
								<button
									class="flex w-full items-center gap-2.5 px-4 py-2 text-left text-sm text-red-600 transition-colors hover:bg-red-50"
									onclick={logout}
									disabled={loggingOut}
								>
									<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
										<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
										<polyline points="16 17 21 12 16 7"/>
										<line x1="21" y1="12" x2="9" y2="12"/>
									</svg>
									{loggingOut ? 'Wylogowywanie...' : 'Wyloguj się'}
								</button>
							</div>
						</div>
					{/if}
				</div>
			</header>
		{/if}

		{@render children()}
	</main>
</div>
