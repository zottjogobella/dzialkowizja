<script lang="ts">
	import SearchInput from '$lib/components/SearchInput.svelte';
	import { hasSearched } from '$lib/stores/search';
</script>

<svelte:head>
	<title>Gruntify</title>
</svelte:head>

<div class="flex flex-col gap-[14px]">
	<!-- Masthead card -->
	<div class="glass-card" style="padding: 32px 34px 28px;">
		<div class="eyebrow mb-3.5">&mdash; REJESTR DZIALEK EWIDENCYJNYCH &middot; POLSKA</div>
		<div class="grid items-end gap-8" style="grid-template-columns: 1fr auto;">
			<div>
				<h1 class="font-serif leading-none" style="font-size: 56px; font-weight: 500; letter-spacing: -1.5px; margin-bottom: 10px;">Gruntify</h1>
				<p class="text-[15px] leading-relaxed text-[var(--color-mute)]" style="max-width: 460px;">
					Sprawdz dane o dowolnej dzialce w Polsce. Numer ewidencyjny, adres lub TERYT.
				</p>
			</div>
			<div class="flex gap-2.5">
				{#each [
					{ label: 'POKRYCIE', value: '38M', sub: 'dzialek' },
					{ label: 'GMINY', value: '2 477', sub: 'w bazie' },
				] as stat}
					<div class="glass-chip px-[18px] py-[14px]" style="min-width: 130px;">
						<div class="eyebrow" style="font-size: 9.5px; letter-spacing: 1.2px;">{stat.label}</div>
						<div class="font-serif" style="font-size: 28px; font-weight: 500; letter-spacing: -0.8px; margin-top: 4px;">{stat.value}</div>
						<div class="font-mono text-[10px] text-[var(--color-mute)]" style="margin-top: 2px;">{stat.sub}</div>
					</div>
				{/each}
			</div>
		</div>
	</div>

	<!-- Search card -->
	<div class="glass-card p-[18px]">
		<SearchInput />
	</div>

</div>
