<script lang="ts">
	import { browser } from '$app/environment';
	import 'maplibre-gl/dist/maplibre-gl.css';
	import {
		distance,
		midpoint,
		point,
		buffer,
		intersect,
		area as turfArea,
		union,
		featureCollection,
	} from '@turf/turf';
	import type { Transaction, Listing, Investment } from '$lib/types/plot';
	import {
		getPlotPowerlines,
		type PowerlineSource,
		type RoszczenieRow,
	} from '$lib/api/plots';

	interface Props {
		idDzialki: string;
		geometry: GeoJSON.Feature | Record<string, unknown> | null;
		buildings: GeoJSON.FeatureCollection | null;
		loading: boolean;
		transactions?: Transaction[];
		listings?: Listing[];
		investments?: Investment[];
		roszczenieRow?: RoszczenieRow | null;
		onPinClick?: (kind: 'transaction' | 'listing' | 'investment', id: number) => void;
	}

	let {
		idDzialki,
		geometry,
		buildings,
		loading,
		transactions = [],
		listings = [],
		investments = [],
		roszczenieRow = null,
		onPinClick,
	}: Props = $props();

	let mapContainer = $state<HTMLDivElement>(undefined!);
	let map: import('maplibre-gl').Map | undefined;
	let orthoOpacity = $state(50);
	let mapReady = $state(false);
	// First-visit hint for the "download map image" button. Persisted in
	// localStorage so it only appears once per browser.
	const DOWNLOAD_HINT_KEY = 'dzialkowizja_download_hint_seen';
	let showDownloadHint = $state(false);

	const LAYERS = [
		{ source: 'egib', label: 'EGiB', color: '#e8d5b7' },
		{ source: 'bdot', label: 'BDOT', color: '#c8bda8' },
		{ source: 'osm',  label: 'OSM',  color: '#b8c4b0' },
	] as const;

	let layerVisible = $state<Record<string, boolean>>({ egib: false, bdot: false, osm: false });
	let gesutVisible = $state(false);
	let gesutUrzadzeniaVisible = $state(false);
	let mpzpVisible = $state(false);
	let mpzpOpacity = $state(55);
	let mpzpLoadingTiles = $state(false);
	// Actual tile loading state — reflects pending tile requests on the
	// corresponding raster sources (GESUT WMS is slow: tiles can take
	// several seconds each at 2048 px).
	let gesutLoadingTiles = $state(false);
	let gesutUrzadzeniaLoadingTiles = $state(false);
	let showDimensions = $state(true);
	let buildings3d = $state(false);

	// Powerlines state — separate per source
	let bdotLinesVisible = $state(false);
	let bdotLinesBuffer = $state(10);  // default 10 m per spec
	let osmLinesVisible = $state(false);
	let osmLinesBuffer = $state(10);
	let bdotDevicesVisible = $state(false);
	// Buffered polygon FCs kept in state so a $derived can compute the
	// plot ∩ buffer intersection area reactively as the slider moves.
	let bdotBufferedFC = $state<GeoJSON.FeatureCollection | null>(null);
	let osmBufferedFC = $state<GeoJSON.FeatureCollection | null>(null);
	// Plot valuation (total zł) used by the claim calculator. When the
	// roszczenia.csv sheet has a row for the plot we auto-populate this
	// with the sheet's `wartosc_dzialki` field (see $effect below); the
	// user can still overwrite it manually.
	//
	// Claim formula (consistent across sheet and manual modes):
	//   claim = plotValuation × 0.5 × (intersection_m² / plot_area_m²)
	// The 0.5 is the easement-reduction factor (strefa ochronna lowers
	// usable value to half), and the coverage fraction makes the slider
	// meaningful.
	let plotValuationZl = $state(0);
	// Cached raw features per source (fetched on first enable, reused for buffer changes)
	let powerlineFeatures = $state<Record<PowerlineSource, GeoJSON.FeatureCollection | null>>({
		bdot: null,
		osm: null,
		bdot_devices: null,
	});
	let powerlineLoading = $state<Record<PowerlineSource, boolean>>({
		bdot: false,
		osm: false,
		bdot_devices: false,
	});

	// Pin layer visibility
	let txPinsVisible = $state(false);
	let listingPinsVisible = $state(false);
	let invPinsVisible = $state(false);

	// OSM voltage buffer presets (default 10, user can pick)
	const OSM_BUFFER_PRESETS = [5, 10, 15] as const;

	const FELT_COLORS = [
		'#50957f', '#9fa145', '#80b66d', '#7aa824', '#60759f', '#377ca4',
		'#4e8bd4', '#68c6de', '#889add', '#8f7dbf', '#9e65b3', '#bf69a2',
		'#cc625c', '#eb9360', '#d5b02a', '#f2da3a', '#ad7a67', '#826464',
		'#333333', '#808080', '#cccccc', '#ffffff',
	];

	// Plot style controls
	let plotFill = $state('#2563eb');
	let plotFillOpacity = $state(20);
	let plotStroke = $state('#1d4ed8');
	let plotStrokeWidth = $state(1.5);
	let plotStrokeOpacity = $state(80);
	let showStylePanel = $state(false);

	function getBBox(feature: any): [number, number, number, number] | null {
		const coords = extractCoords(feature.geometry);
		if (coords.length === 0) return null;
		let minLng = Infinity, minLat = Infinity, maxLng = -Infinity, maxLat = -Infinity;
		for (const [lng, lat] of coords) {
			if (lng < minLng) minLng = lng;
			if (lat < minLat) minLat = lat;
			if (lng > maxLng) maxLng = lng;
			if (lat > maxLat) maxLat = lat;
		}
		return [minLng, minLat, maxLng, maxLat];
	}

	function extractCoords(geom: any): number[][] {
		if (!geom) return [];
		switch (geom.type) {
			case 'Point': return [geom.coordinates];
			case 'MultiPoint':
			case 'LineString': return geom.coordinates;
			case 'MultiLineString':
			case 'Polygon': return geom.coordinates.flat();
			case 'MultiPolygon': return geom.coordinates.flat(2);
			default: return [];
		}
	}

	function addBuildingsLayers(m: import('maplibre-gl').Map, data: GeoJSON.FeatureCollection) {
		if (m.getSource('buildings')) {
			(m.getSource('buildings') as any).setData(data);
			return;
		}

		m.addSource('buildings', { type: 'geojson', data });

		for (const layer of LAYERS) {
			const filter: any = ['==', ['get', 'source'], layer.source];

			const vis = layerVisible[layer.source] ? 'visible' : 'none';
			const vis3d = layerVisible[layer.source] && buildings3d ? 'visible' : 'none';
			const vis2d = layerVisible[layer.source] && !buildings3d ? 'visible' : 'none';

			m.addLayer({
				id: `buildings-${layer.source}-3d`,
				type: 'fill-extrusion',
				source: 'buildings',
				filter,
				layout: { visibility: vis3d },
				paint: {
					'fill-extrusion-color': layer.color,
					'fill-extrusion-height': ['get', 'height'],
					'fill-extrusion-base': 0,
					'fill-extrusion-opacity': 0.85
				}
			});

			m.addLayer({
				id: `buildings-${layer.source}-2d`,
				type: 'fill',
				source: 'buildings',
				filter,
				layout: { visibility: vis2d },
				paint: {
					'fill-color': layer.color,
					'fill-opacity': 0.7
				}
			});

			m.addLayer({
				id: `buildings-${layer.source}-outline`,
				type: 'line',
				source: 'buildings',
				filter,
				layout: { visibility: vis },
				paint: {
					'line-color': '#8a7e6e',
					'line-width': 0.5,
					'line-opacity': 0.5
				}
			});
		}
	}

	function toggleGesut() {
		gesutVisible = !gesutVisible;
		if (!map || !mapReady) return;
		if (map.getLayer('gesut-layer')) {
			map.setLayoutProperty('gesut-layer', 'visibility', gesutVisible ? 'visible' : 'none');
		}
	}

	function toggleGesutUrzadzenia() {
		gesutUrzadzeniaVisible = !gesutUrzadzeniaVisible;
		if (!map || !mapReady) return;
		if (map.getLayer('gesut-urzadzenia-layer')) {
			map.setLayoutProperty(
				'gesut-urzadzenia-layer',
				'visibility',
				gesutUrzadzeniaVisible ? 'visible' : 'none',
			);
		}
	}

	function toggleMpzp() {
		mpzpVisible = !mpzpVisible;
		if (!map || !mapReady) return;
		if (map.getLayer('mpzp-layer')) {
			map.setLayoutProperty(
				'mpzp-layer',
				'visibility',
				mpzpVisible ? 'visible' : 'none',
			);
		}
	}

	async function ensurePowerlines(source: PowerlineSource) {
		if (powerlineFeatures[source] || powerlineLoading[source]) return;
		powerlineLoading[source] = true;
		try {
			// Fetch within a generous radius so slider changes don't require refetch
			const fc = await getPlotPowerlines(idDzialki, source, 500);
			powerlineFeatures[source] = fc;
		} catch (e) {
			console.error('Failed to fetch powerlines', source, e);
			powerlineFeatures[source] = { type: 'FeatureCollection', features: [] };
		} finally {
			powerlineLoading[source] = false;
		}
	}

	function plotAsFeature(): GeoJSON.Feature | null {
		if (!geometry) return null;
		const g = geometry as any;
		if (g.type === 'Feature') return g;
		if (g.type === 'FeatureCollection' && g.features?.[0]) return g.features[0];
		return { type: 'Feature', properties: {}, geometry: g };
	}

	function computeIntersectionArea(bufferedFC: GeoJSON.FeatureCollection | null): number {
		const plot = plotAsFeature();
		if (!plot || !bufferedFC || bufferedFC.features.length === 0) return 0;
		try {
			// Union all buffer polygons pairwise so overlapping buffers are
			// not double-counted when we intersect with the plot.
			const polys = bufferedFC.features.filter(
				(f: any) =>
					f.geometry &&
					(f.geometry.type === 'Polygon' || f.geometry.type === 'MultiPolygon'),
			);
			if (polys.length === 0) return 0;
			let merged: any = polys[0];
			for (let i = 1; i < polys.length; i++) {
				try {
					const u = union(featureCollection([merged, polys[i] as any]) as any);
					if (u) merged = u;
				} catch {
					// Pairwise union can fail on degenerate geometry — skip
					// that buffer polygon and keep going.
				}
			}
			const inter = intersect(featureCollection([plot as any, merged]) as any);
			if (!inter) return 0;
			return turfArea(inter);
		} catch (e) {
			console.warn('plot ∩ buffer area computation failed', e);
			return 0;
		}
	}

	// Reactive — updates whenever the buffered FC (which itself updates on
	// slider change) or the plot geometry changes.
	const bdotIntersectM2 = $derived(
		bdotLinesVisible && bdotLinesBuffer > 0
			? computeIntersectionArea(bdotBufferedFC)
			: 0,
	);
	const osmIntersectM2 = $derived(
		osmLinesVisible && osmLinesBuffer > 0
			? computeIntersectionArea(osmBufferedFC)
			: 0,
	);
	// Total plot area in m² from the plot polygon itself — used to express
	// the intersection as a percentage of the whole plot and to scale the
	// sheet's total claim when the user moves the buffer slider.
	const plotAreaM2 = $derived.by(() => {
		const pf = plotAsFeature();
		if (!pf) return 0;
		try {
			return turfArea(pf as any);
		} catch {
			return 0;
		}
	});
	const bdotCoveragePct = $derived(
		plotAreaM2 > 0 ? (bdotIntersectM2 / plotAreaM2) * 100 : 0,
	);
	const osmCoveragePct = $derived(
		plotAreaM2 > 0 ? (osmIntersectM2 / plotAreaM2) * 100 : 0,
	);
	// Claim = plot valuation × 0.5 × coverage fraction. Same formula for
	// sheet mode (autofill from arkusz) and manual mode (user types total
	// plot valuation in zł) — the input is always "wartość działki", not
	// a zł/m² rate, so the two modes stay consistent.
	const bdotClaimZl = $derived((plotValuationZl * 0.5 * bdotCoveragePct) / 100);
	const osmClaimZl = $derived((plotValuationZl * 0.5 * osmCoveragePct) / 100);

	function computeBufferedFC(
		fc: GeoJSON.FeatureCollection | null,
		bufferM: number,
	): GeoJSON.FeatureCollection {
		if (!fc || fc.features.length === 0 || bufferM <= 0) {
			return { type: 'FeatureCollection', features: [] };
		}
		const out: GeoJSON.Feature[] = [];
		for (const f of fc.features) {
			try {
				const b = buffer(f as any, bufferM, { units: 'meters' });
				if (b) out.push(b as GeoJSON.Feature);
			} catch {
				// skip degenerate geometry
			}
		}
		return { type: 'FeatureCollection', features: out };
	}

	function setPowerlineSourceData(source: PowerlineSource) {
		if (!map || !mapReady) return;
		const fc = powerlineFeatures[source] ?? { type: 'FeatureCollection', features: [] };
		const src = map.getSource(`pl-${source}`);
		if (src && 'setData' in src) (src as any).setData(fc);

		// Buffer only applies to line sources, not bdot_devices
		if (source === 'bdot' || source === 'osm') {
			const bufferM = source === 'bdot' ? bdotLinesBuffer : osmLinesBuffer;
			const buffered = computeBufferedFC(fc, bufferM);
			// Stash in state so the plot ∩ buffer $derived picks it up.
			if (source === 'bdot') bdotBufferedFC = buffered;
			else osmBufferedFC = buffered;
			const bufSrc = map.getSource(`pl-${source}-buffer`);
			if (bufSrc && 'setData' in bufSrc) (bufSrc as any).setData(buffered);
		}
	}

	function setPowerlineVisibility(source: PowerlineSource, visible: boolean) {
		if (!map || !mapReady) return;
		const vis = visible ? 'visible' : 'none';
		const layers = {
			bdot: ['pl-bdot-buffer-fill', 'pl-bdot-line'],
			osm: ['pl-osm-buffer-fill', 'pl-osm-line'],
			bdot_devices: ['pl-bdot_devices-point', 'pl-bdot_devices-poly-fill', 'pl-bdot_devices-poly-outline'],
		}[source];
		for (const id of layers) {
			if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', vis);
		}
	}

	async function toggleBdotLines() {
		bdotLinesVisible = !bdotLinesVisible;
		if (bdotLinesVisible) {
			await ensurePowerlines('bdot');
			setPowerlineSourceData('bdot');
		}
		setPowerlineVisibility('bdot', bdotLinesVisible);
	}

	async function toggleOsmLines() {
		osmLinesVisible = !osmLinesVisible;
		if (osmLinesVisible) {
			await ensurePowerlines('osm');
			setPowerlineSourceData('osm');
		}
		setPowerlineVisibility('osm', osmLinesVisible);
	}

	async function toggleBdotDevices() {
		bdotDevicesVisible = !bdotDevicesVisible;
		if (bdotDevicesVisible) {
			await ensurePowerlines('bdot_devices');
			setPowerlineSourceData('bdot_devices');
		}
		setPowerlineVisibility('bdot_devices', bdotDevicesVisible);
	}

	function onBdotBufferChange(v: number) {
		bdotLinesBuffer = v;
		if (bdotLinesVisible) setPowerlineSourceData('bdot');
	}

	function onOsmBufferChange(v: number) {
		osmLinesBuffer = v;
		if (osmLinesVisible) setPowerlineSourceData('osm');
	}

	function toFeatureCollection<T extends { id: number; lng: number | null; lat: number | null }>(
		items: T[],
		kind: 'transaction' | 'listing' | 'investment',
	): GeoJSON.FeatureCollection {
		const features: GeoJSON.Feature[] = [];
		for (const item of items) {
			if (item.lng == null || item.lat == null) continue;
			features.push({
				type: 'Feature',
				geometry: { type: 'Point', coordinates: [item.lng, item.lat] },
				properties: { id: item.id, kind },
			});
		}
		return { type: 'FeatureCollection', features };
	}

	function dismissDownloadHint() {
		showDownloadHint = false;
		try {
			localStorage.setItem(DOWNLOAD_HINT_KEY, '1');
		} catch {
			// localStorage may be blocked in some browsers — the hint will
			// just come back next visit, which is harmless.
		}
	}

	function downloadMapImage() {
		if (showDownloadHint) dismissDownloadHint();
		if (!map || !mapReady) return;
		// Force a synchronous render so the current state is in the drawing
		// buffer before we read it (otherwise we can get a stale frame when
		// nothing has caused a redraw recently).
		map.triggerRepaint();
		requestAnimationFrame(() => {
			if (!map) return;
			try {
				const canvas = map.getCanvas();
				canvas.toBlob((blob) => {
					if (!blob) return;
					const url = URL.createObjectURL(blob);
					const a = document.createElement('a');
					a.href = url;
					a.download = `mapa_${idDzialki.replace(/[^a-zA-Z0-9_.-]/g, '_')}.png`;
					document.body.appendChild(a);
					a.click();
					document.body.removeChild(a);
					setTimeout(() => URL.revokeObjectURL(url), 5000);
				}, 'image/png');
			} catch (e) {
				console.error('Failed to capture map image', e);
			}
		});
	}

	function togglePins(kind: 'tx' | 'listing' | 'investment') {
		if (!map || !mapReady) return;
		let visible: boolean;
		let layerId: string;
		let srcId: string;
		let fc: GeoJSON.FeatureCollection;
		if (kind === 'tx') {
			txPinsVisible = !txPinsVisible;
			visible = txPinsVisible;
			layerId = 'pins-tx';
			srcId = 'pins-tx-src';
			fc = toFeatureCollection(transactions, 'transaction');
		} else if (kind === 'listing') {
			listingPinsVisible = !listingPinsVisible;
			visible = listingPinsVisible;
			layerId = 'pins-listing';
			srcId = 'pins-listing-src';
			fc = toFeatureCollection(listings, 'listing');
		} else {
			invPinsVisible = !invPinsVisible;
			visible = invPinsVisible;
			layerId = 'pins-investment';
			srcId = 'pins-investment-src';
			fc = toFeatureCollection(investments, 'investment');
		}
		// Belt-and-suspenders: always push fresh data to the source when
		// enabling a pin layer, even if the $effect above did its job. This
		// makes the toggle-on flow deterministic regardless of any prop
		// reactivity quirks.
		if (visible) {
			const src = map.getSource(srcId);
			if (src && 'setData' in src) (src as any).setData(fc);
		}
		if (map.getLayer(layerId)) {
			map.setLayoutProperty(layerId, 'visibility', visible ? 'visible' : 'none');
		}
	}

	function countBySource(src: string): number {
		if (!buildings) return 0;
		return buildings.features.filter(f => f.properties?.source === src).length;
	}

	function computeDimensionLabels(feature: any): GeoJSON.FeatureCollection {
		const rings: number[][][] = [];
		if (feature.geometry.type === 'Polygon') {
			rings.push(feature.geometry.coordinates[0]);
		} else if (feature.geometry.type === 'MultiPolygon') {
			for (const poly of feature.geometry.coordinates) {
				rings.push(poly[0]);
			}
		}

		const features: GeoJSON.Feature[] = [];
		for (const ring of rings) {
			for (let i = 0; i < ring.length - 1; i++) {
				const a = point(ring[i] as [number, number]);
				const b = point(ring[i + 1] as [number, number]);
				const d = distance(a, b, { units: 'meters' });
				if (d < 1) continue;
				const mid = midpoint(a, b);
				const dx = ring[i + 1][0] - ring[i][0];
				const dy = ring[i + 1][1] - ring[i][1];
				let bearing = -Math.atan2(dx, dy) * (180 / Math.PI) + 90;
				// Keep text readable (not upside down)
				if (bearing > 90) bearing -= 180;
				if (bearing < -90) bearing += 180;
				mid.properties = {
					label: `${Math.round(d)} m`,
					bearing
				};
				features.push(mid);
			}
		}
		return { type: 'FeatureCollection', features };
	}

	function toggleDimensions() {
		showDimensions = !showDimensions;
		if (!map || !mapReady) return;
		if (map.getLayer('dimension-labels')) {
			map.setLayoutProperty('dimension-labels', 'visibility', showDimensions ? 'visible' : 'none');
		}
	}

	function applyPlotStyle() {
		if (!map || !mapReady) return;
		if (map.getLayer('plot-fill')) {
			map.setPaintProperty('plot-fill', 'fill-color', plotFill);
			map.setPaintProperty('plot-fill', 'fill-opacity', plotFillOpacity / 100);
		}
		if (map.getLayer('plot-border')) {
			map.setPaintProperty('plot-border', 'line-color', plotStroke);
			map.setPaintProperty('plot-border', 'line-width', plotStrokeWidth);
			map.setPaintProperty('plot-border', 'line-opacity', plotStrokeOpacity / 100);
		}
	}

	$effect(() => {
		if (!browser || !mapContainer || !geometry) return;

		let cancelled = false;

		import('maplibre-gl').then(({ Map, NavigationControl }) => {
			if (cancelled) return;

			const bbox = getBBox(geometry);
			const initCenter: [number, number] = bbox
				? [(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2]
				: [19.9, 52.2];

			map = new Map({
				container: mapContainer,
				style: {
					version: 8,
					glyphs: 'https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf',
					sources: {
						carto: {
							type: 'raster',
							tiles: ['https://basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}@2x.png'],
							tileSize: 256,
							attribution: '&copy; <a href="https://carto.com/">CARTO</a>'
						},
						ortho: {
							type: 'raster',
							// WMTS (tile cache, CDN-backed) — the WMS GetMap endpoint
							// periodically goes dead and hangs MapLibre's initial
							// render because ortho-layer is visible at opacity 0.5
							// and map.on('load') waits for visible tiles.
							tiles: [
								'https://mapy.geoportal.gov.pl/wss/service/PZGIK/ORTO/WMTS/StandardResolution?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=ORTOFOTOMAPA&TILEMATRIXSET=EPSG:3857&TILEMATRIX=EPSG:3857:{z}&TILEROW={y}&TILECOL={x}&FORMAT=image/jpeg'
							],
							tileSize: 256,
							maxzoom: 19,
							attribution: '&copy; <a href="https://geoportal.gov.pl/">Geoportal</a>'
						},
						gesut: {
							type: 'raster',
							tiles: [
								'/api/gesut/tile?bbox={bbox-epsg-3857}&width=2048&height=2048'
							],
							tileSize: 512,
							// MapLibre treats a 512-size raster as "one level ahead":
							// tiles are fetched at source_zoom = display_zoom - 1.
							// With minzoom 17 the effective floor was display zoom 18,
							// so small plots (which fitBounds lands at 17.5–17.9) never
							// triggered any tile requests. Drop to 15 so any plot
							// detail view reliably fetches electric lines.
							minzoom: 15,
							maxzoom: 20,
							attribution: '&copy; <a href="https://integracja.gugik.gov.pl/">GUGiK GESUT</a>'
						},
						'gesut-urzadzenia': {
							type: 'raster',
							tiles: [
								'/api/gesut/tile-urzadzenia?bbox={bbox-epsg-3857}&width=2048&height=2048'
							],
							tileSize: 512,
							minzoom: 15,
							maxzoom: 20,
							attribution: '&copy; <a href="https://integracja.gugik.gov.pl/">GUGiK GESUT</a>'
						},
						mpzp: {
							type: 'raster',
							tiles: [
								'/api/mpzp/tile?bbox={bbox-epsg-3857}&width=2048&height=2048'
							],
							tileSize: 512,
							// GUGiK WMS MaxScaleDenominator=10000 → data only at ~zoom 15+.
							// With tileSize 512 MapLibre fetches source_zoom = display_zoom-1,
							// so minzoom 14 here means display zoom 15 is the effective floor.
							minzoom: 14,
							attribution: '&copy; <a href="https://integracja.gugik.gov.pl/">GUGiK KI MPZP</a>'
						}
					},
					layers: [
						{ id: 'carto-layer', type: 'raster', source: 'carto' },
						{ id: 'ortho-layer', type: 'raster', source: 'ortho', paint: { 'raster-opacity': 0.5 } },
						// MPZP sits above ortho but below vector overlays added later so
						// plot borders, buildings and pins remain readable.
						{ id: 'mpzp-layer', type: 'raster', source: 'mpzp', layout: { visibility: 'none' }, paint: { 'raster-opacity': 0.55 } },
						{ id: 'gesut-layer', type: 'raster', source: 'gesut', layout: { visibility: 'none' }, paint: { 'raster-opacity': 0.9 } },
						{ id: 'gesut-urzadzenia-layer', type: 'raster', source: 'gesut-urzadzenia', layout: { visibility: 'none' }, paint: { 'raster-opacity': 0.9 } }
					]
				},
				center: initCenter,
				zoom: 15,
				pitch: 0,
				bearing: 0,
				maxPitch: 70,
				// Required so getCanvas().toDataURL() captures the rendered tiles
				// when the user triggers "Pobierz mapę"; has a small perf cost.
				// Not in MapLibre's typed MapOptions, but it IS a valid runtime
				// option passed through to the underlying WebGL context.
				preserveDrawingBuffer: true,
			} as any);

			map.addControl(new NavigationControl({ visualizePitch: true }), 'top-right');

			map.on('load', () => {
				if (cancelled || !map) return;

				// Fit bounds FIRST, before any layer adds that could fail
				if (bbox) {
					map.fitBounds(bbox as [number, number, number, number], {
						padding: 80,
						maxZoom: 19,
						duration: 0
					});
				}

				try {
					map.addSource('plot', { type: 'geojson', data: geometry as any });
					map.addLayer({
						id: 'plot-fill', type: 'fill', source: 'plot',
						paint: { 'fill-color': plotFill, 'fill-opacity': plotFillOpacity / 100 }
					});
					map.addLayer({
						id: 'plot-border', type: 'line', source: 'plot',
						paint: {
							'line-color': plotStroke,
							'line-width': plotStrokeWidth,
							'line-opacity': plotStrokeOpacity / 100
						}
					});
				} catch (e) {
					console.error('Failed to add plot layers', e);
				}

				// Dimension labels (can fail if glyphs/fonts unavailable)
				try {
					const labels = computeDimensionLabels(geometry);
					map.addSource('dimension-labels-src', { type: 'geojson', data: labels });
					map.addLayer({
						id: 'dimension-labels',
						type: 'symbol',
						source: 'dimension-labels-src',
						layout: {
							'text-field': ['get', 'label'],
							'text-size': 15,
							'text-font': ['Noto Sans Regular'],
							'text-anchor': 'center',
							'text-allow-overlap': false,
							'text-rotate': ['get', 'bearing'],
							'text-rotation-alignment': 'map',
							'text-pitch-alignment': 'map',
							visibility: showDimensions ? 'visible' : 'none'
						},
						paint: {
							'text-color': '#1e3a5f',
							'text-halo-color': '#ffffff',
							'text-halo-width': 1.5
						}
					});
				} catch (e) {
					console.error('Failed to add dimension labels', e);
				}

				// Always seed the buildings source + layers, even if the prop
				// hasn't arrived yet. If we skipped this and added buildings
				// later via the $effect below, the new layers would end up
				// stacked ABOVE the pin layers added further down and hide
				// the transaction / listing / investment pins. Seeding an
				// empty FeatureCollection now locks the z-order in place —
				// the $effect later just does setData on the existing
				// source via addBuildingsLayers' early-return branch.
				try {
					const initialBuildings: GeoJSON.FeatureCollection =
						buildings && buildings.features.length > 0
							? buildings
							: { type: 'FeatureCollection', features: [] };
					addBuildingsLayers(map, initialBuildings);
				} catch (e) {
					console.error('Failed to add buildings', e);
				}

				// Powerlines — sources/layers start empty and hidden; populated on toggle
				try {
					const empty: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features: [] };

					// BDOT lines + buffer
					map.addSource('pl-bdot', { type: 'geojson', data: empty });
					map.addSource('pl-bdot-buffer', { type: 'geojson', data: empty });
					map.addLayer({
						id: 'pl-bdot-buffer-fill', type: 'fill', source: 'pl-bdot-buffer',
						layout: { visibility: 'none' },
						paint: { 'fill-color': '#e53e3e', 'fill-opacity': 0.18 },
					});
					map.addLayer({
						id: 'pl-bdot-line', type: 'line', source: 'pl-bdot',
						layout: { visibility: 'none', 'line-cap': 'round', 'line-join': 'round' },
						paint: { 'line-color': '#c53030', 'line-width': 2.5 },
					});

					// OSM lines + buffer
					map.addSource('pl-osm', { type: 'geojson', data: empty });
					map.addSource('pl-osm-buffer', { type: 'geojson', data: empty });
					map.addLayer({
						id: 'pl-osm-buffer-fill', type: 'fill', source: 'pl-osm-buffer',
						layout: { visibility: 'none' },
						paint: { 'fill-color': '#06b6d4', 'fill-opacity': 0.22 },
					});
					map.addLayer({
						id: 'pl-osm-line', type: 'line', source: 'pl-osm',
						layout: { visibility: 'none', 'line-cap': 'round', 'line-join': 'round' },
						paint: { 'line-color': '#0e7490', 'line-width': 2.5, 'line-dasharray': [2, 1] },
					});

					// BDOT point devices (mix of Point + Polygon)
					map.addSource('pl-bdot_devices', { type: 'geojson', data: empty });
					map.addLayer({
						id: 'pl-bdot_devices-point', type: 'circle', source: 'pl-bdot_devices',
						filter: ['==', ['geometry-type'], 'Point'],
						layout: { visibility: 'none' },
						paint: {
							'circle-radius': 5,
							'circle-color': '#805ad5',
							'circle-stroke-color': '#ffffff',
							'circle-stroke-width': 1.5,
						},
					});
					map.addLayer({
						id: 'pl-bdot_devices-poly-fill', type: 'fill', source: 'pl-bdot_devices',
						filter: ['==', ['geometry-type'], 'Polygon'],
						layout: { visibility: 'none' },
						paint: { 'fill-color': '#805ad5', 'fill-opacity': 0.35 },
					});
					map.addLayer({
						id: 'pl-bdot_devices-poly-outline', type: 'line', source: 'pl-bdot_devices',
						filter: ['==', ['geometry-type'], 'Polygon'],
						layout: { visibility: 'none' },
						paint: { 'line-color': '#553c9a', 'line-width': 1.5 },
					});
				} catch (e) {
					console.error('Failed to add powerline layers', e);
				}

				// GESUT tile loading tracker — GESUT WMS can take several seconds
				// per tile, so we reflect the real pending-request state in the UI.
				try {
					map.on('dataloading', (ev: any) => {
						if (!ev?.sourceId) return;
						if (ev.sourceId === 'gesut') gesutLoadingTiles = true;
						else if (ev.sourceId === 'gesut-urzadzenia') gesutUrzadzeniaLoadingTiles = true;
						else if (ev.sourceId === 'mpzp') mpzpLoadingTiles = true;
					});
					map.on('sourcedata', (ev: any) => {
						if (!map || !ev?.sourceId) return;
						if (ev.sourceId === 'gesut') {
							gesutLoadingTiles = !map.isSourceLoaded('gesut');
						} else if (ev.sourceId === 'gesut-urzadzenia') {
							gesutUrzadzeniaLoadingTiles = !map.isSourceLoaded('gesut-urzadzenia');
						} else if (ev.sourceId === 'mpzp') {
							mpzpLoadingTiles = !map.isSourceLoaded('mpzp');
						}
					});
					// If the source never actually starts loading (e.g. because the
					// layer was toggled off before tile requests began), make sure
					// the spinner eventually clears when the map goes idle.
					map.on('idle', () => {
						gesutLoadingTiles = false;
						gesutUrzadzeniaLoadingTiles = false;
						mpzpLoadingTiles = false;
					});
				} catch (e) {
					console.error('Failed to wire GESUT loading tracker', e);
				}

				// Pinezki — transactions / listings / investments
				try {
					const empty: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features: [] };
					map.addSource('pins-tx-src', { type: 'geojson', data: toFeatureCollection(transactions, 'transaction') });
					map.addSource('pins-listing-src', { type: 'geojson', data: toFeatureCollection(listings, 'listing') });
					map.addSource('pins-investment-src', { type: 'geojson', data: toFeatureCollection(investments, 'investment') });

					map.addLayer({
						id: 'pins-tx', type: 'circle', source: 'pins-tx-src',
						layout: { visibility: 'none' },
						paint: {
							'circle-radius': 7,
							'circle-color': '#3182ce',
							'circle-stroke-color': '#ffffff',
							'circle-stroke-width': 2,
						},
					});
					map.addLayer({
						id: 'pins-listing', type: 'circle', source: 'pins-listing-src',
						layout: { visibility: 'none' },
						paint: {
							'circle-radius': 7,
							'circle-color': '#38a169',
							'circle-stroke-color': '#ffffff',
							'circle-stroke-width': 2,
						},
					});
					map.addLayer({
						id: 'pins-investment', type: 'circle', source: 'pins-investment-src',
						layout: { visibility: 'none' },
						paint: {
							'circle-radius': 7,
							'circle-color': '#d69e2e',
							'circle-stroke-color': '#ffffff',
							'circle-stroke-width': 2,
						},
					});

					// Click handlers → callback to parent
					const pinLayers = [
						{ id: 'pins-tx', kind: 'transaction' as const },
						{ id: 'pins-listing', kind: 'listing' as const },
						{ id: 'pins-investment', kind: 'investment' as const },
					];
					for (const { id, kind } of pinLayers) {
						map.on('click', id, (ev: any) => {
							const feat = ev.features?.[0];
							if (!feat) return;
							const fid = feat.properties?.id;
							if (fid != null && onPinClick) onPinClick(kind, Number(fid));
						});
						map.on('mouseenter', id, () => {
							if (map) map.getCanvas().style.cursor = 'pointer';
						});
						map.on('mouseleave', id, () => {
							if (map) map.getCanvas().style.cursor = '';
						});
					}
				} catch (e) {
					console.error('Failed to add pin layers', e);
				}

				mapReady = true;
			});
		});

		return () => {
			cancelled = true;
			mapReady = false;
			if (map) { map.remove(); map = undefined; }
		};
	});

	$effect(() => {
		if (!map || !mapReady || !buildings) return;
		if (buildings.features.length > 0) {
			addBuildingsLayers(map, buildings);
		}
	});

	// Keep pin sources in sync when transactions / listings / investments
	// props change. Each effect computes the FeatureCollection BEFORE the
	// early return so the props are always read (and therefore always
	// tracked as reactive deps) — otherwise, if map/mapReady were still
	// false on the first run, the prop reads never happened and later
	// updates from the parent wouldn't retrigger the effect, leaving the
	// source empty forever. This was the root cause of "ogłoszenia na
	// mapie pinezki nie działają".
	$effect(() => {
		const fc = toFeatureCollection(transactions, 'transaction');
		if (!map || !mapReady) return;
		const src = map.getSource('pins-tx-src');
		if (src && 'setData' in src) (src as any).setData(fc);
	});
	$effect(() => {
		const fc = toFeatureCollection(listings, 'listing');
		if (!map || !mapReady) return;
		const src = map.getSource('pins-listing-src');
		if (src && 'setData' in src) (src as any).setData(fc);
	});
	$effect(() => {
		const fc = toFeatureCollection(investments, 'investment');
		if (!map || !mapReady) return;
		const src = map.getSource('pins-investment-src');
		if (src && 'setData' in src) (src as any).setData(fc);
	});

	// Autofill the plot valuation input from the roszczenia.csv sheet
	// when the plot has a matching row. Runs once per plot load — later
	// user edits stick because we only re-sync when the incoming
	// `roszczenieRow` reference actually changes.
	$effect(() => {
		if (roszczenieRow) {
			plotValuationZl = roszczenieRow.wartosc_dzialki;
		}
	});

	// Show the download-map hint on first visit only. Waits until the map
	// has loaded (so the button is actually visible) and stops showing once
	// the user has either closed it or clicked the button itself.
	$effect(() => {
		if (!browser || loading || !mapReady) return;
		try {
			if (localStorage.getItem(DOWNLOAD_HINT_KEY)) return;
		} catch {
			return; // storage blocked — don't pester the user
		}
		const t = setTimeout(() => {
			showDownloadHint = true;
		}, 700);
		return () => clearTimeout(t);
	});

	function handleSlider(e: Event) {
		const value = parseInt((e.target as HTMLInputElement).value);
		orthoOpacity = value;
		if (map && mapReady && map.getLayer('ortho-layer')) {
			map.setPaintProperty('ortho-layer', 'raster-opacity', value / 100);
		}
	}

	function handleMpzpOpacity(e: Event) {
		const value = parseInt((e.target as HTMLInputElement).value);
		mpzpOpacity = value;
		if (map && mapReady && map.getLayer('mpzp-layer')) {
			map.setPaintProperty('mpzp-layer', 'raster-opacity', value / 100);
		}
	}

	function toggleLayer(src: string) {
		layerVisible[src] = !layerVisible[src];
		applyBuildingVisibility();
	}

	function toggleBuildings3d() {
		buildings3d = !buildings3d;
		if (!map || !mapReady) return;
		// Adjust pitch for 2D/3D
		map.easeTo({ pitch: buildings3d ? 45 : 0, duration: 400 });
		applyBuildingVisibility();
	}

	function applyBuildingVisibility() {
		if (!map || !mapReady) return;
		for (const layer of LAYERS) {
			const on = layerVisible[layer.source];
			const vis3d = on && buildings3d ? 'visible' : 'none';
			const vis2d = on && !buildings3d ? 'visible' : 'none';
			const visOutline = on ? 'visible' : 'none';
			if (map.getLayer(`buildings-${layer.source}-3d`)) {
				map.setLayoutProperty(`buildings-${layer.source}-3d`, 'visibility', vis3d);
			}
			if (map.getLayer(`buildings-${layer.source}-2d`)) {
				map.setLayoutProperty(`buildings-${layer.source}-2d`, 'visibility', vis2d);
			}
			if (map.getLayer(`buildings-${layer.source}-outline`)) {
				map.setLayoutProperty(`buildings-${layer.source}-outline`, 'visibility', visOutline);
			}
		}
	}
</script>

<div class="w-full space-y-2">
	<div class="relative h-[600px] w-full overflow-hidden rounded-xl border border-[var(--color-border)]">
		{#if loading}
			<div class="flex h-full items-center justify-center bg-[var(--color-surface)]">
				<div class="h-8 w-8 animate-spin rounded-full border-4 border-[var(--color-border)] border-t-[var(--color-primary)]"></div>
			</div>
		{:else}
			<div bind:this={mapContainer} class="h-full w-full"></div>

			<!-- Floating download button, top-left of the map -->
			<button
				onclick={downloadMapImage}
				class="absolute left-3 top-3 flex h-9 w-9 items-center justify-center rounded-lg bg-white/95 text-gray-600 shadow backdrop-blur-sm hover:bg-white hover:text-gray-900"
				title="Pobierz aktualny widok mapy"
				aria-label="Pobierz mapę"
			>
				<svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
					<path stroke-linecap="round" stroke-linejoin="round" d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2M7 10l5 5 5-5M12 15V3"/>
				</svg>
			</button>

			<!-- First-visit hint pointing at the download button -->
			{#if showDownloadHint}
				<div
					role="dialog"
					aria-label="Wskazówka: pobierz widok mapy"
					class="absolute left-14 top-3 flex max-w-xs items-start gap-2 rounded-lg bg-gray-900/95 p-3 text-xs text-white shadow-lg"
				>
					<!-- Arrow pointing left at the button -->
					<div class="absolute -left-1.5 top-3 h-3 w-3 rotate-45 bg-gray-900/95"></div>
					<div class="flex-1 leading-snug">
						<div class="font-semibold">Pobierz widok mapy</div>
						<div class="mt-0.5 text-gray-300">
							Kliknij, aby zapisać aktualny widok (z wszystkimi włączonymi warstwami) jako PNG.
						</div>
					</div>
					<button
						onclick={dismissDownloadHint}
						class="-mr-1 -mt-1 text-lg leading-none text-gray-400 hover:text-white"
						title="Zamknij wskazówkę"
						aria-label="Zamknij wskazówkę"
					>&times;</button>
				</div>
			{/if}
		{/if}
	</div>

	{#if !loading}
		<!-- Always-visible full-width controls, laid out horizontally under the map -->
		<div class="w-full rounded-xl border border-[var(--color-border)] bg-white/95 p-4 text-xs text-gray-700 shadow-sm">
			<div class="flex flex-wrap gap-x-6 gap-y-4">
						<!-- 1. Mapa bazowa -->
						<section class="min-w-[220px] flex-1">
							<h4 class="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-gray-400">Mapa bazowa</h4>
							<label class="flex items-center gap-2">
								<span>Carto</span>
								<input
									type="range" min="0" max="100"
									value={orthoOpacity}
									oninput={handleSlider}
									class="h-1.5 flex-1 cursor-pointer accent-blue-600"
								/>
								<span>Orto</span>
							</label>
						</section>

						<!-- 2. Działka -->
						<section class="min-w-[180px] flex-1">
							<h4 class="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-gray-400">Działka</h4>
							<label class="flex cursor-pointer items-center gap-2 py-1">
								<input type="checkbox" checked={showDimensions} onchange={toggleDimensions} class="accent-blue-600" />
								<span class="inline-block h-2.5 w-2.5 rounded-sm" style="background:#1e3a5f"></span>
								Wymiary boków
							</label>

							<details class="mt-1">
								<summary class="cursor-pointer select-none py-1 text-gray-600 hover:text-gray-900">
									<span class="inline-block h-2.5 w-2.5 rounded-sm border border-gray-300" style="background:{plotFill}; opacity:{plotFillOpacity / 100}"></span>
									<span class="ml-1">Styl działki</span>
								</summary>
								<div class="mt-2 space-y-3 rounded-lg bg-gray-50 p-3">
									<div>
										<label class="mb-1 flex items-center justify-between text-[11px] text-gray-500">
											<span>Wypełnienie</span>
											<span>{plotFillOpacity}%</span>
										</label>
										<div class="mb-1.5 flex flex-wrap gap-1">
											{#each FELT_COLORS as c}
												<button
													onclick={() => { plotFill = c; applyPlotStyle(); }}
													class="h-4 w-4 rounded-sm border transition-transform hover:scale-125 {plotFill === c ? 'border-gray-800 ring-1 ring-gray-400' : 'border-gray-200'}"
													style="background:{c}"
													title={c}
												></button>
											{/each}
										</div>
										<div class="flex items-center gap-2">
											<input type="color" bind:value={plotFill} oninput={applyPlotStyle} class="h-5 w-5 cursor-pointer rounded border-0 p-0" />
											<input type="range" min="0" max="100" bind:value={plotFillOpacity} oninput={applyPlotStyle} class="h-1 w-full cursor-pointer accent-blue-600" />
										</div>
									</div>
									<div>
										<label class="mb-1 flex items-center justify-between text-[11px] text-gray-500">
											<span>Obrys</span>
											<span>{plotStrokeWidth}px / {plotStrokeOpacity}%</span>
										</label>
										<div class="mb-1.5 flex flex-wrap gap-1">
											{#each FELT_COLORS as c}
												<button
													onclick={() => { plotStroke = c; applyPlotStyle(); }}
													class="h-4 w-4 rounded-sm border transition-transform hover:scale-125 {plotStroke === c ? 'border-gray-800 ring-1 ring-gray-400' : 'border-gray-200'}"
													style="background:{c}"
													title={c}
												></button>
											{/each}
										</div>
										<div class="flex items-center gap-2">
											<input type="color" bind:value={plotStroke} oninput={applyPlotStyle} class="h-5 w-5 cursor-pointer rounded border-0 p-0" />
											<input type="range" min="0" max="100" bind:value={plotStrokeOpacity} oninput={applyPlotStyle} class="h-1 w-full cursor-pointer accent-blue-600" />
										</div>
										<div class="mt-1.5">
											<label class="flex items-center gap-2 text-[11px] text-gray-500">
												<span>Grubość</span>
												<input type="range" min="0" max="10" step="0.5" bind:value={plotStrokeWidth} oninput={applyPlotStyle} class="h-1 w-full cursor-pointer accent-blue-600" />
											</label>
										</div>
									</div>
								</div>
							</details>
						</section>

						<!-- 3. Budynki -->
						{#if buildings && buildings.features.length > 0}
							<section class="min-w-[180px] flex-1">
								<div class="mb-1.5 flex items-center justify-between">
									<h4 class="text-[10px] font-semibold uppercase tracking-wider text-gray-400">Budynki</h4>
									<button
										onclick={toggleBuildings3d}
										class="rounded border border-gray-300 px-1.5 py-0.5 text-[10px] font-medium text-gray-600 hover:bg-gray-100"
									>
										{buildings3d ? '2D' : '3D'}
									</button>
								</div>
								{#each LAYERS as layer}
									{@const count = countBySource(layer.source)}
									{#if count > 0}
										<label class="flex cursor-pointer items-center gap-2 py-1">
											<input
												type="checkbox"
												checked={layerVisible[layer.source]}
												onchange={() => toggleLayer(layer.source)}
												class="accent-blue-600"
											/>
											<span class="inline-block h-2.5 w-2.5 rounded-sm" style="background:{layer.color}"></span>
											<span class="flex-1">{layer.label}</span>
											<span class="text-[10px] text-gray-400">{count}</span>
										</label>
									{/if}
								{/each}
							</section>
						{/if}

						<!-- 4. Plan zagospodarowania (KI MPZP) -->
						<section class="min-w-[200px] flex-1">
							<h4 class="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-gray-400">Plan zagospodarowania</h4>
							<label class="flex cursor-pointer items-center gap-2 py-1">
								<input type="checkbox" checked={mpzpVisible} onchange={toggleMpzp} class="accent-blue-600" />
								<span class="inline-block h-2.5 w-2.5 rounded-sm" style="background:#b45309"></span>
								<span class="flex-1">MPZP (krajowa integracja)</span>
								{#if mpzpVisible && mpzpLoadingTiles}
									<span class="h-3 w-3 animate-spin rounded-full border-2 border-gray-300 border-t-gray-600" title="Ładowanie kafli z GUGiK…"></span>
								{/if}
							</label>
							{#if mpzpVisible}
								<label class="flex items-center gap-2 pl-6 text-[11px] text-gray-500">
									<span>Przezroczystość</span>
									<input
										type="range" min="0" max="100"
										value={mpzpOpacity}
										oninput={handleMpzpOpacity}
										class="h-1.5 flex-1 cursor-pointer accent-blue-600"
									/>
									<span class="w-7 text-right">{mpzpOpacity}%</span>
								</label>
							{/if}
						</section>

						<!-- 5. Sieci uzbrojenia (GESUT WMS) -->
						<section class="min-w-[220px] flex-1">
							<h4 class="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-gray-400">Sieci uzbrojenia (GESUT)</h4>
							<label class="flex cursor-pointer items-center gap-2 py-1">
								<input type="checkbox" checked={gesutVisible} onchange={toggleGesut} class="accent-blue-600" />
								<span class="inline-block h-2.5 w-2.5 rounded-sm" style="background:#e53e3e"></span>
								<span class="flex-1">Linie elektroenergetyczne</span>
								{#if gesutVisible && gesutLoadingTiles}
									<span class="h-3 w-3 animate-spin rounded-full border-2 border-gray-300 border-t-gray-600" title="Ładowanie kafli z GUGiK…"></span>
								{/if}
							</label>
							<label class="flex cursor-pointer items-center gap-2 py-1">
								<input type="checkbox" checked={gesutUrzadzeniaVisible} onchange={toggleGesutUrzadzenia} class="accent-blue-600" />
								<span class="inline-block h-2.5 w-2.5 rounded-sm" style="background:#9f1239"></span>
								<span class="flex-1">Urządzenia uzbrojenia</span>
								{#if gesutUrzadzeniaVisible && gesutUrzadzeniaLoadingTiles}
									<span class="h-3 w-3 animate-spin rounded-full border-2 border-gray-300 border-t-gray-600" title="Ładowanie kafli z GUGiK…"></span>
								{/if}
							</label>
						</section>

						<!-- 5. Linie energetyczne (wektorowe + bufor) -->
						<section class="min-w-[280px] flex-[2]">
							<h4 class="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-gray-400">Linie energetyczne</h4>

							<label class="flex cursor-pointer items-center gap-2 py-1">
								<input type="checkbox" checked={bdotLinesVisible} onchange={toggleBdotLines} class="accent-red-600" />
								<span class="inline-block h-2.5 w-2.5 rounded-sm" style="background:#c53030"></span>
								<span class="flex-1">BDOT</span>
								{#if powerlineLoading.bdot}
									<span class="h-3 w-3 animate-spin rounded-full border-2 border-gray-300 border-t-gray-600"></span>
								{/if}
							</label>
							{#if bdotLinesVisible}
								<div class="ml-6 mb-1">
									<label class="flex items-center justify-between text-[11px] text-gray-500">
										<span>Bufor</span>
										<span>{bdotLinesBuffer} m</span>
									</label>
									<input
										type="range" min="0" max="35" step="1"
										value={bdotLinesBuffer}
										oninput={(e) => onBdotBufferChange(parseInt((e.target as HTMLInputElement).value))}
										class="h-1 w-full cursor-pointer accent-red-600"
									/>
								</div>
							{/if}

							<label class="mt-1 flex cursor-pointer items-center gap-2 py-1">
								<input type="checkbox" checked={osmLinesVisible} onchange={toggleOsmLines} class="accent-cyan-600" />
								<span class="inline-block h-2.5 w-2.5 rounded-sm" style="background:#0e7490"></span>
								<span class="flex-1">OSM</span>
								{#if powerlineLoading.osm}
									<span class="h-3 w-3 animate-spin rounded-full border-2 border-gray-300 border-t-gray-600"></span>
								{/if}
							</label>
							{#if osmLinesVisible}
								<div class="ml-6 mb-1">
									<label class="flex items-center justify-between text-[11px] text-gray-500">
										<span>Bufor</span>
										<span>{osmLinesBuffer} m</span>
									</label>
									<input
										type="range" min="0" max="35" step="1"
										value={osmLinesBuffer}
										oninput={(e) => onOsmBufferChange(parseInt((e.target as HTMLInputElement).value))}
										class="h-1 w-full cursor-pointer accent-cyan-600"
									/>
									<div class="mt-1 flex gap-1">
										{#each OSM_BUFFER_PRESETS as p}
											<button
												onclick={() => onOsmBufferChange(p)}
												class="rounded border px-1.5 py-0.5 text-[10px] {osmLinesBuffer === p ? 'border-cyan-500 bg-cyan-50 text-cyan-700' : 'border-gray-200 text-gray-500 hover:bg-gray-50'}"
											>
												{p} m
											</button>
										{/each}
									</div>
								</div>
							{/if}

							<label class="mt-1 flex cursor-pointer items-center gap-2 py-1">
								<input type="checkbox" checked={bdotDevicesVisible} onchange={toggleBdotDevices} class="accent-purple-600" />
								<span class="inline-block h-2.5 w-2.5 rounded-sm" style="background:#805ad5"></span>
								<span class="flex-1">Urządzenia BDOT</span>
								{#if powerlineLoading.bdot_devices}
									<span class="h-3 w-3 animate-spin rounded-full border-2 border-gray-300 border-t-gray-600"></span>
								{/if}
							</label>
						</section>

						<!-- 6. Pinezki -->
						<section class="min-w-[220px] flex-1">
							<h4 class="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-gray-400">Pinezki</h4>
							<label class="flex cursor-pointer items-center gap-2 py-1">
								<input type="checkbox" checked={txPinsVisible} onchange={() => togglePins('tx')} class="accent-blue-600" />
								<span class="inline-block h-2.5 w-2.5 rounded-full" style="background:#3182ce"></span>
								<span class="flex-1">Transakcje</span>
								<span class="text-[10px] text-gray-400">{transactions.filter(t => t.lng != null).length}</span>
							</label>
							<label class="flex cursor-pointer items-center gap-2 py-1">
								<input type="checkbox" checked={listingPinsVisible} onchange={() => togglePins('listing')} class="accent-green-600" />
								<span class="inline-block h-2.5 w-2.5 rounded-full" style="background:#38a169"></span>
								<span class="flex-1">Ogłoszenia</span>
								<span class="text-[10px] text-gray-400">{listings.filter(l => l.lng != null).length}</span>
							</label>
							<label class="flex cursor-pointer items-center gap-2 py-1">
								<input type="checkbox" checked={invPinsVisible} onchange={() => togglePins('investment')} class="accent-yellow-600" />
								<span class="inline-block h-2.5 w-2.5 rounded-full" style="background:#d69e2e"></span>
								<span class="flex-1">Aktywność inwestycyjna</span>
								<span class="text-[10px] text-gray-400">{investments.filter(i => i.lng != null).length}</span>
							</label>
						</section>
			</div>
		</div>

		<!-- Standalone full-width Strefa · Roszczenie section: large numbers
			 need room to breathe, and the claim values are the whole reason
			 somebody is using this view, so give them their own container. -->
		{#if bdotLinesVisible || osmLinesVisible || roszczenieRow}
			<div class="w-full rounded-xl border border-amber-200 bg-amber-50/60 p-5 shadow-sm">
				<h3 class="mb-4 text-xs font-semibold uppercase tracking-wider text-amber-700">
					Strefa · Roszczenie
				</h3>

				<div class="grid gap-6 md:grid-cols-3">
					<!-- Column 1: STREFY — intersection area per source, m² + % of plot -->
					<div>
						<div class="mb-2 text-[10px] font-semibold uppercase tracking-wider text-amber-700">
							Strefy
						</div>
						<div class="space-y-2 text-sm">
							{#if bdotLinesVisible}
								<div>
									<div class="flex items-center gap-2 text-gray-600">
										<span class="inline-block h-2.5 w-2.5 rounded-sm" style="background:#c53030"></span>
										<span>BDOT ∩ działka</span>
									</div>
									<div class="mt-0.5 flex items-baseline gap-2 pl-4 font-mono tabular-nums">
										<span class="text-gray-900">{Math.round(bdotIntersectM2).toLocaleString('pl-PL')} m²</span>
										<span class="text-xs text-gray-500">({bdotCoveragePct.toFixed(1)}% działki)</span>
									</div>
								</div>
							{/if}
							{#if osmLinesVisible}
								<div>
									<div class="flex items-center gap-2 text-gray-600">
										<span class="inline-block h-2.5 w-2.5 rounded-sm" style="background:#0e7490"></span>
										<span>OSM ∩ działka</span>
									</div>
									<div class="mt-0.5 flex items-baseline gap-2 pl-4 font-mono tabular-nums">
										<span class="text-gray-900">{Math.round(osmIntersectM2).toLocaleString('pl-PL')} m²</span>
										<span class="text-xs text-gray-500">({osmCoveragePct.toFixed(1)}% działki)</span>
									</div>
								</div>
							{/if}
							{#if !bdotLinesVisible && !osmLinesVisible}
								<div class="text-xs italic text-gray-400">
									Włącz warstwę BDOT lub OSM żeby policzyć strefę
								</div>
							{/if}
							{#if plotAreaM2 > 0 && (bdotLinesVisible || osmLinesVisible)}
								<div class="pt-1 text-[11px] text-gray-400">
									Powierzchnia działki: <span class="font-mono tabular-nums">{Math.round(plotAreaM2).toLocaleString('pl-PL')} m²</span>
								</div>
							{/if}
						</div>
					</div>

					<!-- Column 2: WARTOŚĆ DZIAŁKI — the input, prefilled from the sheet -->
					<div>
						<label class="block">
							<div class="mb-2 flex items-baseline justify-between">
								<span class="text-[10px] font-semibold uppercase tracking-wider text-amber-700">
									Wartość działki
								</span>
								{#if roszczenieRow}
									<span class="text-[10px] italic text-amber-600">z arkusza</span>
								{/if}
							</div>
							<div class="relative">
								<input
									type="number"
									min="0"
									step="0.01"
									bind:value={plotValuationZl}
									placeholder="—"
									class="w-full rounded border border-gray-300 bg-white px-2.5 py-2 pr-10 text-right font-mono text-base font-semibold tabular-nums text-amber-900"
								/>
								<span class="pointer-events-none absolute inset-y-0 right-2.5 flex items-center text-xs font-semibold text-gray-400">
									zł
								</span>
							</div>
							<div class="mt-1 text-[10px] text-gray-400">
								Roszczenie = wartość × 0,5 × (strefa / działka)
							</div>
						</label>
					</div>

					<!-- Column 3: ROSZCZENIE — wartość × 0.5 × coverage per source -->
					<div>
						<div class="mb-2 text-[10px] font-semibold uppercase tracking-wider text-amber-700">
							Wysokość roszczenia
						</div>
						{#if plotValuationZl > 0 && (bdotLinesVisible || osmLinesVisible)}
							<div class="space-y-2 text-sm">
								{#if bdotLinesVisible}
									<div>
										<div class="text-gray-600">
											BDOT
											<span class="ml-1 text-xs text-gray-400">({bdotCoveragePct.toFixed(1)}% × 0,5)</span>
										</div>
										<div class="mt-0.5 font-mono text-base font-semibold tabular-nums text-amber-800">
											{Math.round(bdotClaimZl).toLocaleString('pl-PL')} zł
										</div>
									</div>
								{/if}
								{#if osmLinesVisible}
									<div>
										<div class="text-gray-600">
											OSM
											<span class="ml-1 text-xs text-gray-400">({osmCoveragePct.toFixed(1)}% × 0,5)</span>
										</div>
										<div class="mt-0.5 font-mono text-base font-semibold tabular-nums text-amber-800">
											{Math.round(osmClaimZl).toLocaleString('pl-PL')} zł
										</div>
									</div>
								{/if}
							</div>
						{:else if !plotValuationZl}
							<div class="text-xs italic text-gray-400">
								Brak wartości działki — wpisz ją lub załaduj z arkusza
							</div>
						{:else}
							<div class="text-xs italic text-gray-400">
								Włącz warstwę BDOT lub OSM żeby policzyć roszczenie
							</div>
						{/if}
					</div>
				</div>
			</div>
		{/if}
	{/if}
</div>
