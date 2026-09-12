import assert from "node:assert/strict";
import { afterEach, describe, it, mock } from "node:test";
import { askTravelAgent, createTravelGroup, lookupTravelGroup } from "./trip-tools";

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
  delete process.env.TRIP_API_URL;
});

describe("shared trip backend tools", () => {
  it("creates a group and returns the backend join code", async () => {
    const group = {
      id: "group-1",
      name: "Prague crew",
      join_code: "ABC234",
      city: { name: "Prague" },
    };
    globalThis.fetch = mock.fn(async (url, init) => {
      assert.equal(url, "http://127.0.0.1:8000/api/groups");
      assert.equal(init?.method, "POST");
      assert.deepEqual(JSON.parse(String(init?.body)), {
        name: "Prague crew",
        city: "Prague",
        interests: ["history", "food"],
        transport: "foot",
      });
      return Response.json(group, { status: 201 });
    }) as typeof fetch;

    const result = await createTravelGroup.handler(
      {
        name: "Prague crew",
        city: "Prague",
        interests: ["history", "food"],
        transport: "foot",
      },
      {} as never,
    );
    assert.deepEqual(result, group);
  });

  it("looks up the same group by a normalized join code", async () => {
    globalThis.fetch = mock.fn(async (url) => {
      assert.equal(url, "http://127.0.0.1:8000/api/groups/by-code/ABC234");
      return Response.json({ id: "group-1", join_code: "ABC234" });
    }) as typeof fetch;

    const result = await lookupTravelGroup.handler(
      { joinCode: "abc234" },
      {} as never,
    );
    assert.deepEqual(result, { id: "group-1", join_code: "ABC234" });
  });

  it("asks the trip agent and returns its answer", async () => {
    globalThis.fetch = mock.fn(async (url, init) => {
      assert.equal(url, "http://127.0.0.1:8000/api/groups/group-1/ask");
      assert.equal(init?.method, "POST");
      assert.deepEqual(JSON.parse(String(init?.body)), {
        question: "Any rainy-day backup?",
      });
      return Response.json({
        question: "Any rainy-day backup?",
        answer: "Try the National Gallery.",
      });
    }) as typeof fetch;

    const result = await askTravelAgent.handler(
      { groupId: "group-1", question: "Any rainy-day backup?" },
      {} as never,
    );
    assert.deepEqual(result, {
      question: "Any rainy-day backup?",
      answer: "Try the National Gallery.",
    });
  });

  it("returns a controlled error when the backend is unavailable", async () => {
    globalThis.fetch = mock.fn(async () => {
      throw new Error("connection refused with secret details");
    }) as typeof fetch;

    await assert.rejects(
      async () =>
        await lookupTravelGroup.handler(
          { joinCode: "ABC234" },
          {} as never,
        ),
      /trip backend is unavailable/i,
    );
  });
});
