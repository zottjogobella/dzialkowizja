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

export async function getPlotTransactions(idDzialki: string): Promise<Transaction[]> {
	return apiGet<Transaction[]>(`/api/plots/${encodeURIComponent(idDzialki)}/transactions`);
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

export interface GesutVectorResponse extends GeoJSON.FeatureCollection {
	meta?: {
		raw_contour_count?: number;
		kept_line_count?: number;
		non_zero_pixels?: number;
		error?: string;
	};
}

/** POC: vectorize GESUT electric lines inside a 3857 bbox. */
export async function getGesutVector(
	bbox3857: [number, number, number, number],
): Promise<GesutVectorResponse> {
	const qs = new URLSearchParams({ bbox: bbox3857.join(',') });
	return apiGet<GesutVectorResponse>(`/api/gesut/vector?${qs.toString()}`);
}

