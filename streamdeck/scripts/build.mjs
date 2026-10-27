// Bundle the plugin into the .sdPlugin folder, draw its static icons, and
// (with --install) copy it into Stream Deck's plugins folder on Windows.
import { build } from "esbuild";
import { cpSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { C, icons, key, text } from "../src/keys.ts";

const out = "dev.workstation.deck.sdPlugin";
mkdirSync(`${out}/bin`, { recursive: true });
mkdirSync(`${out}/imgs`, { recursive: true });

await build({
	entryPoints: ["src/plugin.ts"],
	bundle: true,
	platform: "node",
	target: "node24",
	format: "esm",
	outfile: `${out}/bin/plugin.js`,
	// ws (inside the SDK) is CommonJS and requires Node built-ins at runtime.
	banner: { js: 'import { createRequire } from "node:module"; const require = createRequire(import.meta.url);' },
	logLevel: "warning",
});
writeFileSync(`${out}/bin/package.json`, JSON.stringify({ type: "module" }) + "\n");
cpSync("bridges/windows-bridge.ps1", `${out}/bin/windows-bridge.ps1`);

// Faces shown in the actions list and before the plugin has state.
const svg = (dataUrl) => decodeURIComponent(dataUrl.slice(dataUrl.indexOf(",") + 1));
const faces = {
	plugin: key(icons.grid(C.accent)),
	"needs-you": key(text(72, 66, "✓", 48, C.green, 700) + text(72, 108, "claude", 20, C.dim)),
	theme: key(icons.moon(C.fg, C.bg) + text(72, 116, "theme", 22, C.dim)),
	"play-pause": key(icons.play(C.fg) + text(72, 116, "play", 20, C.dim)),
	skip: key(icons.next(C.fg) + text(72, 108, "next", 20, C.fg) + text(72, 130, "hold: prev", 15, C.dim, 400)),
	"volume-up": key(icons.speaker(C.fg) + text(110, 64, "+", 30, C.accent, 700) + text(72, 120, "vol", 24, C.dim)),
	"volume-down": key(icons.speaker(C.fg) + text(110, 64, "−", 30, C.dim, 700) + text(72, 120, "vol", 24, C.dim)),
	"window-shot": key(icons.camera(C.fg, C.bg) + text(72, 118, "window", 22, C.dim)),
	services: key(icons.grid(C.green) + text(72, 118, "services", 20, C.dim)),
};
for (const [name, face] of Object.entries(faces)) writeFileSync(`${out}/imgs/${name}.svg`, svg(face));

if (process.argv.includes("--install")) {
	const appdata = execFileSync("cmd.exe", ["/c", "echo %APPDATA%"], { encoding: "utf8" }).trim();
	const dest = execFileSync("wslpath", ["-u", `${appdata}\\Elgato\\StreamDeck\\Plugins\\${out}`], { encoding: "utf8" }).trim();
	// Stream Deck holds the plugin's files open while it runs.
	execFileSync("powershell.exe", ["-NoProfile", "-Command", "Stop-Process -Name StreamDeck -ErrorAction SilentlyContinue; Start-Sleep 2"]);
	rmSync(dest, { recursive: true, force: true });
	cpSync(out, dest, { recursive: true, filter: (p) => !p.includes("/logs") });
	execFileSync("powershell.exe", ["-NoProfile", "-Command", "Start-Process 'C:\\Program Files\\Elgato\\StreamDeck\\StreamDeck.exe'"]);
	console.log(`installed to ${dest} and restarted Stream Deck`);
}
