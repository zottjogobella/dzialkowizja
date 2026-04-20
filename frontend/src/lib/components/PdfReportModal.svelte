<script lang="ts">
	import type { PlotDetail, Transaction, Listing, Investment } from '$lib/types/plot';
	import type { RoszczenieRow, ArgumentacjaRow, MpzpFeature } from '$lib/api/plots';

	interface Props {
		open: boolean;
		plot: PlotDetail;
		roszczenieRow: RoszczenieRow | null;
		argumentacjaRow: ArgumentacjaRow | null;
		mpzpFeatures: MpzpFeature[];
		transactions: Transaction[];
		activeListings: Listing[];
		inactiveListings: Listing[];
		investments: Investment[];
		onClose: () => void;
	}

	let {
		open,
		plot,
		roszczenieRow,
		argumentacjaRow,
		mpzpFeatures,
		transactions,
		activeListings,
		inactiveListings,
		investments,
		onClose,
	}: Props = $props();

	type SectionId = 'map' | 'kw' | 'argumentacja' | 'mpzp' | 'zoning' | 'transactions' | 'listings' | 'investments';

	const SECTIONS: { id: SectionId; label: string }[] = [
		{ id: 'map', label: 'Mapa (rzuty)' },
		{ id: 'kw', label: 'Ksiega wieczysta i wlasciciel' },
		{ id: 'argumentacja', label: 'Argumentacja wyceny' },
		{ id: 'mpzp', label: 'Plan zagospodarowania' },
		{ id: 'zoning', label: 'Plan ogolny gminy' },
		{ id: 'transactions', label: 'Transakcje w okolicy' },
		{ id: 'listings', label: 'Ogloszenia w okolicy' },
		{ id: 'investments', label: 'Aktywnosc inwestycyjna' },
	];

	let selected = $state<Record<SectionId, boolean>>({
		map: true,
		kw: true,
		argumentacja: true,
		mpzp: true,
		zoning: true,
		transactions: true,
		listings: true,
		investments: true,
	});

	const available = $derived<Record<SectionId, boolean>>({
		map: true,
		kw: !!roszczenieRow,
		argumentacja: !!argumentacjaRow,
		mpzp: mpzpFeatures.length > 0,
		zoning: !!plot?.zoning_symbol,
		transactions: transactions.length > 0,
		listings: activeListings.length + inactiveListings.length > 0,
		investments: investments.length > 0,
	});

	const enabledCount = $derived(
		SECTIONS.filter((s) => available[s.id] && selected[s.id]).length,
	);

	let generating = $state(false);
	let errorMsg = $state('');

	const RODZAJ_NIERUCHOMOSCI: Record<number, string> = {
		1: 'Niezabudowana',
		2: 'Zabudowana',
		3: 'Budynkowa',
		4: 'Lokalowa',
	};
	const RODZAJ_RYNKU: Record<number, string> = { 1: 'Pierwotny', 2: 'Wtorny' };

	const OWNER_TYPE_TOKENS = new Set(['os prawna', 'os fizyczna', 'panstwo']);
	function parseOwners(raw: string): { name: string; type: string | null }[] {
		const parts = raw.split(';;').map((p) => p.trim()).filter(Boolean);
		const out: { name: string; type: string | null }[] = [];
		for (let i = 0; i < parts.length; i++) {
			const name = parts[i];
			const next = parts[i + 1];
			if (next && OWNER_TYPE_TOKENS.has(next)) {
				out.push({ name, type: next });
				i += 1;
			} else {
				out.push({ name, type: null });
			}
		}
		return out;
	}

	function fmtArea(area: number | null): string {
		if (area === null) return '\u2014';
		if (area >= 10_000) return `${(area / 10_000).toFixed(2)} ha`;
		return `${area.toFixed(0)} m\u00B2`;
	}

	function fmtPrice(val: number | null | undefined): string {
		if (val == null || val === 0) return '\u2014';
		return val.toLocaleString('pl-PL', { maximumFractionDigits: 0 }) + ' zl';
	}

	function fmtDist(val: number | null): string {
		if (val === null) return '\u2014';
		if (val >= 1000) return `${(val / 1000).toFixed(1)} km`;
		return `${val} m`;
	}

	function boolLabel(val: boolean | null): string {
		if (val === null) return '\u2014';
		return val ? 'Tak' : 'Nie';
	}

	function snapshotUrl(type: string): string {
		return `/api/plots/${encodeURIComponent(plot.id_dzialki)}/snapshot/${type}`;
	}

	const today = new Date().toLocaleDateString('pl-PL', {
		year: 'numeric',
		month: 'long',
		day: 'numeric',
	});

	const location = $derived(
		[plot?.miejscowosc, plot?.ulica, plot?.gmina].filter(Boolean).join(', ') || '',
	);

	async function waitForImages(el: HTMLElement): Promise<void> {
		const imgs = Array.from(el.querySelectorAll('img'));
		await Promise.all(
			imgs.map(
				(img) =>
					new Promise<void>((resolve) => {
						if (img.complete && img.naturalHeight > 0) resolve();
						else {
							img.onload = () => resolve();
							img.onerror = () => resolve();
						}
					}),
			),
		);
	}

	async function generatePdf() {
		generating = true;
		errorMsg = '';
		try {
			const [{ default: jsPDF }, { default: html2canvas }] = await Promise.all([
				import('jspdf'),
				import('html2canvas'),
			]);

			const reportEl = document.getElementById('pdf-report-content');
			if (!reportEl) throw new Error('Report element not found');

			// Reveal off-screen for html2canvas to capture
			reportEl.style.display = 'block';
			reportEl.style.position = 'fixed';
			reportEl.style.left = '0px';
			reportEl.style.top = '0px';
			reportEl.style.zIndex = '-9999';

			await waitForImages(reportEl);
			// Let browser finish layout
			await new Promise((r) => setTimeout(r, 400));

			const canvas = await html2canvas(reportEl, {
				scale: 2,
				useCORS: true,
				allowTaint: true,
				logging: false,
				width: 794,
				windowWidth: 794,
				backgroundColor: '#ffffff',
			});

			reportEl.style.display = 'none';

			const pdf = new jsPDF('p', 'mm', 'a4');
			const pageWidth = 210;
			const pageHeight = 297;
			const imgWidth = pageWidth;
			const imgHeight = (canvas.height * imgWidth) / canvas.width;
			const imgData = canvas.toDataURL('image/jpeg', 0.92);

			let position = 0;
			pdf.addImage(imgData, 'JPEG', 0, position, imgWidth, imgHeight);

			let heightLeft = imgHeight - pageHeight;
			while (heightLeft > 0) {
				position -= pageHeight;
				pdf.addPage();
				pdf.addImage(imgData, 'JPEG', 0, position, imgWidth, imgHeight);
				heightLeft -= pageHeight;
			}

			pdf.save(`raport_${plot.id_dzialki}.pdf`);
			onClose();
		} catch (err) {
			console.error('PDF generation failed:', err);
			errorMsg = 'Nie udalo sie wygenerowac raportu. Sprobuj ponownie.';
		} finally {
			generating = false;
		}
	}

	function handleKey(e: KeyboardEvent) {
		if (e.key === 'Escape' && open) onClose();
	}

	function toggleAll(val: boolean) {
		for (const s of SECTIONS) {
			if (available[s.id]) selected[s.id] = val;
		}
	}
</script>

<svelte:window onkeydown={handleKey} />

{#if open}
	<!-- Backdrop -->
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div class="fixed inset-0 z-40 bg-black/40" onclick={onClose}></div>

	<!-- Modal -->
	<div
		class="glass-card fixed left-1/2 top-1/2 z-50 flex max-h-[85vh] w-[min(28rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 flex-col"
		role="dialog"
		aria-modal="true"
	>
		<!-- Header -->
		<div class="flex items-center justify-between border-b border-[var(--color-faint)] px-5 py-4">
			<div>
				<div class="text-base font-semibold">Pobierz raport PDF</div>
				<div class="mt-0.5 text-xs text-[var(--color-mute)]">Wybierz sekcje do uwzglednienia w raporcie</div>
			</div>
			<button
				class="flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center rounded text-[var(--color-mute)] transition-colors hover:bg-[var(--color-glass)]"
				onclick={onClose}
				aria-label="Zamknij"
			>
				<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
					<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
				</svg>
			</button>
		</div>

		<!-- Section list -->
		<div class="flex-1 overflow-y-auto px-5 py-3">
			<div class="mb-2 flex gap-2">
				<button
					class="cursor-pointer font-mono text-[10px] text-[var(--color-accent)] hover:underline"
					onclick={() => toggleAll(true)}
				>Zaznacz wszystkie</button>
				<span class="text-[var(--color-faint)]">|</span>
				<button
					class="cursor-pointer font-mono text-[10px] text-[var(--color-mute)] hover:underline"
					onclick={() => toggleAll(false)}
				>Odznacz wszystkie</button>
			</div>

			<div class="space-y-1">
				{#each SECTIONS as section}
					{@const isAvailable = available[section.id]}
					<label
						class="flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2.5 transition-colors hover:bg-[var(--color-glass)] {!isAvailable ? 'opacity-40' : ''}"
					>
						<input
							type="checkbox"
							bind:checked={selected[section.id]}
							disabled={!isAvailable}
							class="h-4 w-4 rounded border-[var(--color-glass-border)] accent-[var(--color-accent)]"
						/>
						<span class="text-sm {!isAvailable ? 'line-through' : ''}">{section.label}</span>
						{#if !isAvailable}
							<span class="ml-auto font-mono text-[9px] text-[var(--color-mute)]">brak danych</span>
						{/if}
					</label>
				{/each}
			</div>
		</div>

		<!-- Footer -->
		<div class="border-t border-[var(--color-faint)] px-5 py-4">
			{#if errorMsg}
				<p class="mb-2 text-xs text-red-600">{errorMsg}</p>
			{/if}
			<button
				onclick={generatePdf}
				disabled={generating || enabledCount === 0}
				class="flex w-full cursor-pointer items-center justify-center gap-2 rounded-xl bg-[var(--color-accent)] px-5 py-3 font-mono text-[11px] font-semibold uppercase tracking-wider text-white transition-opacity disabled:cursor-not-allowed disabled:opacity-50"
			>
				{#if generating}
					<div class="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white"></div>
					Generowanie...
				{:else}
					<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
						<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
					</svg>
					Pobierz PDF ({enabledCount} {enabledCount === 1 ? 'sekcja' : enabledCount < 5 ? 'sekcje' : 'sekcji'})
				{/if}
			</button>
		</div>
	</div>
{/if}

<!-- Hidden report content for PDF capture -->
<div id="pdf-report-content" style="display: none; width: 794px; background: #ffffff; font-family: 'IBM Plex Sans', sans-serif; color: #0f1218; line-height: 1.5;">
	<!-- Header -->
	<div style="background: linear-gradient(135deg, #3d5a2a 0%, #4a6b33 100%); padding: 36px 44px 32px; color: white;">
		<div style="font-family: 'IBM Plex Mono', monospace; font-size: 10px; letter-spacing: 3px; text-transform: uppercase; opacity: 0.6;">RAPORT DZIALKI</div>
		<div style="font-family: 'IBM Plex Mono', monospace; font-size: 34px; font-weight: 600; margin-top: 8px; letter-spacing: -0.5px;">{plot?.id_dzialki ?? ''}</div>
		{#if location}
			<div style="font-family: 'IBM Plex Serif', serif; font-size: 18px; font-style: italic; margin-top: 6px; opacity: 0.85;">{location}</div>
		{/if}
		<div style="font-family: 'IBM Plex Mono', monospace; font-size: 10px; margin-top: 18px; opacity: 0.45;">Wygenerowano: {today} &middot; Gruntify</div>
	</div>

	<!-- Basic info bar -->
	<div style="display: flex; gap: 1px; background: #e8e8e8;">
		{#each [
			['Powierzchnia', fmtArea(plot?.area ?? null)],
			['Budowlana', boolLabel(plot?.is_buildable ?? null)],
			['Typ', plot?.lot_type ?? '\u2014'],
			['Budynki (BDOT)', String(plot?.building_count_bdot ?? '\u2014')],
		] as [label, value]}
			<div style="flex: 1; background: #f8f9fa; padding: 14px 18px;">
				<div style="font-family: 'IBM Plex Mono', monospace; font-size: 9px; letter-spacing: 1.2px; color: #6b6e76; text-transform: uppercase;">{label}</div>
				<div style="font-family: 'IBM Plex Mono', monospace; font-size: 15px; font-weight: 600; margin-top: 4px;">{value}</div>
			</div>
		{/each}
	</div>

	<div style="padding: 32px 44px 44px;">

		<!-- MAP SECTION -->
		{#if selected.map}
			<div style="margin-bottom: 32px;">
				<div style="font-family: 'IBM Plex Mono', monospace; font-size: 10px; letter-spacing: 2px; color: #6b6e76; font-weight: 600; text-transform: uppercase; margin-bottom: 14px; padding-bottom: 8px; border-bottom: 1px solid #e5e5e5;">RZUTY MAPY</div>
				<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 14px;">
					{#each [
						{ type: 'ortho', label: 'Ortofotomapa' },
						{ type: 'map', label: 'Mapa hybrydowa' },
					] as item}
						<div>
							<img
								src={snapshotUrl(item.type)}
								alt={item.label}
								crossorigin="anonymous"
								style="width: 100%; aspect-ratio: 1; object-fit: cover; border-radius: 8px; border: 1px solid #e5e5e5;"
							/>
							<div style="font-family: 'IBM Plex Mono', monospace; font-size: 10px; color: #6b6e76; margin-top: 6px; text-align: center;">{item.label}</div>
						</div>
					{/each}
				</div>
			</div>
		{/if}

		<!-- KW SECTION -->
		{#if selected.kw && roszczenieRow}
			<div style="margin-bottom: 32px;">
				<div style="font-family: 'IBM Plex Mono', monospace; font-size: 10px; letter-spacing: 2px; color: #6b6e76; font-weight: 600; text-transform: uppercase; margin-bottom: 14px; padding-bottom: 8px; border-bottom: 1px solid #e5e5e5;">KSIEGA WIECZYSTA I WLASCICIEL</div>
				<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 14px;">
					<div style="background: #f8f9fa; border-radius: 8px; padding: 16px 18px;">
						<div style="font-family: 'IBM Plex Mono', monospace; font-size: 9px; color: #6b6e76; letter-spacing: 1px; text-transform: uppercase;">NUMER KW</div>
						<div style="font-family: 'IBM Plex Mono', monospace; font-size: 16px; font-weight: 600; margin-top: 6px;">{roszczenieRow.kw ?? 'Dane ukryte'}</div>
					</div>
					<div style="background: #f8f9fa; border-radius: 8px; padding: 16px 18px;">
						<div style="font-family: 'IBM Plex Mono', monospace; font-size: 9px; color: #6b6e76; letter-spacing: 1px; text-transform: uppercase;">WLASCICIEL</div>
						{#if roszczenieRow.entities}
							{#each parseOwners(roszczenieRow.entities) as owner}
								<div style="font-family: 'IBM Plex Serif', serif; font-size: 15px; font-weight: 500; margin-top: 6px;">
									{owner.name}
									{#if owner.type}
										<span style="font-size: 11px; color: #6b6e76; margin-left: 4px;">({owner.type})</span>
									{/if}
								</div>
							{/each}
						{:else}
							<div style="font-size: 15px; color: #6b6e76; margin-top: 6px;">Dane ukryte</div>
						{/if}
					</div>
				</div>
			</div>
		{/if}

		<!-- ARGUMENTACJA SECTION -->
		{#if selected.argumentacja && argumentacjaRow}
			<div style="margin-bottom: 32px;">
				<div style="font-family: 'IBM Plex Mono', monospace; font-size: 10px; letter-spacing: 2px; color: #6b6e76; font-weight: 600; text-transform: uppercase; margin-bottom: 14px; padding-bottom: 8px; border-bottom: 1px solid #e5e5e5;">ARGUMENTACJA WYCENY</div>
				<!-- Metrics -->
				<div style="display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 10px; margin-bottom: 16px;">
					{#if argumentacjaRow.cena_ensemble != null}
						<div style="background: #f8f9fa; border-radius: 8px; padding: 12px 14px;">
							<div style="font-family: 'IBM Plex Mono', monospace; font-size: 8px; color: #6b6e76; letter-spacing: 1px;">CENA ENSEMBLE</div>
							<div style="font-family: 'IBM Plex Mono', monospace; font-size: 14px; font-weight: 600; margin-top: 4px;">{argumentacjaRow.cena_ensemble.toFixed(0)} zl/m2</div>
						</div>
					{/if}
					{#if argumentacjaRow.wartosc_total != null}
						<div style="background: #f8f9fa; border-radius: 8px; padding: 12px 14px;">
							<div style="font-family: 'IBM Plex Mono', monospace; font-size: 8px; color: #6b6e76; letter-spacing: 1px;">WARTOSC CALKOWITA</div>
							<div style="font-family: 'IBM Plex Mono', monospace; font-size: 14px; font-weight: 600; margin-top: 4px;">{argumentacjaRow.wartosc_total.toLocaleString('pl-PL', { maximumFractionDigits: 0 })} zl</div>
						</div>
					{/if}
					{#if argumentacjaRow.cena_m2_roszczenie_orig != null}
						<div style="background: #f8f9fa; border-radius: 8px; padding: 12px 14px;">
							<div style="font-family: 'IBM Plex Mono', monospace; font-size: 8px; color: #6b6e76; letter-spacing: 1px;">CENA ROSZCZENIA</div>
							<div style="font-family: 'IBM Plex Mono', monospace; font-size: 14px; font-weight: 600; margin-top: 4px;">{argumentacjaRow.cena_m2_roszczenie_orig.toFixed(0)} zl/m2</div>
						</div>
					{/if}
					{#if argumentacjaRow.wartosc_roszczenia_orig != null}
						<div style="background: #f8f9fa; border-radius: 8px; padding: 12px 14px;">
							<div style="font-family: 'IBM Plex Mono', monospace; font-size: 8px; color: #6b6e76; letter-spacing: 1px;">WARTOSC ROSZCZENIA</div>
							<div style="font-family: 'IBM Plex Mono', monospace; font-size: 14px; font-weight: 600; margin-top: 4px;">{argumentacjaRow.wartosc_roszczenia_orig.toLocaleString('pl-PL', { maximumFractionDigits: 0 })} zl</div>
						</div>
					{/if}
				</div>
				{#if argumentacjaRow.segment || argumentacjaRow.pewnosc_kategoria}
					<div style="font-family: 'IBM Plex Mono', monospace; font-size: 10px; color: #6b6e76; margin-bottom: 12px; display: flex; gap: 16px;">
						{#if argumentacjaRow.segment}
							<span>Segment: <strong style="color: #0f1218;">{argumentacjaRow.segment}</strong></span>
						{/if}
						{#if argumentacjaRow.procent_pow != null}
							<span>Pokrycie: <strong style="color: #0f1218;">{argumentacjaRow.procent_pow.toFixed(1)}%</strong></span>
						{/if}
						{#if argumentacjaRow.pewnosc_kategoria}
							<span>Pewnosc: <strong style="color: #0f1218;">{argumentacjaRow.pewnosc_kategoria} ({argumentacjaRow.pewnosc_0_100}/100)</strong></span>
						{/if}
					</div>
				{/if}
				<!-- Arguments -->
				{#if argumentacjaRow.argumenty.length > 0}
					{#each argumentacjaRow.argumenty as arg, i}
						<div style="display: grid; grid-template-columns: 36px 1fr; gap: 10px; padding: 8px 0; border-bottom: 1px dashed #e5e5e5; font-size: 12px; {i === argumentacjaRow.argumenty.length - 1 ? 'border-bottom: none;' : ''}">
							<div style="font-family: 'IBM Plex Mono', monospace; font-size: 11px; font-weight: 600; color: #3d5a2a;">{arg.waga}</div>
							<div>{arg.text}</div>
						</div>
					{/each}
				{/if}
			</div>
		{/if}

		<!-- MPZP SECTION -->
		{#if selected.mpzp && mpzpFeatures.length > 0}
			<div style="margin-bottom: 32px;">
				<div style="font-family: 'IBM Plex Mono', monospace; font-size: 10px; letter-spacing: 2px; color: #6b6e76; font-weight: 600; text-transform: uppercase; margin-bottom: 14px; padding-bottom: 8px; border-bottom: 1px solid #e5e5e5;">PLAN ZAGOSPODAROWANIA (MPZP)</div>
				{#each mpzpFeatures as feat, i}
					<div style="background: #f8f9fa; border-radius: 8px; padding: 16px 18px; margin-bottom: 10px;">
						{#if feat.tytul_planu}
							<div style="font-weight: 600; font-size: 13px; margin-bottom: 6px;">{feat.tytul_planu}</div>
						{/if}
						{#if feat.przeznaczenie}
							<div style="font-size: 12px; margin-bottom: 4px;"><span style="color: #6b6e76;">Przeznaczenie:</span> {feat.przeznaczenie}</div>
						{/if}
						{#if feat.uchwala}
							<div style="font-size: 11px; color: #6b6e76; margin-bottom: 6px;">{feat.uchwala}</div>
						{/if}
						<div style="display: flex; gap: 16px; font-size: 11px; color: #6b6e76;">
							{#if feat.status}
								<span>Status: <strong style="color: #0f1218;">{feat.status}</strong></span>
							{/if}
							{#if feat.data_uchwalenia}
								<span>Od: <strong style="color: #0f1218;">{feat.data_uchwalenia}</strong></span>
							{/if}
							{#if feat.typ_planu}
								<span>Typ: <strong style="color: #0f1218;">{feat.typ_planu}</strong></span>
							{/if}
						</div>
						{#if feat.opis}
							<div style="font-size: 12px; margin-top: 8px; white-space: pre-wrap;">{feat.opis}</div>
						{/if}
					</div>
				{/each}
			</div>
		{/if}

		<!-- ZONING SECTION -->
		{#if selected.zoning && plot?.zoning_symbol}
			<div style="margin-bottom: 32px;">
				<div style="font-family: 'IBM Plex Mono', monospace; font-size: 10px; letter-spacing: 2px; color: #6b6e76; font-weight: 600; text-transform: uppercase; margin-bottom: 14px; padding-bottom: 8px; border-bottom: 1px solid #e5e5e5;">PLAN OGOLNY GMINY</div>
				<div style="display: flex; align-items: baseline; gap: 12px; margin-bottom: 12px;">
					<span style="background: rgba(61,90,42,0.1); border: 1px solid rgba(61,90,42,0.25); color: #3d5a2a; padding: 5px 12px; border-radius: 20px; font-family: 'IBM Plex Mono', monospace; font-size: 11px; font-weight: 600; letter-spacing: 1px;">{plot.zoning_symbol}</span>
					{#if plot.zoning_name}
						<span style="font-family: 'IBM Plex Serif', serif; font-size: 15px; font-weight: 500;">{plot.zoning_name}</span>
					{/if}
				</div>
				<div style="font-size: 13px; color: #6b6e76; display: flex; flex-direction: column; gap: 6px;">
					{#if plot.zoning_max_height != null && plot.zoning_max_height > 0}
						<div>Maksymalna wysokosc zabudowy: <strong style="color: #0f1218;">{plot.zoning_max_height} m</strong></div>
					{/if}
					{#if plot.zoning_max_coverage != null && plot.zoning_max_coverage > 0}
						<div>Maks. udzial pow. zabudowy: <strong style="color: #0f1218;">{plot.zoning_max_coverage}%</strong></div>
					{/if}
					{#if plot.zoning_min_green != null && plot.zoning_min_green > 0}
						<div>Min. pow. biologicznie czynna: <strong style="color: #0f1218;">{plot.zoning_min_green}%</strong></div>
					{/if}
				</div>
			</div>
		{/if}

		<!-- TRANSACTIONS SECTION -->
		{#if selected.transactions && transactions.length > 0}
			{@const txSlice = transactions.slice(0, 25)}
			<div style="margin-bottom: 32px;">
				<div style="font-family: 'IBM Plex Mono', monospace; font-size: 10px; letter-spacing: 2px; color: #6b6e76; font-weight: 600; text-transform: uppercase; margin-bottom: 14px; padding-bottom: 8px; border-bottom: 1px solid #e5e5e5;">TRANSAKCJE W OKOLICY ({transactions.length})</div>
				<table style="width: 100%; border-collapse: collapse; font-size: 11px;">
					<thead>
						<tr style="background: #f8f9fa;">
							<th style="text-align: left; padding: 8px 6px; font-family: 'IBM Plex Mono', monospace; font-size: 8px; letter-spacing: 1px; color: #6b6e76; font-weight: 600; border-bottom: 1px solid #e5e5e5;">ODL.</th>
							<th style="text-align: left; padding: 8px 6px; font-family: 'IBM Plex Mono', monospace; font-size: 8px; letter-spacing: 1px; color: #6b6e76; font-weight: 600; border-bottom: 1px solid #e5e5e5;">DATA</th>
							<th style="text-align: left; padding: 8px 6px; font-family: 'IBM Plex Mono', monospace; font-size: 8px; letter-spacing: 1px; color: #6b6e76; font-weight: 600; border-bottom: 1px solid #e5e5e5;">MIEJSCOWOSC</th>
							<th style="text-align: right; padding: 8px 6px; font-family: 'IBM Plex Mono', monospace; font-size: 8px; letter-spacing: 1px; color: #6b6e76; font-weight: 600; border-bottom: 1px solid #e5e5e5;">POW.</th>
							<th style="text-align: right; padding: 8px 6px; font-family: 'IBM Plex Mono', monospace; font-size: 8px; letter-spacing: 1px; color: #6b6e76; font-weight: 600; border-bottom: 1px solid #e5e5e5;">CENA</th>
							<th style="text-align: right; padding: 8px 6px; font-family: 'IBM Plex Mono', monospace; font-size: 8px; letter-spacing: 1px; color: #6b6e76; font-weight: 600; border-bottom: 1px solid #e5e5e5;">ZL/M2</th>
							<th style="text-align: left; padding: 8px 6px; font-family: 'IBM Plex Mono', monospace; font-size: 8px; letter-spacing: 1px; color: #6b6e76; font-weight: 600; border-bottom: 1px solid #e5e5e5;">RODZAJ</th>
						</tr>
					</thead>
					<tbody>
						{#each txSlice as t}
							<tr>
								<td style="padding: 6px; border-bottom: 1px solid #f0f0f0; color: #6b6e76; font-family: 'IBM Plex Mono', monospace;">{fmtDist(t.distance_m)}</td>
								<td style="padding: 6px; border-bottom: 1px solid #f0f0f0; font-family: 'IBM Plex Mono', monospace;">{t.data_transakcji ?? '\u2014'}</td>
								<td style="padding: 6px; border-bottom: 1px solid #f0f0f0; max-width: 160px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{[t.miejscowosc, t.ulica].filter(Boolean).join(', ') || '\u2014'}</td>
								<td style="padding: 6px; border-bottom: 1px solid #f0f0f0; text-align: right; font-family: 'IBM Plex Mono', monospace;">{t.powierzchnia_m2 != null ? fmtArea(t.powierzchnia_m2) : '\u2014'}</td>
								<td style="padding: 6px; border-bottom: 1px solid #f0f0f0; text-align: right; font-family: 'IBM Plex Mono', monospace;">{fmtPrice(t.cena_do_analizy ?? t.cena_transakcji)}</td>
								<td style="padding: 6px; border-bottom: 1px solid #f0f0f0; text-align: right; font-family: 'IBM Plex Mono', monospace; color: #6b6e76;">{t.cena_za_m2 != null ? fmtPrice(t.cena_za_m2) : '\u2014'}</td>
								<td style="padding: 6px; border-bottom: 1px solid #f0f0f0; font-size: 10px; color: #6b6e76;">{t.rodzaj_nieruchomosci != null ? RODZAJ_NIERUCHOMOSCI[t.rodzaj_nieruchomosci] ?? '' : '\u2014'}</td>
							</tr>
						{/each}
					</tbody>
				</table>
				{#if transactions.length > 25}
					<div style="font-family: 'IBM Plex Mono', monospace; font-size: 10px; color: #6b6e76; margin-top: 8px; text-align: center;">Pokazano 25 z {transactions.length} transakcji</div>
				{/if}
			</div>
		{/if}

		<!-- LISTINGS SECTION -->
		{#if selected.listings && (activeListings.length > 0 || inactiveListings.length > 0)}
			{@const allLst = [...activeListings, ...inactiveListings].slice(0, 20)}
			<div style="margin-bottom: 32px;">
				<div style="font-family: 'IBM Plex Mono', monospace; font-size: 10px; letter-spacing: 2px; color: #6b6e76; font-weight: 600; text-transform: uppercase; margin-bottom: 14px; padding-bottom: 8px; border-bottom: 1px solid #e5e5e5;">OGLOSZENIA W OKOLICY ({activeListings.length + inactiveListings.length})</div>
				<table style="width: 100%; border-collapse: collapse; font-size: 11px;">
					<thead>
						<tr style="background: #f8f9fa;">
							<th style="text-align: left; padding: 8px 6px; font-family: 'IBM Plex Mono', monospace; font-size: 8px; letter-spacing: 1px; color: #6b6e76; font-weight: 600; border-bottom: 1px solid #e5e5e5;">NAZWA</th>
							<th style="text-align: left; padding: 8px 6px; font-family: 'IBM Plex Mono', monospace; font-size: 8px; letter-spacing: 1px; color: #6b6e76; font-weight: 600; border-bottom: 1px solid #e5e5e5;">TYP</th>
							<th style="text-align: left; padding: 8px 6px; font-family: 'IBM Plex Mono', monospace; font-size: 8px; letter-spacing: 1px; color: #6b6e76; font-weight: 600; border-bottom: 1px solid #e5e5e5;">ZRODLO</th>
							<th style="text-align: right; padding: 8px 6px; font-family: 'IBM Plex Mono', monospace; font-size: 8px; letter-spacing: 1px; color: #6b6e76; font-weight: 600; border-bottom: 1px solid #e5e5e5;">POW.</th>
							<th style="text-align: right; padding: 8px 6px; font-family: 'IBM Plex Mono', monospace; font-size: 8px; letter-spacing: 1px; color: #6b6e76; font-weight: 600; border-bottom: 1px solid #e5e5e5;">CENA</th>
						</tr>
					</thead>
					<tbody>
						{#each allLst as l}
							<tr>
								<td style="padding: 6px; border-bottom: 1px solid #f0f0f0; max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{l.name ?? 'Bez tytulu'}</td>
								<td style="padding: 6px; border-bottom: 1px solid #f0f0f0; font-size: 10px; color: #6b6e76;">{[l.property_type, l.deal_type].filter(Boolean).join(' / ')}</td>
								<td style="padding: 6px; border-bottom: 1px solid #f0f0f0; font-size: 10px; color: #6b6e76; font-family: 'IBM Plex Mono', monospace;">{l.site ?? '\u2014'}</td>
								<td style="padding: 6px; border-bottom: 1px solid #f0f0f0; text-align: right; font-family: 'IBM Plex Mono', monospace;">{l.area ? l.area + ' m\u00B2' : '\u2014'}</td>
								<td style="padding: 6px; border-bottom: 1px solid #f0f0f0; text-align: right; font-family: 'IBM Plex Mono', monospace; font-weight: 500;">{l.price ? Number(l.price).toLocaleString('pl-PL') + ' zl' : '\u2014'}</td>
							</tr>
						{/each}
					</tbody>
				</table>
				{#if activeListings.length + inactiveListings.length > 20}
					<div style="font-family: 'IBM Plex Mono', monospace; font-size: 10px; color: #6b6e76; margin-top: 8px; text-align: center;">Pokazano 20 z {activeListings.length + inactiveListings.length} ogloszen</div>
				{/if}
			</div>
		{/if}

		<!-- INVESTMENTS SECTION -->
		{#if selected.investments && investments.length > 0}
			{@const invSlice = investments.slice(0, 20)}
			<div style="margin-bottom: 32px;">
				<div style="font-family: 'IBM Plex Mono', monospace; font-size: 10px; letter-spacing: 2px; color: #6b6e76; font-weight: 600; text-transform: uppercase; margin-bottom: 14px; padding-bottom: 8px; border-bottom: 1px solid #e5e5e5;">AKTYWNOSC INWESTYCYJNA ({investments.length})</div>
				{#each invSlice as inv}
					<div style="background: #f8f9fa; border-radius: 8px; padding: 12px 16px; margin-bottom: 8px; display: grid; grid-template-columns: 90px 1fr; gap: 12px; align-items: start;">
						<div>
							<span style="display: inline-block; background: {inv.typ === 'pozwolenie_budowa' ? '#3d5a2a' : '#b8862a'}; color: white; padding: 3px 8px; border-radius: 12px; font-family: 'IBM Plex Mono', monospace; font-size: 8px; font-weight: 600; letter-spacing: 0.8px; text-transform: uppercase;">
								{inv.typ === 'pozwolenie_budowa' ? 'Pozwolenie' : inv.typ === 'zgloszenie' ? 'Zgloszenie' : inv.typ ?? ''}
							</span>
						</div>
						<div>
							{#if inv.opis}
								<div style="font-size: 12px; margin-bottom: 4px;">{inv.opis}</div>
							{/if}
							<div style="font-family: 'IBM Plex Mono', monospace; font-size: 10px; color: #6b6e76;">
								{inv.data_decyzji ?? inv.data_wniosku ?? ''}
								{#if inv.distance_m != null} &middot; {fmtDist(inv.distance_m)}{/if}
								{#if inv.miejscowosc} &middot; {inv.miejscowosc}{/if}
							</div>
						</div>
					</div>
				{/each}
				{#if investments.length > 20}
					<div style="font-family: 'IBM Plex Mono', monospace; font-size: 10px; color: #6b6e76; margin-top: 8px; text-align: center;">Pokazano 20 z {investments.length} inwestycji</div>
				{/if}
			</div>
		{/if}

		<!-- Footer -->
		<div style="margin-top: 20px; padding-top: 16px; border-top: 1px solid #e5e5e5; display: flex; justify-content: space-between; font-family: 'IBM Plex Mono', monospace; font-size: 9px; color: #a0a0a0;">
			<span>Gruntify &middot; {today}</span>
			<span>{plot?.id_dzialki ?? ''}</span>
		</div>
	</div>
</div>
