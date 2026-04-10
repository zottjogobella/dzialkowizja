<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import {
		Chart,
		LinearScale,
		TimeScale,
		CategoryScale,
		PointElement,
		BarElement,
		LineElement,
		ScatterController,
		BarController,
		Tooltip,
		Legend,
		Title,
		Filler
	} from 'chart.js';

	Chart.register(
		LinearScale,
		TimeScale,
		CategoryScale,
		PointElement,
		BarElement,
		LineElement,
		ScatterController,
		BarController,
		Tooltip,
		Legend,
		Title,
		Filler
	);

	interface ScatterPoint {
		x: number;
		y: number;
		label?: string;
	}

	interface Props {
		type: 'scatter' | 'histogram';
		datasets: { label: string; color: string; points: ScatterPoint[] }[];
		xLabel: string;
		yLabel: string;
		title: string;
		histogramBins?: number;
		xAsTime?: boolean;
	}

	let { type, datasets, xLabel, yLabel, title, histogramBins = 10, xAsTime = false }: Props = $props();

	let canvas: HTMLCanvasElement | undefined = $state();
	let chart: Chart | null = null;

	function buildHistogram(points: { y: number }[], bins: number) {
		if (points.length === 0) return { labels: [], counts: [] };
		const values = points.map((p) => p.y).filter((v) => Number.isFinite(v));
		if (values.length === 0) return { labels: [], counts: [] };
		const min = Math.min(...values);
		const max = Math.max(...values);
		if (max === min) {
			return { labels: [`${Math.round(min)}`], counts: [values.length] };
		}
		const step = (max - min) / bins;
		const counts = new Array(bins).fill(0);
		for (const v of values) {
			let idx = Math.floor((v - min) / step);
			if (idx >= bins) idx = bins - 1;
			counts[idx]++;
		}
		const labels = Array.from({ length: bins }, (_, i) => {
			const lo = Math.round(min + i * step);
			const hi = Math.round(min + (i + 1) * step);
			return `${lo}-${hi}`;
		});
		return { labels, counts };
	}

	function render() {
		if (!canvas) return;
		if (chart) {
			chart.destroy();
			chart = null;
		}

		if (datasets.length === 0 || datasets.every((d) => d.points.length === 0)) return;

		if (type === 'scatter') {
			chart = new Chart(canvas, {
				type: 'scatter',
				data: {
					datasets: datasets.map((d) => ({
						label: d.label,
						data: d.points,
						backgroundColor: d.color,
						borderColor: d.color,
						pointRadius: 4,
						pointHoverRadius: 6
					}))
				},
				options: {
					responsive: true,
					maintainAspectRatio: false,
					plugins: {
						title: { display: true, text: title, font: { size: 14 } },
						legend: { display: datasets.length > 1, position: 'bottom' },
						tooltip: {
							callbacks: {
								label: (ctx) => {
									const p = ctx.raw as ScatterPoint;
									const parts = [`${yLabel}: ${Math.round(p.y).toLocaleString('pl-PL')}`];
									if (p.label) parts.push(p.label);
									return parts;
								}
							}
						}
					},
					scales: {
						x: {
							title: { display: true, text: xLabel },
							ticks: {
								maxTicksLimit: 8,
								callback: xAsTime
									? (v) => {
											const d = new Date(Number(v));
											return d.toLocaleDateString('pl-PL', {
												year: 'numeric',
												month: 'short'
											});
										}
									: (v) => Number(v).toLocaleString('pl-PL')
							}
						},
						y: {
							title: { display: true, text: yLabel },
							ticks: {
								callback: (v) => Number(v).toLocaleString('pl-PL')
							}
						}
					}
				}
			});
		} else {
			// histogram (bar chart)
			const hist = buildHistogram(datasets[0].points, histogramBins);
			chart = new Chart(canvas, {
				type: 'bar',
				data: {
					labels: hist.labels,
					datasets: [
						{
							label: datasets[0].label,
							data: hist.counts,
							backgroundColor: datasets[0].color,
							borderColor: datasets[0].color
						}
					]
				},
				options: {
					responsive: true,
					maintainAspectRatio: false,
					plugins: {
						title: { display: true, text: title, font: { size: 14 } },
						legend: { display: false }
					},
					scales: {
						x: { title: { display: true, text: xLabel } },
						y: { title: { display: true, text: 'Liczba' }, beginAtZero: true }
					}
				}
			});
		}
	}

	onMount(render);

	$effect(() => {
		// rerender on data change
		datasets;
		type;
		if (canvas) render();
	});

	onDestroy(() => {
		chart?.destroy();
	});
</script>

<div class="relative h-64 w-full">
	<canvas bind:this={canvas}></canvas>
</div>
