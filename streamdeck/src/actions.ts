import streamDeck, { action, SingletonAction, type KeyDownEvent, type WillAppearEvent } from "@elgato/streamdeck";
import { herdr, TERMINAL_PROCESS, windows } from "./config";
import { C, clip, icons, key, text } from "./keys";
import { checkServices, openServicesPage, type Service } from "./services";

/** An action whose face is drawn from shared state; repaint() updates every key showing it. */
abstract class Painted extends SingletonAction {
	abstract face(): string;

	repaint(): void {
		const img = this.face();
		for (const a of this.actions) if (a.isKey()) void a.setImage(img);
	}

	override onWillAppear(ev: WillAppearEvent): void {
		if (ev.action.isKey()) void ev.action.setImage(this.face());
	}
}

// ---------- Herdr ----------

type HerdrState = {
	blocked: { pane: string; title: string }[];
	done: { pane: string; title: string }[];
	idle: { pane: string; title: string }[];
	working: number;
	theme: string;
	error: string | null;
};
let hs: HerdrState | undefined;
let herdrError: string | null = "starting";

@action({ UUID: "dev.workstation.deck.needs-you" })
export class NeedsYou extends Painted {
	private blink = false;
	private busyUntil = 0;

	constructor() {
		super();
		// Flash while something is blocked on you; a still key is easy to stop seeing.
		setInterval(() => {
			if (hs?.blocked.length) {
				this.blink = !this.blink;
				this.repaint();
			}
		}, 600);
	}

	face(): string {
		if (herdrError || !hs) return key(text(72, 64, "herdr", 26, C.dim) + text(72, 98, clip(herdrError ?? "…", 14), 16, C.red, 400));
		const waiting = hs.blocked.length;
		const done = hs.done.length;
		if (waiting) {
			const bg = this.blink ? C.red : C.bg;
			const fg = this.blink ? C.bg : C.red;
			return key(text(72, 70, String(waiting), 56, fg, 700) + text(72, 98, "waiting", 20, fg) + text(72, 126, clip(hs.blocked[0].title, 15), 15, this.blink ? C.bg : C.fg, 400), bg);
		}
		if (done) {
			return key(text(72, 70, String(done), 56, C.amber, 700) + text(72, 98, "done", 20, C.amber) + text(72, 126, clip(hs.done[0].title, 15), 15, C.fg, 400));
		}
		if (Date.now() < this.busyUntil) return key(text(72, 66, "✓", 48, C.green, 700) + text(72, 108, "all busy", 20, C.fg));
		const idle = hs.idle.length;
		return key(
			text(72, 62, "✓", 44, C.green, 700) +
				text(72, 100, `${hs.working} working`, 18, C.dim, 400) +
				(idle ? text(72, 124, `${idle} ready`, 18, C.fg, 400) : ""),
		);
	}

	override onKeyDown(ev: KeyDownEvent): void {
		if (!hs) {
			void ev.action.showAlert();
			return;
		}
		if (!hs.blocked.length && !hs.done.length && !hs.idle.length) {
			// Everything is working: say so on the key instead of the alert triangle.
			this.busyUntil = Date.now() + 1500;
			this.repaint();
			setTimeout(() => this.repaint(), 1600);
			return;
		}
		herdr.send("focus");
		windows.send(`raise ${TERMINAL_PROCESS}`);
	}
}

@action({ UUID: "dev.workstation.deck.theme" })
export class Theme extends Painted {
	face(): string {
		const mode = hs?.theme ?? "unknown";
		if (mode === "light") return key(icons.sun(C.amber) + text(72, 116, "light", 22, C.ink), C.light);
		if (mode === "dark") return key(icons.moon(C.fg, C.bg) + text(72, 116, "dark", 22, C.dim));
		return key(text(72, 80, "theme ?", 22, C.dim));
	}

	override onKeyDown(ev: KeyDownEvent): void {
		herdr.send("theme");
		void ev.action.showOk();
	}
}

// ---------- Music ----------

type MediaState = { status: string; title: string | null; artist: string | null; volume: number; muted: boolean };
let ms: MediaState | undefined;

@action({ UUID: "dev.workstation.deck.play-pause" })
export class PlayPause extends Painted {
	face(): string {
		if (!ms || ms.status === "none") return key(icons.play(C.dim) + text(72, 112, "no music", 18, C.dim, 400));
		const playing = ms.status === "playing";
		const icon = playing ? icons.pause(C.accent) : icons.play(C.fg);
		return key(icon + text(72, 106, clip(ms.title ?? "", 15), 17, C.fg) + text(72, 128, clip(ms.artist?.replace(/ - Topic$/, "") ?? "", 17), 14, C.dim, 400));
	}

	override onKeyDown(ev: KeyDownEvent): void {
		if (!ms || ms.status === "none") void ev.action.showAlert();
		else windows.send("toggle");
	}
}

/** Tap for the next track, hold for the previous one. */
@action({ UUID: "dev.workstation.deck.skip" })
export class Skip extends Painted {
	private hold?: NodeJS.Timeout;
	private held = false;

	face(): string {
		const none = !ms || ms.status === "none";
		return key(icons.next(none ? C.dim : C.fg) + text(72, 108, "next", 20, none ? C.dim : C.fg) + text(72, 130, "hold: prev", 15, C.dim, 400));
	}

	override onKeyDown(ev: KeyDownEvent): void {
		this.held = false;
		clearTimeout(this.hold);
		// Previous fires while the key is still down, so a hold doesn't feel dead.
		this.hold = setTimeout(() => {
			this.held = true;
			windows.send("prev");
			void ev.action.showOk();
		}, 500);
	}

	override onKeyUp(): void {
		clearTimeout(this.hold);
		if (!this.held) windows.send("next");
	}
}

/** Volume keys: one press is a step, holding keeps stepping. */
abstract class Volume extends Painted {
	abstract step: number;
	private repeat?: NodeJS.Timeout;

	face(): string {
		const up = this.step > 0;
		const vol = ms && ms.volume >= 0 ? `${ms.volume}%` : "—";
		const waves = up
			? `<path d="M80 40 Q92 56 80 72 M88 32 Q106 56 88 80" stroke="${C.accent}" stroke-width="5" fill="none" stroke-linecap="round"/>`
			: `<path d="M80 40 Q92 56 80 72" stroke="${C.dim}" stroke-width="5" fill="none" stroke-linecap="round"/>`;
		const sign = text(110, 64, up ? "+" : "−", 30, up ? C.accent : C.dim, 700);
		return key(icons.speaker(C.fg) + waves + (up ? "" : sign) + text(72, 120, vol, 26, ms?.muted ? C.red : C.fg));
	}

	override onKeyDown(): void {
		windows.send(`vol ${this.step}`);
		clearInterval(this.repeat);
		const started = Date.now();
		this.repeat = setInterval(() => {
			if (Date.now() - started > 400) windows.send(`vol ${this.step}`);
		}, 150);
	}

	override onKeyUp(): void {
		clearInterval(this.repeat);
	}
}

@action({ UUID: "dev.workstation.deck.volume-up" })
export class VolumeUp extends Volume {
	step = 5;
}

@action({ UUID: "dev.workstation.deck.volume-down" })
export class VolumeDown extends Volume {
	step = -5;
}

// ---------- Screenshot ----------

/** Shoots whatever window is in front: pressing a key doesn't take focus from it. */
@action({ UUID: "dev.workstation.deck.window-shot" })
export class WindowShot extends Painted {
	private pending: KeyDownEvent["action"][] = [];

	face(): string {
		return key(icons.camera(C.fg, C.bg) + text(72, 118, "window", 22, C.dim));
	}

	override onKeyDown(ev: KeyDownEvent): void {
		this.pending.push(ev.action);
		windows.send("shot");
	}

	done(ok: boolean): void {
		for (const a of this.pending.splice(0)) void (ok ? a.showOk() : a.showAlert());
	}
}

// ---------- Services ----------

let services: Service[] | undefined;

@action({ UUID: "dev.workstation.deck.services" })
export class Services extends Painted {
	private busy = false;

	face(): string {
		if (this.busy) return key(icons.grid(C.dim) + text(72, 118, "checking", 18, C.dim, 400));
		if (!services) return key(icons.grid(C.dim) + text(72, 118, "services", 20, C.dim));
		const up = services.filter((s) => s.ok).length;
		const allUp = up === services.length;
		return key(icons.grid(allUp ? C.green : C.amber) + text(72, 120, `${up}/${services.length} up`, 22, allUp ? C.fg : C.amber));
	}

	async refresh(): Promise<void> {
		try {
			services = await checkServices();
		} catch (e) {
			streamDeck.logger.error(`services: ${(e as Error).message}`);
		}
		this.repaint();
	}

	override async onKeyDown(ev: KeyDownEvent): Promise<void> {
		this.busy = true;
		this.repaint();
		try {
			services = await checkServices();
			await openServicesPage(services);
		} catch (e) {
			streamDeck.logger.error(`services: ${(e as Error).message}`);
			void ev.action.showAlert();
		} finally {
			this.busy = false;
			this.repaint();
		}
	}
}

// ---------- wiring ----------

export function wire(a: { needsYou: NeedsYou; theme: Theme; playPause: PlayPause; volUp: VolumeUp; volDown: VolumeDown; skip: Skip; services: Services; shot: WindowShot }): void {
	herdr.subscribe((msg) => {
		if ("theme" in msg) {
			hs = msg as HerdrState;
			herdrError = hs.error;
		} else if (msg.down) {
			herdrError = "restarting";
		} else if (msg.error) {
			streamDeck.logger.warn(`herdr bridge: ${msg.error}`);
		}
		a.needsYou.repaint();
		a.theme.repaint();
	});
	windows.subscribe((msg) => {
		if ("shot" in msg) {
			if (!msg.shot) streamDeck.logger.error(`window shot: ${msg.error}`);
			a.shot.done(Boolean(msg.shot));
			return;
		}
		if ("status" in msg) ms = msg as MediaState;
		else if (msg.down) {
			ms = undefined;
			a.shot.done(false);
		}
		a.playPause.repaint();
		a.volUp.repaint();
		a.volDown.repaint();
		a.skip.repaint();
	});
	void a.services.refresh();
	setInterval(() => void a.services.refresh(), 2 * 60 * 1000);
}
