import { execFile, spawn } from "node:child_process";
import { writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import { TAILSCALE } from "./config";

export type Service = { url: string; backend: string; name: string; ok: boolean; status: number | null; ms: number | null };

/**
 * Every service is published through `tailscale serve`, so its config is the
 * list of services: a new one shows up here without touching this plugin.
 */
async function listServices(): Promise<{ url: string; backend: string }[]> {
	const { stdout } = await promisify(execFile)(TAILSCALE, ["serve", "status", "--json"], { windowsHide: true, timeout: 10000 });
	const web: Record<string, { Handlers?: Record<string, { Proxy?: string }> }> = JSON.parse(stdout).Web ?? {};
	return Object.entries(web).flatMap(([hostPort, v]) =>
		Object.entries(v.Handlers ?? {}).map(([p, h]) => ({
			url: `https://${hostPort.replace(/:443$/, "")}${p}`,
			backend: h.Proxy ?? "",
		})),
	);
}

async function probe(url: string): Promise<{ status: number | null; ms: number | null; title: string | null }> {
	const t = Date.now();
	try {
		const r = await fetch(url, { signal: AbortSignal.timeout(5000), redirect: "follow" });
		const body = (await r.text()).slice(0, 20000);
		const title = /<title[^>]*>([^<]*)<\/title>/i.exec(body)?.[1]?.trim() || null;
		return { status: r.status, ms: Date.now() - t, title };
	} catch {
		return { status: null, ms: null, title: null };
	}
}

export async function checkServices(): Promise<Service[]> {
	const list = await listServices();
	return Promise.all(
		list.map(async ({ url, backend }) => {
			const p = await probe(url);
			const port = new URL(url).port || "443";
			return { url, backend, name: p.title ?? `:${port}`, ok: p.status !== null && p.status < 500, status: p.status, ms: p.ms };
		}),
	);
}

function esc(s: string): string {
	return s.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
}

function page(services: Service[]): string {
	const when = new Date().toLocaleString();
	const cards = services
		.map((s) => {
			const state = s.ok ? "up" : "down";
			const detail = s.status === null ? "no response" : `${s.status} · ${s.ms} ms`;
			return `<a class="card ${state}" href="${esc(s.url)}">
  <span class="dot"></span>
  <span class="name">${esc(s.name)}</span>
  <span class="url">${esc(s.url.replace(/^https:\/\//, ""))}</span>
  <span class="meta">${esc(detail)} · ${esc(s.backend.replace(/^http:\/\//, ""))}</span>
</a>`;
		})
		.join("\n");
	const up = services.filter((s) => s.ok).length;
	return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Services</title>
<style>
:root { --bg:#DCD6C5; --panel:#E8E3D6; --fg:#2B2F28; --dim:#5F665A; --line:#C3CFB0; --up:#4F7D2A; --down:#B5452F; }
@media (prefers-color-scheme: dark) { :root { --bg:#1B2A20; --panel:#243229; --fg:#EDE6D6; --dim:#8E9B88; --line:#34493A; --up:#B5D86B; --down:#E07A5F; } }
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--fg); font: 15px/1.4 "Segoe UI", system-ui, sans-serif; padding: 32px 16px; }
main { max-width: 880px; margin: 0 auto; }
h1 { font-size: 22px; margin: 0 0 4px; }
p.sub { color: var(--dim); margin: 0 0 24px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; }
.card { display: grid; grid-template-columns: 14px 1fr; column-gap: 10px; row-gap: 2px; padding: 14px 16px;
  background: var(--panel); border: 1px solid var(--line); border-radius: 10px; color: inherit; text-decoration: none; }
.card:hover, .card:focus-visible { border-color: var(--up); outline: none; }
.card.down { border-color: var(--down); }
.dot { width: 10px; height: 10px; border-radius: 50%; background: var(--up); margin-top: 6px; grid-row: 1; }
.down .dot { background: var(--down); }
.name { font-weight: 600; font-size: 16px; }
.url, .meta { grid-column: 2; color: var(--dim); font-size: 13px; overflow-wrap: anywhere; }
.meta { font-variant-numeric: tabular-nums; }
</style></head>
<body><main>
<h1>Services</h1>
<p class="sub">${up} of ${services.length} up · checked ${esc(when)}</p>
<div class="grid">
${cards}
</div>
</main></body></html>`;
}

export async function openServicesPage(services: Service[]): Promise<void> {
	const file = path.join(os.tmpdir(), "streamdeck-services.html");
	await writeFile(file, page(services), "utf8");
	// explorer hands the file to the default browser.
	spawn("explorer.exe", [file], { detached: true, stdio: "ignore", windowsHide: true }).unref();
}
