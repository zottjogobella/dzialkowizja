<script lang="ts">
	import { browser } from '$app/environment';
	import 'maplibre-gl/dist/maplibre-gl.css';
	import { distance, midpoint, point, buffer } from '@turf/turf';
	import type { Transaction, Listing, Investment } from '$lib/types/plot';
	import { getPlotPowerlines, type PowerlineSource } from '$lib/api/plots';

	interface Props {
		idDzialki: string;
		geometry: GeoJSON.Feature | Record<string, unknown> | null;
		buildings: GeoJSON.FeatureCollection | null;
		loading: boolean;
		transactions?: Transaction[];
		listings?: Listing[];
		investments?: Investment[];
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
		onPinClick,
	}: Props = $props();

	let mapContainer = $state<HTMLDivElement>(undefined!);
	let map: import('maplibre-gl').Map | undefined;
	let orthoOpacity = $state(50);
	let mapReady = $state(false);
	let panelOpen = $state(true);

	const LAYERS = [
		{ source: 'egib', label: 'EGiB', color: '#e8d5b7' },
		{ source: 'bdot', label: 'BDOT', color: '#c8bda8' },
		{ source: 'osm',  label: 'OSM',  color: '#b8c4b0' },
	] as const;

	let layerVisible = $state<Record<string, boolean>>({ egib: false, bdot: false, osm: false });
	let gesutVisible = $state(false);
	let gesutUrzadzeniaVisible = $state(false);
	let showDimensions = $state(true);
	let buildings3d = $state(true);

	// Powerlines state — separate per source
	let bdotLinesVisible = $state(false);
	let bdotLinesBuffer = $state(10);  // default 10 m per spec
	let osmLinesVisible = $state(false);
	let osmLinesBuffer = $state(10);
	let bdotDevicesVisible = $state(false);
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

	function togglePins(kind: 'tx' | 'listing' | 'investment') {
		if (!map || !mapReady) return;
		let visible: boolean;
		let layerId: string;
		if (kind === 'tx') {
			txPinsVisible = !txPinsVisible;
			visible = txPinsVisible;
			layerId = 'pins-tx';
		} else if (kind === 'listing') {
			listingPinsVisible = !listingPinsVisible;
			visible = listingPinsVisible;
			layerId = 'pins-listing';
		} else {
			invPinsVisible = !invPinsVisible;
			visible = invPinsVisible;
			layerId = 'pins-investment';
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
								'/api/gesut/tile?bbox={bbox-epsg-3857}&width=512&height=512'
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
								'/api/gesut/tile-urzadzenia?bbox={bbox-epsg-3857}&width=512&height=512'
							],
							tileSize: 512,
							minzoom: 15,
							maxzoom: 20,
							attribution: '&copy; <a href="https://integracja.gugik.gov.pl/">GUGiK GESUT</a>'
						}
					},
					layers: [
						{ id: 'carto-layer', type: 'raster', source: 'carto' },
						{ id: 'ortho-layer', type: 'raster', source: 'ortho', paint: { 'raster-opacity': 0.5 } },
						{ id: 'gesut-layer', type: 'raster', source: 'gesut', layout: { visibility: 'none' }, paint: { 'raster-opacity': 0.9 } },
						{ id: 'gesut-urzadzenia-layer', type: 'raster', source: 'gesut-urzadzenia', layout: { visibility: 'none' }, paint: { 'raster-opacity': 0.9 } }
					]
				},
				center: initCenter,
				zoom: 15,
				pitch: 45,
				bearing: -15,
				maxPitch: 70
			});

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

				try {
					if (buildings && buildings.features.length > 0) {
						addBuildingsLayers(map, buildings);
					}
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
						paint: { 'fill-color': '#dd6b20', 'fill-opacity': 0.18 },
					});
					map.addLayer({
						id: 'pl-osm-line', type: 'line', source: 'pl-osm',
						layout: { visibility: 'none', 'line-cap': 'round', 'line-join': 'round' },
						paint: { 'line-color': '#c05621', 'line-width': 2.5, 'line-dasharray': [2, 1] },
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

	// Keep pin sources in sync when transactions/listings/investments props change
	$effect(() => {
		if (!map || !mapReady) return;
		const src = map.getSource('pins-tx-src');
		if (src && 'setData' in src) (src as any).setData(toFeatureCollection(transactions, 'transaction'));
	});
	$effect(() => {
		if (!map || !mapReady) return;
		const src = map.getSource('pins-listing-src');
		if (src && 'setData' in src) (src as any).setData(toFeatureCollection(listings, 'listing'));
	});
	$effect(() => {
		if (!map || !mapReady) return;
		const src = map.getSource('pins-investment-src');
		if (src && 'setData' in src) (src as any).setData(toFeatureCollection(investments, 'investment'));
	});

	function handleSlider(e: Event) {
		const value = parseInt((e.target as HTMLInputElement).value);
		orthoOpacity = value;
		if (map && mapReady && map.getLayer('ortho-layer')) {
			map.setPaintProperty('ortho-layer', 'raster-opacity', value / 100);
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

<div class="relative h-[500px] w-full overflow-hidden rounded-xl border border-[var(--color-border)]">
	{#if loading}
		<div class="flex h-full items-center justify-center bg-[var(--color-surface)]">
			<div class="h-8 w-8 animate-spin rounded-full border-4 border-[var(--color-border)] border-t-[var(--color-primary)]"></div>
		</div>
	{:else}
		<div bind:this={mapContainer} class="h-full w-full"></div>

		<!-- Left side: controls panel (collapsible, open by default) -->
		<div class="pointer-events-none absolute inset-y-3 left-3 flex items-start">
			{#if panelOpen}
				<div
					class="pointer-events-auto flex max-h-full w-72 flex-col overflow-hidden rounded-xl bg-white/95 shadow-lg backdrop-blur-sm"
				>
					<div class="flex items-center justify-between border-b border-gray-100 px-4 py-2.5">
						<span class="text-xs font-semibold uppercase tracking-wider text-gray-700">Warstwy mapy</span>
						<button
							onclick={() => (panelOpen = false)}
							class="text-lg leading-none text-gray-400 hover:text-gray-700"
							title="Zwiń panel"
							aria-label="Zwiń panel"
						>&times;</button>
					</div>

					<div class="flex-1 space-y-4 overflow-y-auto px-4 py-3 text-xs text-gray-700">
						<!-- 1. Mapa bazowa -->
						<section>
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
						<section>
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
							<section>
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

						<!-- 4. Sieci uzbrojenia (GESUT WMS) -->
						<section>
							<h4 class="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-gray-400">Sieci uzbrojenia (GESUT)</h4>
							<label class="flex cursor-pointer items-center gap-2 py-1">
								<input type="checkbox" checked={gesutVisible} onchange={toggleGesut} class="accent-blue-600" />
								<span class="inline-block h-2.5 w-2.5 rounded-sm" style="background:#e53e3e"></span>
								Linie elektroenergetyczne
							</label>
							<label class="flex cursor-pointer items-center gap-2 py-1">
								<input type="checkbox" checked={gesutUrzadzeniaVisible} onchange={toggleGesutUrzadzenia} class="accent-blue-600" />
								<span class="inline-block h-2.5 w-2.5 rounded-sm" style="background:#9f1239"></span>
								Urządzenia uzbrojenia
							</label>
						</section>

						<!-- 5. Linie energetyczne (wektorowe + bufor) -->
						<section>
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
								<input type="checkbox" checked={osmLinesVisible} onchange={toggleOsmLines} class="accent-orange-600" />
								<span class="inline-block h-2.5 w-2.5 rounded-sm" style="background:#c05621"></span>
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
										class="h-1 w-full cursor-pointer accent-orange-600"
									/>
									<div class="mt-1 flex gap-1">
										{#each OSM_BUFFER_PRESETS as p}
											<button
												onclick={() => onOsmBufferChange(p)}
												class="rounded border px-1.5 py-0.5 text-[10px] {osmLinesBuffer === p ? 'border-orange-500 bg-orange-50 text-orange-700' : 'border-gray-200 text-gray-500 hover:bg-gray-50'}"
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
						<section>
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
			{:else}
				<button
					onclick={() => (panelOpen = true)}
					class="pointer-events-auto flex h-9 items-center gap-1.5 rounded-lg bg-white/95 px-2.5 text-xs font-medium text-gray-700 shadow backdrop-blur-sm hover:bg-white"
					title="Pokaż warstwy"
					aria-label="Pokaż warstwy"
				>
					<svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M4 6h16M4 12h16M4 18h16"/>
					</svg>
					Warstwy
				</button>
			{/if}
		</div>
	{/if}
</div>
