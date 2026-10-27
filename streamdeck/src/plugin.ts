import streamDeck from "@elgato/streamdeck";
import { NeedsYou, PlayPause, Services, Skip, Theme, VolumeDown, VolumeUp, WindowShot, wire } from "./actions";
import { herdr, windows } from "./config";

const a = {
	needsYou: new NeedsYou(),
	theme: new Theme(),
	playPause: new PlayPause(),
	volUp: new VolumeUp(),
	volDown: new VolumeDown(),
	skip: new Skip(),
	services: new Services(),
	shot: new WindowShot(),
};
for (const action of Object.values(a)) streamDeck.actions.registerAction(action);

herdr.start();
windows.start();
wire(a);

void streamDeck.connect();
