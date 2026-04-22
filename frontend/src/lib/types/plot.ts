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
	pog_status: string | null;
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

export interface Listing {
	id: number;
	name: string | null;
	property_type: string | null;
	deal_type: string | null;
	price: string | null;
	price_per_meter: number | null;
	area: string | null;
	city: string | null;
	url: string | null;
	site: string | null;
	publish_date: string | null;
	lng: number | null;
	lat: number | null;
}

export interface Transaction {
	id: number;
	teryt: string | null;
	wojewodztwo: string | null;
	id_dzialki: string | null;
	data_transakcji: string | null;
	rok: number | null;
	oznaczenie_dokumentu: string | null;
	tworca_dokumentu: string | null;
	cena_transakcji: number | null;
	cena_nieruchomosci: number | null;
	cena_dzialki: number | null;
	cena_do_analizy: number | null;
	kwota_vat: number | null;
	liczba_dzialek_w_transakcji: number | null;
	powierzchnia_m2: number | null;
	powierzchnia_nieruchomosci_ha: number | null;
	cena_za_m2: number | null;
	rodzaj_nieruchomosci: number | null;
	rodzaj_rynku: number | null;
	rodzaj_transakcji: number | null;
	rodzaj_prawa: number | null;
	udzial_w_prawie: string | null;
	sposob_uzytkowania: number | null;
	przeznaczenie_mpzp: string | null;
	strona_kupujaca: number | null;
	strona_sprzedajaca: number | null;
	miejscowosc: string | null;
	ulica: string | null;
	numer_porzadkowy: string | null;
	geometria_wkt: string | null;
	centroid_x: number | null;
	centroid_y: number | null;
	dodatkowe_informacje: string | null;
	distance_m: number | null;
	lng: number | null;
	lat: number | null;
	segment_rynku: string | null;
	outlier: number | null;
	do_wyceny: number | null;
	jakosc_ceny: number | null;
}

export interface Investment {
	id: number;
	typ: string | null;
	status: string | null;
	data_wniosku: string | null;
	data_decyzji: string | null;
	inwestor: string | null;
	organ: string | null;
	wojewodztwo: string | null;
	gmina: string | null;
	miejscowosc: string | null;
	teryt_gmi: string | null;
	adres: string | null;
	opis: string | null;
	kategoria: string | null;
	rodzaj_inwestycji: string | null;
	kubatura: number | null;
	parcel_id: string | null;
	source_id: string | null;
	raw_data: Record<string, unknown> | null;
	lng: number | null;
	lat: number | null;
	distance_m: number | null;
}

export interface HistoryItem {
	id: string;
	query_text: string;
	query_type: string;
	result_count: number;
	top_result_id: string | null;
	created_at: string;
}
