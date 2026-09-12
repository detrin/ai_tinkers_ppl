const PALETTE = [
  "#1f6feb",
  "#d9480f",
  "#0b7285",
  "#862e9c",
  "#2b8a3e",
  "#c2255c",
  "#5f3dc4",
  "#e67700",
];

/** Stable per-member colour, so a dot on the map matches its row in the list. */
export function colorFor(id: string): string {
  let hash = 0;
  for (const character of id) hash = (hash * 31 + character.charCodeAt(0)) >>> 0;
  return PALETTE[hash % PALETTE.length];
}

export function initials(name: string): string {
  const letters = name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((word) => word[0] ?? "")
    .join("");
  return letters.toUpperCase() || "?";
}

export function metres(value: number | null | undefined): string {
  if (value == null) return "—";
  return value < 950 ? `${Math.round(value)} m` : `${(value / 1000).toFixed(1)} km`;
}

export function duration(seconds: number): string {
  const total = Math.round(seconds / 60);
  if (total < 60) return `${total} min`;
  return `${Math.floor(total / 60)} h ${String(total % 60).padStart(2, "0")}`;
}

export const INTERESTS = [
  "history",
  "art",
  "museums",
  "food",
  "parks",
  "views",
  "architecture",
  "nightlife",
] as const;
