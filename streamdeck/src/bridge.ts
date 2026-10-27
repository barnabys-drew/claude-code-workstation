import { spawn, type ChildProcess } from "node:child_process";
import { createInterface } from "node:readline";
import streamDeck from "@elgato/streamdeck";

type Listener = (msg: Record<string, unknown>) => void;

/**
 * A long-lived helper process that speaks JSON lines: commands go in on
 * stdin, state comes back on stdout. Restarts with backoff if it dies, so a
 * Herdr restart or a WSL hiccup only blanks the keys for a moment.
 */
export class Bridge {
	private child?: ChildProcess;
	private listeners: Listener[] = [];
	private backoff = 1000;
	last?: Record<string, unknown>;

	constructor(
		private name: string,
		private command: string,
		private args: string[],
	) {}

	start(): void {
		const child = spawn(this.command, this.args, { stdio: ["pipe", "pipe", "pipe"], windowsHide: true });
		this.child = child;
		createInterface({ input: child.stdout! }).on("line", (line) => {
			let msg: Record<string, unknown>;
			try {
				msg = JSON.parse(line);
			} catch {
				return;
			}
			this.backoff = 1000;
			this.last = msg;
			for (const l of this.listeners) l(msg);
		});
		createInterface({ input: child.stderr! }).on("line", (line) => streamDeck.logger.warn(`${this.name}: ${line}`));
		child.on("exit", (code) => {
			streamDeck.logger.warn(`${this.name} exited (${code}); restarting in ${this.backoff}ms`);
			this.child = undefined;
			for (const l of this.listeners) l({ down: true });
			setTimeout(() => this.start(), this.backoff);
			this.backoff = Math.min(this.backoff * 2, 30000);
		});
		child.on("error", (err) => streamDeck.logger.error(`${this.name}: ${err.message}`));
	}

	send(cmd: string): void {
		this.child?.stdin?.write(cmd + "\n");
	}

	/** Calls fn with every message, and once straight away with the last one. */
	subscribe(fn: Listener): void {
		this.listeners.push(fn);
		if (this.last) fn(this.last);
	}
}
