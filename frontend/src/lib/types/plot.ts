export interface PlotSummary {
	id_dzialki: string;
	gmina: string | null;
	numer_dzialki: string | null;
	miejscowosc: string | null;
	ulica: string | null;
	area: number | null;
	is_buildable: boolean | null;
	lot_type: string | null;
	zoning_symbol: string | null;
}

export interface PlotDetail extends PlotSummary {
	zoning_name: string | null;
	zoning_max_height: number | null;
	zoning_max_coverage: number | null;
	zoning_min_green: number | null;
	building_count_bdot: number | null;
	building_count_egib: number | null;
	building_count_osm: number | null;
	is_nature_protected: boolean | null;
	nature_protection: string[] | null;
	nearest_road_name: string | null;
	nearest_road_class: string | null;
	nearest_road_distance_m: number | null;
	nearest_education_m: number | null;
	nearest_healthcare_m: number | null;
	nearest_shopping_m: number | null;
	nearest_transport_m: number | null;
	has_water: boolean | null;
	has_sewage: boolean | null;
	has_gas: boolean | null;
	has_electric: boolean | null;
	has_heating: boolean | null;
	has_telecom: boolean | null;
	utility_count: number | null;
}

export interface SearchResult {
	results: PlotSummary[];
	total: number;
	query_type: string;
}

export interface HistoryItem {
	id: string;
	query_text: string;
	query_type: string;
	result_count: number;
	created_at: string;
}
