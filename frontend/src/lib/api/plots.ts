import type { PlotDetail, Listing, Transaction, Investment } from '$lib/types/plot';
import { apiGet } from './client';

export async function getPlot(idDzialki: string): Promise<PlotDetail> {
	return apiGet<PlotDetail>(`/api/plots/${encodeURIComponent(idDzialki)}`);
}

export async function getPlotGeometry(
	idDzialki: string
): Promise<Record<string, unknown>> {
	return apiGet<Record<string, unknown>>(
		`/api/plots/${encodeURIComponent(idDzialki)}/geometry`
	);
}

export interface ListingsResponse {
	active: Listing[];
	inactive: Listing[];
}

export async function getPlotListings(idDzialki: string): Promise<ListingsResponse> {
	return apiGet<ListingsResponse>(`/api/plots/${encodeURIComponent(idDzialki)}/listings`);
}

export type TransactionType = 'all' | 'gruntowe' | 'inne';

export async function getPlotTransactions(
	idDzialki: string,
	type: TransactionType = 'all',
	includeOutliers: boolean = false,
): Promise<Transaction[]> {
	const qs = new URLSearchParams({ type });
	if (includeOutliers) qs.set('include_outliers', 'true');
	return apiGet<Transaction[]>(
		`/api/plots/${encodeURIComponent(idDzialki)}/transactions?${qs.toString()}`,
	);
}

export interface CenaSredniaRodzaj {
	rodzaj_nieruchomosci: number;
	rodzaj_nazwa: string | null;
	liczba_transakcji: number;
	cena_za_m2_srednia: number | null;
	cena_za_m2_mediana: number | null;
	cena_za_m2_q1: number | null;
	cena_za_m2_q3: number | null;
	pow_m2_srednia: number | null;
	cena_transakcji_srednia: number | null;
	rok_min: number | null;
	rok_max: number | null;
}

export interface CenaSredniaSegment extends CenaSredniaRodzaj {
	segment_rynku: string;
	cena_za_m2_min: number | null;
	cena_za_m2_max: number | null;
}

export interface CenySrednieResponse {
	gmina_teryt: string;
	powiat_teryt: string;
	gmina: CenaSredniaRodzaj[];
	powiat_total: CenaSredniaRodzaj[];
	powiat: CenaSredniaSegment[];
}

export async function getPlotCenySrednie(idDzialki: string): Promise<CenySrednieResponse> {
	return apiGet<CenySrednieResponse>(
		`/api/plots/${encodeURIComponent(idDzialki)}/ceny-srednie`,
	);
}

export async function getPlotBuildings(
	idDzialki: string
): Promise<GeoJSON.FeatureCollection> {
	return apiGet<GeoJSON.FeatureCollection>(
		`/api/plots/${encodeURIComponent(idDzialki)}/buildings`
	);
}

export interface TransactionStat {
	date: string | null;
	price_per_m2: number;
	distance_m: number | null;
}

export interface ListingStat {
	date: string | null;
	price_per_m2: number;
	active: boolean;
}

export async function getPlotTransactionStats(idDzialki: string): Promise<TransactionStat[]> {
	return apiGet<TransactionStat[]>(
		`/api/plots/${encodeURIComponent(idDzialki)}/transactions/stats`
	);
}

export async function getPlotListingStats(idDzialki: string): Promise<ListingStat[]> {
	return apiGet<ListingStat[]>(
		`/api/plots/${encodeURIComponent(idDzialki)}/listings/stats`
	);
}

export type InvestmentType = 'all' | 'pozwolenie' | 'zgloszenie';

export async function getPlotInvestments(
	idDzialki: string,
	months: number = 24,
	type: InvestmentType = 'all',
	maxDistanceM: number = 10000,
): Promise<Investment[]> {
	const qs = new URLSearchParams({
		months: String(months),
		type,
		max_distance_m: String(maxDistanceM),
	});
	return apiGet<Investment[]>(
		`/api/investments/${encodeURIComponent(idDzialki)}?${qs.toString()}`,
	);
}

export type PowerlineSource = 'bdot' | 'osm' | 'bdot_devices';

export async function getPlotPowerlines(
	idDzialki: string,
	source: PowerlineSource,
	bufferM: number = 50,
): Promise<GeoJSON.FeatureCollection> {
	const qs = new URLSearchParams({
		source,
		buffer_m: String(bufferM),
	});
	return apiGet<GeoJSON.FeatureCollection>(
		`/api/powerlines/${encodeURIComponent(idDzialki)}?${qs.toString()}`,
	);
}

export interface MpzpFeature {
	tytul_planu: string | null;
	uchwala: string | null;
	data_uchwalenia: string | null;
	obowiazuje_do: string | null;
	status: string | null;
	typ_planu: string | null;
	przeznaczenie: string | null;
	opis: string | null;
	link_do_uchwaly: string | null;
	rysunek_url: string | null;
	dokument_przystepujacy: string | null;
	mapa_podkladowa: string | null;
	raw: Record<string, unknown>;
}

export interface MpzpResponse {
	features: MpzpFeature[];
	upstream_error?: boolean;
}

/** GetFeatureInfo against KI MPZP at the plot centroid. */
export async function getPlotMpzp(idDzialki: string): Promise<MpzpResponse | null> {
	try {
		return await apiGet<MpzpResponse>(
			`/api/mpzp/${encodeURIComponent(idDzialki)}`,
		);
	} catch (e: any) {
		const msg = String(e?.message ?? e);
		if (e?.status === 404 || msg.includes('404')) return null;
		throw e;
	}
}

export interface RoszczenieRow {
	id_dzialki: string;
	/** Total plot valuation from the sheet. Claim = this × 0.5 × coverage_fraction. */
	wartosc_dzialki: number;
	/** Prior valuation from the same sheet (CSV's `wycena_old`). Null when absent. */
	wartosc_dzialki_old: number | null;
	/** Land registry number (księga wieczysta). Null if not in the CSV. */
	kw: string | null;
	/** Owner names + type, semicolon-separated as in the source CSV. */
	entities: string | null;
	/** KW lists easements (służebności). */
	has_sluzebnosci: boolean | null;
	/** 10 or more co-owners on the title. */
	has_10_or_more_owners: boolean | null;
	/** Skarb Państwa is among the owners. */
	has_state_owner: boolean | null;
}

export interface ArgumentacjaArgument {
	text: string;
	waga: number;
}

export interface ArgumentacjaRow {
	id_dzialki: string;
	segment: string | null;
	pow_m2: number | null;
	pow_buforu: number | null;
	procent_pow: number | null;
	cena_ensemble: number | null;
	wartosc_total: number | null;
	cena_m2_roszczenie_orig: number | null;
	wartosc_roszczenia_orig: number | null;
	pewnosc_0_100: number | null;
	pewnosc_kategoria: string | null;
	argumenty: ArgumentacjaArgument[];
}

export async function getPlotArgumentacja(idDzialki: string): Promise<ArgumentacjaRow | null> {
	try {
		return await apiGet<ArgumentacjaRow>(
			`/api/argumentacja/${encodeURIComponent(idDzialki)}`,
		);
	} catch (e: any) {
		const msg = String(e?.message ?? e);
		if (e?.status === 404 || msg.includes('404')) return null;
		throw e;
	}
}

/** Return the pre-computed claim value for a plot, or null if not in the sheet. */
export async function getPlotRoszczenie(idDzialki: string): Promise<RoszczenieRow | null> {
	try {
		return await apiGet<RoszczenieRow>(
			`/api/roszczenia/${encodeURIComponent(idDzialki)}`,
		);
	} catch (e: any) {
		// apiGet throws on non-2xx — a 404 means "not in the sheet" which
		// is a valid outcome, not an error worth surfacing to the user.
		const msg = String(e?.message ?? e);
		if (e?.status === 404 || msg.includes('404')) return null;
		throw e;
	}
}

