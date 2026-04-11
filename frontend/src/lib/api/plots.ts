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
): Promise<Transaction[]> {
	const qs = new URLSearchParams({ type });
	return apiGet<Transaction[]>(
		`/api/plots/${encodeURIComponent(idDzialki)}/transactions?${qs.toString()}`,
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
	radiusM: number = 1000,
): Promise<Investment[]> {
	const qs = new URLSearchParams({
		months: String(months),
		type,
		radius_m: String(radiusM),
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

export interface RoszczenieRow {
	id_dzialki: string;
	/** Total plot valuation from the sheet. Claim = this × 0.5 × coverage_fraction. */
	wartosc_dzialki: number;
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

