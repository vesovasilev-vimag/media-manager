# Library overview visualization

Frontend-only addition to the pending Library UX/English naming PR. The requested screenshot was not attached in the available conversation/workspace; the implementation follows the supplied panel composition and the existing ViMag colors, typography and spacing. Exact screenshot matching is therefore unverified.

`LibraryAnalytics.vue` replaces the two progress-meter panels. Native SVG renders a count-based donut, with API-derived total count, category tooltips and separated percentage labels. A compact statistics table uses the requested category order and shares its byte/count totals with the donut and total-size KPI. The adjacent CSS bar chart sorts categories by actual bytes, uses the same category colors, displays binary units and chooses a readable axis range dynamically. No chart dependency is added.

All values come from the existing `/api/v1/library/analytics` response. Backend calculations and API/schema remain unchanged. Known byte sizes are summed once for chart/table/KPI presentation; binary conversions use GiB/TiB, never decimal GB/TB labels. `known_sizes` distinguishes incomplete metadata from proven zero bytes, with explicit partial-total notices. Initial loading and API failures do not display a fabricated zero total; a failed refresh identifies previously loaded data as stale. Empty libraries show zero values and no donut percentage labels. Invalid numeric data produces an unavailable state.

The two panels sit beside each other when the Library container has sufficient width, stack on tablets and adapt within narrow mobile layouts. The mobile size KPI moves below the bars to preserve usable chart width. Charts have accessible labels, category tooltips and an equivalent semantic table, so color and SVG are not the only access to data. Existing Library actions, filters, sorting, pagination and selection remain intact.

Regression coverage: `frontend/tests/analytics.test.ts` checks count/byte totals, binary units, sorted bars, shared colors, percentages, zero values, unknown sizes, loading/errors/stale data and crowded-label separation. `frontend/e2e/library-analytics.spec.ts` verifies values, layout, label non-overlap and no page overflow in Chromium at 1600, 1024, 390 and 320 pixels; screenshots are retained in `.test-artifacts` and uploaded by CI. Existing action/menu/delete regressions still run.

No backend changes, production reads/writes, image publication, merge or deployment are part of this addition. Release authorization remains separate.
