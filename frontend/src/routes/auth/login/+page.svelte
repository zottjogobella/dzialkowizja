<script lang="ts">
	import { goto } from '$app/navigation';
	import { user, authStatus } from '$lib/stores/auth';
	import { apiPost } from '$lib/api/client';
	import type { User } from '$lib/types/auth';

	let email = $state('');
	let password = $state('');
	let error = $state('');
	let loading = $state(false);

	async function handleLogin() {
		error = '';
		loading = true;
		try {
			const res = await apiPost<User>('/auth/login', { email, password });
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
			<label for="email" class="mb-1 block text-sm font-medium">Email</label>
			<input
				id="email"
				type="email"
				bind:value={email}
				required
				autocomplete="email"
				class="w-full rounded-lg border border-[var(--color-border)] px-4 py-2.5 outline-none focus:ring-2 focus:ring-[var(--color-primary)]/20"
			/>
		</div>

		<div>
			<label for="password" class="mb-1 block text-sm font-medium">Hasło</label>
			<input
				id="password"
				type="password"
				bind:value={password}
				required
				autocomplete="current-password"
				class="w-full rounded-lg border border-[var(--color-border)] px-4 py-2.5 outline-none focus:ring-2 focus:ring-[var(--color-primary)]/20"
			/>
		</div>

		<button
			type="submit"
			disabled={loading}
			class="w-full rounded-lg bg-[var(--color-primary)] px-4 py-2.5 text-white transition-colors hover:opacity-90 disabled:opacity-50"
		>
			{loading ? 'Logowanie...' : 'Zaloguj się'}
		</button>

		<p class="text-center text-sm text-[var(--color-text-muted)]">
			Nie masz konta?
			<a href="/auth/register" class="text-[var(--color-primary)] hover:underline">Zarejestruj się</a>
		</p>
	</form>
</div>
