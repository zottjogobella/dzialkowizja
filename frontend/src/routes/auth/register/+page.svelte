<script lang="ts">
	import { goto } from '$app/navigation';
	import { user, authStatus } from '$lib/stores/auth';
	import { apiPost } from '$lib/api/client';
	import type { User } from '$lib/types/auth';

	let email = $state('');
	let password = $state('');
	let displayName = $state('');
	let errors = $state<string[]>([]);
	let loading = $state(false);

	// Client-side password strength hints
	let hints = $derived.by(() => {
		const h: string[] = [];
		if (password.length > 0 && password.length < 8) h.push('Min. 8 znaków');
		if (password.length > 0 && !/[a-z]/.test(password)) h.push('Mała litera');
		if (password.length > 0 && !/[A-Z]/.test(password)) h.push('Wielka litera');
		if (password.length > 0 && !/\d/.test(password)) h.push('Cyfra');
		return h;
	});

	async function handleRegister() {
		errors = [];
		loading = true;
		try {
			const res = await apiPost<User>('/auth/register', {
				email,
				password,
				display_name: displayName
			});
			user.set(res);
			authStatus.set('authenticated');
			goto('/');
		} catch (e: any) {
			if (e.status === 409) {
				errors = ['Ten email jest już zarejestrowany'];
			} else if (e.status === 422) {
				errors = ['Sprawdź poprawność danych'];
			} else {
				errors = ['Wystąpił błąd. Spróbuj ponownie.'];
			}
		} finally {
			loading = false;
		}
	}
</script>

<svelte:head>
	<title>Rejestracja - Działkowizja</title>
</svelte:head>

<div class="flex flex-1 flex-col items-center justify-center px-6">
	<h1 class="mb-2 text-3xl font-bold text-[var(--color-primary)]">Działkowizja</h1>
	<p class="mb-8 text-[var(--color-text-muted)]">Utwórz konto</p>

	<form onsubmit={handleRegister} class="w-full max-w-sm space-y-4">
		{#if errors.length > 0}
			<div class="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">
				{#each errors as err}
					<p>{err}</p>
				{/each}
			</div>
		{/if}

		<div>
			<label for="name" class="mb-1 block text-sm font-medium">Nazwa</label>
			<input
				id="name"
				type="text"
				bind:value={displayName}
				required
				minlength={2}
				maxlength={100}
				autocomplete="name"
				class="w-full rounded-lg border border-[var(--color-border)] px-4 py-2.5 outline-none focus:ring-2 focus:ring-[var(--color-primary)]/20"
			/>
		</div>

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
				minlength={8}
				maxlength={128}
				autocomplete="new-password"
				class="w-full rounded-lg border border-[var(--color-border)] px-4 py-2.5 outline-none focus:ring-2 focus:ring-[var(--color-primary)]/20"
			/>
			{#if hints.length > 0}
				<p class="mt-1 text-xs text-amber-600">Brakuje: {hints.join(', ')}</p>
			{:else if password.length >= 8}
				<p class="mt-1 text-xs text-green-600">Hasło spełnia wymagania</p>
			{/if}
			<p class="mt-1 text-xs text-[var(--color-text-muted)]">
				Min. 8 znaków, wielka i mała litera, cyfra
			</p>
		</div>

		<button
			type="submit"
			disabled={loading}
			class="w-full rounded-lg bg-[var(--color-primary)] px-4 py-2.5 text-white transition-colors hover:opacity-90 disabled:opacity-50"
		>
			{loading ? 'Rejestracja...' : 'Zarejestruj się'}
		</button>

		<p class="text-center text-sm text-[var(--color-text-muted)]">
			Masz już konto?
			<a href="/auth/login" class="text-[var(--color-primary)] hover:underline">Zaloguj się</a>
		</p>
	</form>
</div>
