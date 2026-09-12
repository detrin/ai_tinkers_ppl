# SomeJoy — submission draft and evidence checklist

Use the [event rules](hackathon-rules.md) and your city's participant portal
for final eligibility and deliverables. This document describes repository
capabilities; it is not proof that every live integration has been verified.

## Title and pitch

**SomeJoy: plan the trip in the chat you already have.**

Friends discuss a city trip in Slack. A travel assistant creates a shared group,
researches options, and proposes practical next steps. The group opens the same
trip in a map dashboard to see locations and routes, approve shared expenses,
vote on decisions, and view trip records.

For the demo, show one real Slack-to-dashboard write and one human decision:
propose a shared expense in Slack, then approve it in the web UI and show the
updated balances. See [the run of show](dev-docs/somejoy-demo.md).

## Build eligibility and attribution

The team's existing submission notes identify starter commit `86f547d` and
event work beginning at `2093be5`. Confirm that attribution and the event
window before submitting; this documentation review does not independently
certify authorship or eligibility.

Inherited from the CopilotKit Agents, Everywhere starter:

- Channels runtime, managed Slack delivery, thread subscriptions/context,
  native-card infrastructure, and generic approval reference flow.
- Next.js/CopilotKit runtime and frontend-tool infrastructure.
- Ambiguous follow-up task integration and its approval/read-back foundation.
- Shared model configuration and portions of system/surface instructions.
- React Native finance reference and demo assets. Some incident components/tools
  remain in the repository; they are not the SomeJoy product workflow.

Project-specific additions include:

- FastAPI groups, join codes, city discovery, route planning, live positions,
  preference/message/thread APIs, and itinerary proposals.
- React/Vite map dashboard and specialist workspace.
- Slack trip creation/lookup, itinerary, research and specialist tools.
- Expense splitting/approval, polls, media metadata, packing, and memories.
- Pydantic AI advisory research agent and backend bridge.
- Trip-focused Next.js page/context and itinerary review.
- Fast lookup replies, expense receipts, and run diagnostics.

Libraries/services include FastAPI, Pydantic AI, React, Vite, Leaflet, Next.js,
CopilotKit, model providers, OpenStreetMap/Nominatim/Overpass, OSRM, and optional
OpenRouteService, Exa, Google Maps and Ambiguous integrations.

## What to demonstrate

| Evidence | Show |
| --- | --- |
| Shared context | Slack creates a group; the real join code opens that group in the dashboard |
| Agentic action | A prompt saves a proposed expense using registered travellers |
| User control | Proposed expenses do not affect balances; approving one updates the ledger |
| Group collaboration | A Slack-created poll appears in the dashboard and registered users vote |
| Grounded research | Exa returns real source links in Slack; open a source |
| Physical context | Users explicitly share/drop positions and build a route on the map |

Itinerary proposal approval is available in the separate Next.js workspace.
The map's direct Build route action publishes without that proposal step.
Do not present the two paths as one universal approval boundary.

## Integration roles

- **CopilotKit Channels:** managed Slack delivery, thread context, agent/tools,
  native UI.
- **Configured model provider, including OpenRouter:** tool selection and
  conversational responses; exact model depends on the environment.
- **Optional Anthropic ranking:** selects from real backend place candidates,
  with heuristic fallback.
- **Exa:** current web discovery and source links when configured.
- **Optional Google Maps:** advisory-agent place/route tools.
- **Ambiguous AI:** approved follow-up task create/read-back in Next.js,
  not the main trip database or unrestricted Slack tools.

Only claim a live integration in the final video if it has been exercised with
the configured account and the real result can be shown.

## Evidence for the judging criteria

| Criterion | Evidence to collect |
| --- | --- |
| Core Requirements & Functionality | A real Slack request saves a record that can be read back in the dashboard |
| Innovation & Theme Alignment | Show the conversation and shared trip context that make the interaction useful |
| Technical Execution & Integration | Show provider boundaries, a real approval transition, and honest recovery after a failure |
| Usefulness & Agentic Experience | Show the work saved for a travelling group and the controls that keep users involved |

These are evidence targets, not claims that a final live recording exists or
that a particular judging score is assured.

## Known limitations

- Specialist agents are tools/workflows, not independently hosted autonomous
  services.
- Slack thread reading works, but automatic per-speaker preference extraction,
  message archiving, and thread-to-trip backend mapping are not wired.
- Backend trip state has a single-process JSON snapshot; advisory history and
  candidates are separate and in-memory.
- No production authentication or per-trip authorization.
- Media is metadata/keyword classification, not image upload, vision or OCR.
- Expenses are equal-split accounting, not payments; use one currency.
- Packing is on-demand, not a saved shared checklist or live weather integration.
- Advisory proposals and search results do not automatically publish to the map.
- Not every write is idempotent. Read back after timeouts before repeating.
- Routes may use approximate walking distances and do not guarantee accessible
  legs, current hours, dietary suitability or a complete multi-day budget.

## Verification checklist

Run and record the current results rather than relying on an old test count:

```bash
npm run verify
npm run build --prefix frontend
cd backend
.venv/bin/python -m pytest -q
```

Run `uv run pytest` in `services/agent` for that component.
Offline checks do not prove live Slack/model/search delivery.

- [ ] Clean-clone setup verified by another teammate
- [ ] Backend health and correct UI build checked
- [ ] One active listener; real Slack lookup succeeds
- [ ] New expense appears in UI, approval changes balances
- [ ] Poll creation and voting verified
- [ ] Exa source links verified if included
- [ ] Ambiguous create/read/decline verified if included
- [ ] Required tests/builds recorded for the submitted revision
- [ ] Eligibility and inherited-code attribution confirmed by the team
- [ ] Secrets/private trip data excluded from Git, screenshots and logs

## Final deliverables

- [ ] Public repository and readable setup/capability documentation
- [ ] Demo video within the event's limit, with understandable audio
- [ ] Visible real record/result, not only assistant claims
- [ ] User review distinguished from actual execution
- [ ] Sponsor credits appropriate to demonstrated integrations
- [ ] Submission and social post reviewed and published by a human

Do not promise that the assistant automatically heard and persisted every
traveller constraint, that all writes deduplicate, or that photos are analyzed.
Those are roadmap items, not current demo evidence.
