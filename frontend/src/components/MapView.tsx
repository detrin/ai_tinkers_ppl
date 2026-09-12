import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { City, Member, Plan } from "../lib/types";
import { colorFor, duration, initials, metres } from "../lib/format";

interface Props {
  city: City | null;
  members: Member[];
  meId: string | null;
  plan: Plan | null;
  /** Fires when you drag your own dot, or click an empty map with no position yet. */
  onSelfMove: (lat: number, lon: number) => void;
  /** Index of the stop to open, bumped by the panel to focus one. */
  focusedStop: { index: number; nonce: number } | null;
  /** An arbitrary point to pan to, used when a member row is clicked. */
  focusPoint: { lat: number; lon: number; nonce: number } | null;
}

const escapeHtml = (text: string) =>
  text.replace(
    /[&<>"']/g,
    (character) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        character
      ] as string,
  );

const divIcon = (className: string, html: string, size: number, style = "") =>
  L.divIcon({
    className: "",
    html: `<div class="${className}" style="${style}">${html}</div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });

export function MapView({
  city,
  members,
  meId,
  plan,
  onSelfMove,
  focusedStop,
  focusPoint,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const memberMarkers = useRef(new Map<string, L.Marker>());
  const routeLayer = useRef<L.LayerGroup | null>(null);
  const stopMarkers = useRef<L.Marker[]>([]);
  const moveRef = useRef(onSelfMove);
  moveRef.current = onSelfMove;

  // --- Create the map once ------------------------------------------------
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = L.map(containerRef.current, { zoomControl: false }).setView(
      [50.0875, 14.4213],
      13,
    );
    L.control.zoom({ position: "bottomright" }).addTo(map);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(map);

    // With no GPS fix, clicking the map drops you somewhere to start from.
    map.on("click", (event: L.LeafletMouseEvent) => {
      moveRef.current(event.latlng.lat, event.latlng.lng);
    });

    routeLayer.current = L.layerGroup().addTo(map);
    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
      memberMarkers.current.clear();
      stopMarkers.current = [];
    };
  }, []);

  // --- Centre on the city the group chose ---------------------------------
  useEffect(() => {
    if (city && mapRef.current) mapRef.current.setView([city.lat, city.lon], 14);
  }, [city?.lat, city?.lon]);

  // --- Member dots --------------------------------------------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const alive = new Set<string>();

    for (const member of members) {
      if (!member.position) continue;
      alive.add(member.id);

      const isMe = member.id === meId;
      const latlng: L.LatLngTuple = [member.position.lat, member.position.lon];
      let marker = memberMarkers.current.get(member.id);

      if (!marker) {
        marker = L.marker(latlng, {
          icon: divIcon(
            `member-marker${isMe ? " draggable" : ""}`,
            escapeHtml(initials(member.display_name)),
            28,
            `background:${colorFor(member.id)}`,
          ),
          draggable: isMe,
          zIndexOffset: isMe ? 1000 : 500,
        }).addTo(map);

        // Dragging your own dot is how you demo movement without real GPS.
        if (isMe) {
          marker.on("dragend", (event) => {
            const { lat, lng } = (event.target as L.Marker).getLatLng();
            moveRef.current(lat, lng);
          });
        }
        memberMarkers.current.set(member.id, marker);
      } else {
        marker.setLatLng(latlng);
      }

      marker.bindTooltip(
        `${escapeHtml(member.display_name)}${isMe ? " (you)" : ""}`,
        { direction: "top", offset: [0, -16] },
      );
    }

    for (const [id, marker] of memberMarkers.current) {
      if (!alive.has(id)) {
        marker.remove();
        memberMarkers.current.delete(id);
      }
    }
  }, [members, meId]);

  // --- Route, meeting point and stops -------------------------------------
  useEffect(() => {
    const map = mapRef.current;
    const layer = routeLayer.current;
    if (!map || !layer) return;

    layer.clearLayers();
    stopMarkers.current = [];
    if (!plan) return;

    const path: L.LatLngTuple[] = [[plan.meeting_point.lat, plan.meeting_point.lon]];

    L.marker(path[0], {
      icon: divIcon("meet-marker", "&#9873;", 30),
      zIndexOffset: 800,
    })
      .bindTooltip("Meet here", { direction: "top", offset: [0, -17] })
      .addTo(layer);

    plan.stops.forEach((stop, index) => {
      path.push([stop.place.lat, stop.place.lon]);
      const marker = L.marker([stop.place.lat, stop.place.lon], {
        icon: divIcon("stop-marker", String(index + 1), 28),
        zIndexOffset: 600,
      })
        .bindPopup(
          `<strong>${escapeHtml(stop.place.name)}</strong><br>` +
            `<span class="popup-why">${escapeHtml(
              stop.place.reason || stop.place.category,
            )}</span><br>` +
            `${metres(stop.distance_from_previous_m)} · ` +
            `${duration(stop.travel_seconds_from_previous)} walk · ` +
            `${stop.place.suggested_minutes} min there`,
        )
        .addTo(layer);
      stopMarkers.current.push(marker);
    });

    L.polyline(path, {
      color: "#1f6feb",
      weight: 4,
      opacity: 0.75,
      dashArray: "1 9",
      lineCap: "round",
    }).addTo(layer);

    map.fitBounds(L.latLngBounds(path).pad(0.22));
  }, [plan]);

  // --- Camera moves asked for by the panel ---------------------------------
  useEffect(() => {
    if (!focusedStop || !mapRef.current) return;
    const marker = stopMarkers.current[focusedStop.index];
    if (!marker) return;
    mapRef.current.setView(marker.getLatLng(), 17);
    marker.openPopup();
  }, [focusedStop?.nonce]);

  useEffect(() => {
    if (!focusPoint || !mapRef.current) return;
    mapRef.current.panTo([focusPoint.lat, focusPoint.lon]);
  }, [focusPoint?.nonce]);

  return <div ref={containerRef} className="map" />;
}
