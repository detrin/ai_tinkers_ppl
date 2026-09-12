# API keys for the group city-route backend

## Minimum viable set (3 keys, enough for a hackathon demo)

| Purpose | Service | Env var | Sign-up |
|---|---|---|---|
| AI picks the places | Anthropic | `ANTHROPIC_API_KEY` | console.anthropic.com |
| Distances + optimal order | OpenRouteService | `ORS_API_KEY` | openrouteservice.org/dev/#/signup |
| Group sync + live locations | Supabase | `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY` | supabase.com/dashboard |

Places discovery and geocoding then run keyless on Overpass (OpenStreetMap)
and Nominatim. Add a paid provider only when OSM data proves too thin.

## Upgrade path

| Need | Service | Env var | Note |
|---|---|---|---|
| Photos, ratings, opening hours | Google Places API (New) | `GOOGLE_MAPS_API_KEY` | Same key also unlocks Routes + Geocoding. Billing account required; a recurring monthly credit covers small usage. |
| Curated attractions, free tier | OpenTripMap | `OPENTRIPMAP_API_KEY` | Tourism-focused POIs with a rating field. |
| Matrix + tiles from one vendor | Mapbox | `MAPBOX_ACCESS_TOKEN` | Matrix, Directions, Optimization v1 and map tiles. |
| Map tiles only | MapTiler | `MAPTILER_KEY` | Cheaper than Mapbox if you only need tiles. |

## Which call does what

1. **City -> bounds.** Nominatim search, or Google Geocoding. Cache this; the
   city list is tiny and never changes.
2. **Scan the city.** Overpass query over `tourism=*`, `historic=*`,
   `amenity=cafe|restaurant`, `leisure=park` inside the bounds. Returns a few
   hundred candidates with coordinates.
3. **AI ranking.** Send the candidate list plus the group's stated interests to
   Claude. Ask for a scored shortlist with a one-line reason per place. Keep the
   model out of coordinate math; it only chooses and explains.
4. **Distance matrix.** ORS `/v2/matrix/foot-walking` over the shortlist plus
   every member's current position. This produces every pairwise distance and
   duration the UI needs.
5. **Route order.** ORS `/optimization` (VROOM) with one vehicle per group, or
   a plain nearest-neighbour pass if the shortlist is under ~10 stops.
6. **Live positions.** Clients write to a `member_positions` table and subscribe
   to a Supabase Realtime channel keyed by group id. Use Presence for
   online/offline; use the table for the last known coordinate.

## Key hygiene

- `SUPABASE_SERVICE_ROLE_KEY` bypasses row-level security. Server only. Never
  in a mobile bundle or a Vite `VITE_` variable.
- Restrict `GOOGLE_MAPS_API_KEY` by API and by HTTP referrer or IP in the Google
  Cloud console the moment you create it. Unrestricted Maps keys get scraped
  from repos and billed within hours.
- Proxy every third-party call through your own backend so the phone app ships
  zero provider keys.
- Commit `.env.example` only. Add `.env` to `.gitignore` before the first commit.

---

The working `.env` template sits next to this file as `.env.example`, alongside the
implementation. This file stays as the reference on where each key comes from.
