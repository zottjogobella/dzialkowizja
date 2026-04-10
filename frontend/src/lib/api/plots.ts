import type { PlotDetail, Listing, Transaction } from '$lib/types/plot';
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

