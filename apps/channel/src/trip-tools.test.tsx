import assert from "node:assert/strict";
import { afterEach, describe, it, mock } from "node:test";
import { askTravelAgent, createTravelGroup, lookupTravelGroup, prepareLocalGuideSearch, proposeExpense, proposeItinerary } from "./trip-tools";

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

  it("proposes an exact expense through the approval-backed API", async () => {
    const receipt = { id: "expense-1", status: "proposed", title: "Dinner", amount: 60, currency: "EUR", paid_by: "member-1", shares: { "member-1": 30, "member-2": 30 } };
    globalThis.fetch = mock.fn(async (url, init) => {
      if (!init?.method) return Response.json({ members: [{ id: "member-1", display_name: "Anna" }, { id: "member-2", display_name: "David" }] });
      assert.equal(url, "http://127.0.0.1:8000/api/groups/group-1/expenses");
      assert.deepEqual(JSON.parse(String(init?.body)), {
        title: "Dinner", amount: 60, currency: "EUR", paid_by: "member-1",
        participant_ids: ["member-1", "member-2"],
      });
      return Response.json(receipt, { status: 201 });
    }) as typeof fetch;
    const post = mock.fn(async () => ({}));
    const result = await proposeExpense.handler({ groupId: "group-1", title: "Dinner", amount: 60, currency: "EUR", paidBy: "member-1", participantIds: ["member-1", "member-2"] }, { thread: { post } } as never);
    assert.deepEqual(result, { ...receipt, tripPlannerReplyPosted: true });
    assert.equal(post.mock.callCount(), 1);
    assert.match(JSON.stringify(post.mock.calls[0].arguments), /30.00 EUR/);
    assert.match(JSON.stringify(post.mock.calls[0].arguments), /Anna/);
  });

  it("reports a saved expense separately when its receipt fails, without retrying the write", async () => {
    const fetchMock = mock.fn(async () => Response.json({ id: "expense-saved", title: "Coffee", amount: 12, currency: "EUR", status: "proposed", paid_by: "member-1", shares: { "member-1": 12 } }, { status: 201 }));
    globalThis.fetch = fetchMock as typeof fetch;
    const result = await proposeExpense.handler({ groupId: "group-1", title: "Coffee", amount: 12, currency: "EUR", paidBy: "member-1", participantIds: ["member-1"] }, { thread: { post: async () => { throw new Error("packet path is closed"); } } } as never);
    assert.equal(fetchMock.mock.callCount(), 2); // one name lookup and one write
    assert.deepEqual(result, { id: "expense-saved", tripPlannerReplyFailed: true, error: "The expense was saved, but its Slack receipt failed. Do not create it again." });
  });

  it("creates an itinerary proposal without approving it", async () => {
    globalThis.fetch = mock.fn(async (url, init) => {
      assert.equal(url, "http://127.0.0.1:8000/api/groups/group-1/proposals");
      assert.deepEqual(JSON.parse(String(init?.body)), {
        interests: ["history", "food"], transport: "foot", currency: "EUR",
        assumptions: ["Anna is vegetarian"], note: "Three-day trip",
        max_stops: 8, radius_m: 3000, estimated_cost: 300,
      });
      return Response.json({ id: "proposal-1", status: "proposed" }, { status: 201 });
    }) as typeof fetch;
    const result = await proposeItinerary.handler({
      groupId: "group-1", interests: ["history", "food"], maxStops: 8,
      transport: "foot", radiusM: 3000, estimatedCost: 300, currency: "EUR",
      assumptions: ["Anna is vegetarian"], note: "Three-day trip",
    }, {} as never);
    assert.deepEqual(result, { id: "proposal-1", status: "proposed" });
  });

  it("prepares a constrained local-guide search without inventing results", async () => {
    globalThis.fetch = mock.fn(async (url) => {
      assert.equal(url, "http://127.0.0.1:8000/api/groups/group-1/local-guide?need=quiet%20lunch");
      return Response.json({ search_prompt: "Current quiet lunch in Prague" });
    }) as typeof fetch;
    const result = await prepareLocalGuideSearch.handler({ groupId: "group-1", need: "quiet lunch" }, {} as never);
    assert.deepEqual(result, { search_prompt: "Current quiet lunch in Prague" });
  });
});
