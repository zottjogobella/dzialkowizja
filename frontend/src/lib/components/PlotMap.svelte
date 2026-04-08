<script lang="ts">
	import { browser } from '$app/environment';
	import 'maplibre-gl/dist/maplibre-gl.css';

	interface Props {
		geometry: Record<string, unknown> | null;
		buildings: GeoJSON.FeatureCollection | null;
		loading: boolean;
	}

	let { geometry, buildings, loading }: Props = $props();

	let mapContainer = $state<HTMLDivElement>(undefined!);
	let map: import('maplibre-gl').Map | undefined;
	let orthoOpacity = $state(50);
	let mapReady = $state(false);

	const LAYERS = [
		{ source: 'egib', label: 'EGiB', color: '#e8d5b7' },
		{ source: 'bdot', label: 'BDOT', color: '#c8bda8' },
		{ source: 'osm',  label: 'OSM',  color: '#b8c4b0' },
	] as const;

	let layerVisible = $state<Record<string, boolean>>({ egib: false, bdot: false, osm: false });
	let gesutVisible = $state(false);

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
			const filter = ['==', ['get', 'source'], layer.source];

			const vis = layerVisible[layer.source] ? 'visible' : 'none';

			m.addLayer({
				id: `buildings-${layer.source}-3d`,
				type: 'fill-extrusion',
				source: 'buildings',
				filter,
				layout: { visibility: vis },
				paint: {
					'fill-extrusion-color': layer.color,
					'fill-extrusion-height': ['get', 'height'],
					'fill-extrusion-base': 0,
					'fill-extrusion-opacity': 0.85
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

	function countBySource(src: string): number {
		if (!buildings) return 0;
		return buildings.features.filter(f => f.properties?.source === src).length;
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
					sources: {
						carto: {
							type: 'raster',
							tiles: ['https://basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}@2x.png'],
							tileSize: 256,
							attribution: '&copy; <a href="https://carto.com/">CARTO</a>'
						},
						ortho: {
							type: 'raster',
							tiles: [
								'https://mapy.geoportal.gov.pl/wss/service/PZGIK/ORTO/WMS/StandardResolution?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetMap&LAYERS=Raster&STYLES=&SRS=EPSG:3857&BBOX={bbox-epsg-3857}&WIDTH=256&HEIGHT=256&FORMAT=image/jpeg'
							],
							tileSize: 256,
							attribution: '&copy; <a href="https://geoportal.gov.pl/">Geoportal</a>'
						},
						gesut: {
							type: 'raster',
							tiles: [
								'/api/gesut/tile?bbox={bbox-epsg-3857}&width=512&height=512'
							],
							tileSize: 512,
							minzoom: 17,
							maxzoom: 20,
							attribution: '&copy; <a href="https://integracja.gugik.gov.pl/">GUGiK GESUT</a>'
						}
					},
					layers: [
						{ id: 'carto-layer', type: 'raster', source: 'carto' },
						{ id: 'ortho-layer', type: 'raster', source: 'ortho', paint: { 'raster-opacity': 0.5 } },
						{ id: 'gesut-layer', type: 'raster', source: 'gesut', layout: { visibility: 'none' }, paint: { 'raster-opacity': 0.9 } }
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

				if (buildings && buildings.features.length > 0) {
					addBuildingsLayers(map, buildings);
				}

				if (bbox) {
					map.fitBounds(bbox as [number, number, number, number], {
						padding: 80,
						maxZoom: 18,
						duration: 0
					});
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

	function handleSlider(e: Event) {
		const value = parseInt((e.target as HTMLInputElement).value);
		orthoOpacity = value;
		if (map && mapReady && map.getLayer('ortho-layer')) {
			map.setPaintProperty('ortho-layer', 'raster-opacity', value / 100);
		}
	}

	function toggleLayer(src: string) {
		layerVisible[src] = !layerVisible[src];
		if (!map || !mapReady) return;
		const vis = layerVisible[src] ? 'visible' : 'none';
		if (map.getLayer(`buildings-${src}-3d`)) {
			map.setLayoutProperty(`buildings-${src}-3d`, 'visibility', vis);
			map.setLayoutProperty(`buildings-${src}-outline`, 'visibility', vis);
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

		<!-- Bottom-left: base map + building layers -->
		<div class="absolute bottom-3 left-3 flex flex-col gap-2">
			<div class="rounded-lg bg-white/90 px-3 py-2 shadow backdrop-blur-sm">
				<label class="flex items-center gap-2 text-xs text-gray-600">
					<span>Mapa</span>
					<input
						type="range" min="0" max="100"
						value={orthoOpacity}
						oninput={handleSlider}
						class="h-1.5 w-28 cursor-pointer accent-blue-600"
					/>
					<span>Orto</span>
				</label>
			</div>

			<div class="flex flex-wrap gap-1">
				<button
					onclick={toggleGesut}
					class="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium shadow backdrop-blur-sm transition-colors
						{gesutVisible ? 'bg-white/90 text-gray-800' : 'bg-white/50 text-gray-400'}"
				>
					<span
						class="inline-block h-2.5 w-2.5 rounded-sm"
						style="background:#e53e3e; opacity:{gesutVisible ? 1 : 0.3}"
					></span>
					Linie elektryczne
				</button>
				{#if buildings && buildings.features.length > 0}
					{#each LAYERS as layer}
						{@const count = countBySource(layer.source)}
						{#if count > 0}
							<button
								onclick={() => toggleLayer(layer.source)}
								class="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium shadow backdrop-blur-sm transition-colors
									{layerVisible[layer.source] ? 'bg-white/90 text-gray-800' : 'bg-white/50 text-gray-400'}"
							>
								<span
									class="inline-block h-2.5 w-2.5 rounded-sm"
									style="background:{layer.color}; opacity:{layerVisible[layer.source] ? 1 : 0.3}"
								></span>
								{layer.label}
								<span class="text-[10px] text-gray-400">{count}</span>
							</button>
						{/if}
					{/each}
				{/if}
			</div>
		</div>

		<!-- Top-left: plot style panel -->
		<div class="absolute top-3 left-3">
			<button
				onclick={() => showStylePanel = !showStylePanel}
				class="rounded-lg bg-white/90 px-2.5 py-1.5 text-xs font-medium text-gray-700 shadow backdrop-blur-sm transition-colors hover:bg-white"
				title="Styl działki"
			>
				<span class="inline-block h-3 w-3 rounded-sm border border-gray-300" style="background:{plotFill}; opacity:{plotFillOpacity / 100}"></span>
				Styl działki
			</button>

			{#if showStylePanel}
				<div class="mt-1.5 w-56 rounded-xl bg-white/95 p-4 shadow-lg backdrop-blur-sm">
					<div class="mb-3 flex items-center justify-between">
						<span class="text-xs font-semibold text-gray-700">Styl działki</span>
						<button onclick={() => showStylePanel = false} class="text-gray-400 hover:text-gray-600">&times;</button>
					</div>

					<!-- Fill -->
					<div class="mb-3">
						<label class="mb-1 flex items-center justify-between text-[11px] text-gray-500">
							<span>Wypełnienie</span>
							<span>{plotFillOpacity}%</span>
						</label>
						<div class="flex items-center gap-2">
							<input
								type="color" bind:value={plotFill}
								oninput={applyPlotStyle}
								class="h-6 w-6 cursor-pointer rounded border-0 p-0"
							/>
							<input
								type="range" min="0" max="100" bind:value={plotFillOpacity}
								oninput={applyPlotStyle}
								class="h-1 w-full cursor-pointer accent-blue-600"
							/>
						</div>
					</div>

					<!-- Stroke -->
					<div class="mb-3">
						<label class="mb-1 flex items-center justify-between text-[11px] text-gray-500">
							<span>Obrys</span>
							<span>{plotStrokeWidth}px / {plotStrokeOpacity}%</span>
						</label>
						<div class="flex items-center gap-2">
							<input
								type="color" bind:value={plotStroke}
								oninput={applyPlotStyle}
								class="h-6 w-6 cursor-pointer rounded border-0 p-0"
							/>
							<input
								type="range" min="0" max="100" bind:value={plotStrokeOpacity}
								oninput={applyPlotStyle}
								class="h-1 w-full cursor-pointer accent-blue-600"
							/>
						</div>
						<div class="mt-1.5">
							<label class="flex items-center gap-2 text-[11px] text-gray-500">
								<span>Grubość</span>
								<input
									type="range" min="0" max="10" step="0.5" bind:value={plotStrokeWidth}
									oninput={applyPlotStyle}
									class="h-1 w-full cursor-pointer accent-blue-600"
								/>
							</label>
						</div>
					</div>
				</div>
			{/if}
		</div>
	{/if}
</div>
