<script lang="ts">
	import { goto } from '$app/navigation';
	import { user, authStatus } from '$lib/stores/auth';
	import { apiPost } from '$lib/api/client';
	import type { User } from '$lib/types/auth';

	let email = $state('');
	let password = $state('');
	let showPassword = $state(false);
	let error = $state('');
	let loading = $state(false);

	async function handleLogin() {
		error = '';
		loading = true;
		try {
			const res = await apiPost<User>('/api/auth/login', { email, password });
			user.set(res);
			authStatus.set('authenticated');
			goto('/');
		} catch (e: any) {
			if (e.status === 401) {
				error = 'Nieprawidłowy email lub hasło';
			} else {
				error = 'Wystąpił błąd. Spróbuj ponownie.';
			}
		} finally {
			loading = false;
		}
	}
</script>

<svelte:head>
	<title>Zaloguj się - Działkowizja</title>
</svelte:head>

<div class="flex flex-1 flex-col items-center justify-center px-6">
	<h1 class="mb-2 text-3xl font-bold text-[var(--color-primary)]">Działkowizja</h1>
	<p class="mb-8 text-[var(--color-text-muted)]">Zaloguj się aby kontynuować</p>

	<form onsubmit={handleLogin} class="w-full max-w-sm space-y-4">
		{#if error}
			<div class="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
		{/if}

		<div>
			<label for="email" class="mb-1 block text-sm font-medium">Login</label>
			<input
				id="email"
				type="text"
				bind:value={email}
				required
				autocomplete="email"
				class="w-full rounded-lg border border-[var(--color-border)] px-4 py-2.5 outline-none focus:ring-2 focus:ring-[var(--color-primary)]/20"
			/>
		</div>

		<div>
			<label for="password" class="mb-1 block text-sm font-medium">Hasło</label>
			<div class="relative">
				<input
					id="password"
					type={showPassword ? 'text' : 'password'}
					bind:value={password}
					required
					autocomplete="current-password"
					class="w-full rounded-lg border border-[var(--color-border)] px-4 py-2.5 pr-12 outline-none focus:ring-2 focus:ring-[var(--color-primary)]/20"
				/>
				<button
					type="button"
					onclick={() => showPassword = !showPassword}
					class="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)] hover:text-[var(--color-primary)]"
					tabindex="-1"
				>
					{#if showPassword}
						<svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21"/></svg>
					{:else}
						<svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>
					{/if}
				</button>
			</div>
		</div>

		<button
			type="submit"
			disabled={loading}
			class="w-full rounded-lg bg-[var(--color-primary)] px-4 py-2.5 text-white transition-colors hover:opacity-90 disabled:opacity-50"
		>
			{loading ? 'Logowanie...' : 'Zaloguj się'}
		</button>

		<p class="text-center text-sm text-[var(--color-text-muted)]">
			Dostęp tylko na zaproszenie
		</p>
	</form>
</div>
