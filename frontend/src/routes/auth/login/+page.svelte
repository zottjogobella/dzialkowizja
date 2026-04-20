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
	<title>Zaloguj się - Gruntify</title>
</svelte:head>

<div class="flex flex-1 flex-col items-center justify-center px-6" style="background: var(--color-bg);">
	<!-- Ambient glow -->
	<div aria-hidden="true" class="pointer-events-none absolute -top-[80px] left-1/4 h-[400px] w-[400px] rounded-full" style="background: radial-gradient(circle, rgba(120,160,100,0.16), transparent 70%); filter: blur(60px);"></div>

	<div class="glass-card w-full max-w-sm p-8">
		<div class="mb-6 text-center">
			<div class="mx-auto mb-3 grid h-10 w-10 place-items-center rounded-[10px] bg-[var(--color-ink)] font-mono text-lg font-semibold text-white">G</div>
			<h1 class="font-serif text-2xl font-medium" style="letter-spacing: -0.5px;">Gruntify</h1>
			<p class="mt-1 text-sm text-[var(--color-mute)]">Zaloguj się aby kontynuować</p>
		</div>

		<form onsubmit={handleLogin} class="space-y-4">
			{#if error}
				<div class="glass-chip p-3 text-sm text-red-700" style="background: rgba(220,50,50,0.08); border-color: rgba(220,50,50,0.2);">{error}</div>
			{/if}

			<div>
				<label for="email" class="eyebrow mb-1.5 block">LOGIN</label>
				<input
					id="email"
					type="text"
					bind:value={email}
					required
					autocomplete="email"
					class="glass-chip w-full px-4 py-2.5 outline-none"
					style="font-family: var(--font-sans);"
				/>
			</div>

			<div>
				<label for="password" class="eyebrow mb-1.5 block">HASŁO</label>
				<div class="relative">
					<input
						id="password"
						type={showPassword ? 'text' : 'password'}
						bind:value={password}
						required
						autocomplete="current-password"
						class="glass-chip w-full px-4 py-2.5 pr-12 outline-none"
						style="font-family: var(--font-sans);"
					/>
					<button
						type="button"
						onclick={() => showPassword = !showPassword}
						class="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--color-mute)] hover:text-[var(--color-ink)]"
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
				class="w-full cursor-pointer rounded-[var(--r-sm)] border-none px-4 py-2.5 font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
				style="background: var(--color-accent);"
			>
				{loading ? 'Logowanie...' : 'Zaloguj się'}
			</button>

			<p class="text-center font-mono text-[10px] text-[var(--color-mute)]">
				Dostęp tylko na zaproszenie
			</p>
		</form>
	</div>
</div>
