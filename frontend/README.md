# Group City Route — frontend

React 19 + TypeScript + Vite. A full-screen map where a group forms around one
city, everyone's position stays live, and the route appears for all of them at
once.

## Run it

The backend must be running first (see `../backend`).

```bash
npm install
npm run dev
```

Open <http://localhost:5173>. Vite proxies `/api` and the `/ws` socket to
`http://127.0.0.1:8000`, so the browser sees one origin and CORS never comes up.
Point it elsewhere with `BACKEND_URL=http://otherhost:8000 npm run dev`.

For a single-process demo, build instead and let the Python server host it:

```bash
npm run build          # writes dist/
cd ../backend && uvicorn app.main:app
```

Then everything is on <http://127.0.0.1:8000>, with the UI at `/ui/`.

## Using it

1. **Start a group.** Name yourself, name the city, pick what you are into. The
   city is fixed for the whole group from then on.
2. **Others join** with the six-character code.
3. **Put yourself on the map.** Tick *Share my location* for real GPS, or click
   the map to drop your dot and drag it to move. Dragging is how you demo a
   group of three on one laptop.
4. **Build the route.** The meeting point, the stops in walking order, and every
   leg distance appear for everyone at the same moment.
5. **Leave when you are done.** *Leave this group* asks once, then drops you
   back to the setup screen so you can start your own group or join another.
   The rest of the group sees you go straight away.

Each browser tab is its own person: the session lives in `sessionStorage`, so a
refresh keeps you in the group but a new tab joins as somebody else.

## How it is put together

```
src/
  App.tsx                  state, session, geolocation
  components/
    MapView.tsx            Leaflet, markers, route line
    SetupCard.tsx          create or join
    GroupPanel.tsx         members, distances, presence
    RoutePanel.tsx         interests, stop count, itinerary
    InterestChips.tsx
  lib/
    api.ts                 typed REST client
    types.ts               mirrors the backend Pydantic models
    useGroupSocket.ts      the WebSocket, and the reducer over its events
    format.ts              distances, durations, per-member colours
```

`useGroupSocket` is the only place that touches the socket. It reconnects with
backoff, so restarting the backend heals itself without a page refresh, and it
reduces every server event into the single `Group` object the UI renders from.

`MapView` drives Leaflet imperatively inside effects rather than through a
React wrapper. Marker updates then move existing markers instead of tearing
them down, which is what keeps a dragged dot from jumping while you hold it.

## Notes

- Map tiles come from OpenStreetMap. For anything beyond a demo, use a tile
  provider you have an agreement with.
- `npm run typecheck` runs TypeScript alone; `npm run build` runs it and then
  bundles.
