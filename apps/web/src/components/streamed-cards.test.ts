import assert from "node:assert/strict";
import { test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { TripCard, Timeline } from "./streamed-cards";

test("trip card renders loading content before any arguments arrive", () => {
  const html = renderToStaticMarkup(createElement(TripCard, {}));
  assert.match(html, /Preparing the trip summary/);
});

test("trip card preserves the headline while other fields are streaming", () => {
  const html = renderToStaticMarkup(createElement(TripCard, { headline: "Prague weekend" }));
  assert.match(html, /Prague weekend/);
  assert.match(html, /Gathering trip details/);
});

test("trip card tolerates partial arrays and nested entries", () => {
  const html = renderToStaticMarkup(createElement(TripCard, {
    tone: "att",
    facts: [null, {}, { label: "Impact" }, { label: "Since", value: "10:00" }],
    nextSteps: [null, "Book the castle tour"],
  }));
  assert.match(html, /var\(--muted\)/);
  assert.match(html, /Impact/);
  assert.match(html, /10:00/);
  assert.match(html, /Book the castle tour/);
  assert.match(html, /Loading/);
});

test("timeline renders loading content for empty and title-only arguments", () => {
  assert.match(renderToStaticMarkup(createElement(Timeline, {})), /Preparing timeline/);
  const html = renderToStaticMarkup(createElement(Timeline, { title: "Trip history" }));
  assert.match(html, /Trip history/);
  assert.match(html, /Preparing timeline/);
  assert.match(renderToStaticMarkup(createElement(Timeline, { columns: ["Time"] })), /Loading events/);
  assert.match(renderToStaticMarkup(createElement(Timeline, { rows: [["10:00"]] })), /Preparing timeline/);
  assert.match(renderToStaticMarkup(createElement(Timeline, { columns: null, rows: null })), /Preparing timeline/);
});

test("timeline tolerates partially streamed columns, rows, and cells", () => {
  const html = renderToStaticMarkup(createElement(Timeline, {
    columns: ["Time", null],
    rows: [null, [], ["10:00"], ["10:05", null]],
  }));
  assert.match(html, /Time/);
  assert.match(html, /10:00/);
  assert.match(html, /10:05/);
  assert.match(html, /Loading/);
});

test("complete trip and timeline arguments render their content", () => {
  const card = renderToStaticMarkup(createElement(TripCard, {
    headline: "Saturday in Prague", summary: "Five stops, all within a 3 km walk",
    facts: [{ label: "Walking", value: "3 km" }], nextSteps: ["Confirm with the group"], tone: "good",
  }));
  for (const text of ["Saturday in Prague", "Five stops, all within a 3 km walk", "Walking", "3 km", "Confirm with the group", "#2e7d5b"]) {
    assert.ok(card.includes(text));
  }
  assert.doesNotMatch(card, /Loading|Preparing|Gathering/);
  const timeline = renderToStaticMarkup(createElement(Timeline, {
    title: "Saturday", columns: ["Time", "Stop"], rows: [["10:00", "Castle"], ["12:30", "Lunch"]],
  }));
  for (const text of ["Saturday", "Time", "Stop", "10:00", "Castle", "12:30", "Lunch"]) {
    assert.ok(timeline.includes(text));
  }
  assert.doesNotMatch(timeline, /Loading|Preparing/);
});
