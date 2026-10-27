import path from "node:path";
import { Bridge } from "./bridge";

// One machine: paths are set here rather than per key. Point HERDR_BRIDGE at
// your checkout (a WSL path, since the bridge runs inside the distro).
const DISTRO = "Ubuntu";
const HERDR_BRIDGE = "/home/YOU/code/claude-code-workstation/streamdeck/bridges/herdr-bridge.py";
export const TAILSCALE = "C:\\Program Files\\Tailscale\\tailscale.exe";
export const TERMINAL_PROCESS = "wezterm-gui";
export const MEDIA_APP = "chrome";

// Stream Deck runs the plugin with the .sdPlugin folder as the working directory.
const pluginDir = process.cwd();

export const herdr = new Bridge("herdr bridge", "wsl.exe", ["-d", DISTRO, "--", "python3", "-I", HERDR_BRIDGE]);
export const windows = new Bridge("windows bridge", "powershell.exe", [
	"-NoProfile",
	"-ExecutionPolicy",
	"Bypass",
	"-File",
	path.join(pluginDir, "bin", "windows-bridge.ps1"),
	"-App",
	MEDIA_APP,
]);
