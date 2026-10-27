// Key faces, drawn as 144x144 SVG. Colours are the pine palette from term-theme.
export const C = {
	bg: "#1B2A20",
	fg: "#EDE6D6",
	dim: "#8E9B88",
	accent: "#A6E22E",
	green: "#B5D86B",
	amber: "#D4B483",
	red: "#E07A5F",
	panel: "#243229",
	light: "#DCD6C5",
	ink: "#2B2F28",
};

const FONT = "Segoe UI, Arial, sans-serif";

function esc(s: string): string {
	return s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]!);
}

export function clip(s: string, n: number): string {
	return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

export function text(x: number, y: number, s: string, size: number, fill: string, weight = 600): string {
	return `<text x="${x}" y="${y}" font-family="${FONT}" font-size="${size}" font-weight="${weight}" fill="${fill}" text-anchor="middle">${esc(s)}</text>`;
}

export function key(body: string, bg = C.bg): string {
	const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="144" height="144" viewBox="0 0 144 144"><rect width="144" height="144" fill="${bg}"/>${body}</svg>`;
	return `data:image/svg+xml;charset=utf8,${encodeURIComponent(svg)}`;
}

export const icons = {
	play: (fill: string) => `<path d="M58 30 L98 54 L58 78 Z" fill="${fill}"/>`,
	pause: (fill: string) => `<rect x="54" y="30" width="12" height="48" rx="3" fill="${fill}"/><rect x="78" y="30" width="12" height="48" rx="3" fill="${fill}"/>`,
	next: (fill: string) => `<path d="M42 32 L72 54 L42 76 Z M72 32 L102 54 L72 76 Z" fill="${fill}"/><rect x="100" y="32" width="7" height="44" rx="2" fill="${fill}"/>`,
	speaker: (fill: string) => `<path d="M38 46 H52 L70 30 V82 L52 66 H38 Z" fill="${fill}"/>`,
	sun: (fill: string) =>
		`<circle cx="72" cy="54" r="16" fill="${fill}"/>` +
		[0, 45, 90, 135, 180, 225, 270, 315]
			.map((a) => `<rect x="70" y="20" width="4" height="12" rx="2" fill="${fill}" transform="rotate(${a} 72 54)"/>`)
			.join(""),
	moon: (fill: string, bg: string) => `<circle cx="72" cy="54" r="24" fill="${fill}"/><circle cx="84" cy="44" r="20" fill="${bg}"/>`,
	camera: (fill: string, bg: string) =>
		`<rect x="38" y="36" width="68" height="46" rx="8" fill="${fill}"/><rect x="58" y="28" width="28" height="12" rx="3" fill="${fill}"/>` +
		`<circle cx="72" cy="59" r="15" fill="${bg}"/><circle cx="72" cy="59" r="9" fill="${fill}"/>`,
	grid: (fill: string) =>
		[0, 1, 2]
			.flatMap((r) => [0, 1, 2].map((c) => `<rect x="${44 + c * 20}" y="${24 + r * 20}" width="14" height="14" rx="3" fill="${fill}"/>`))
			.join(""),
};
