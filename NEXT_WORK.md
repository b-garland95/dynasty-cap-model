# NEXT_WORK.md

## Ready

### Update Player Forecasted Valuation Framework

**Outcome:** Player valuation views support clear, human-readable surplus analysis across multiple forecast windows, with all outputs normalized to per-season values so users can compare short- and long-term value on the same basis.

**Description:** The current PV/TV framework is hard to interpret and does not provide a clean decision-making frame for dynasty cap management. We should replace the current labels and analysis framing with window-based player value views that show surplus on a per-season basis. The goal is to let a user evaluate how players and teams look in the current year, medium-term, and long-term windows without constantly translating between different time horizons or metric bases.

This work should support at least 3 analysis windows:
- Current year
- 3-year window
- 5-year window

For multi-year views, valuation should be expressed as an average annual projected value over the selected window, compared against average annual cap hit over the same relevant contract span, so surplus is interpretable on a like-for-like per-year basis. This framing should flow through to League Analysis surfaces such as Contract Surplus and Cap Health.

This ticket is about the evaluation framework and presentation layer, not about changing the underlying forecast engine unless needed to support the new outputs cleanly.

**Done when:**
- [ ] App supports current-year, 3-year, and 5-year player valuation windows
- [ ] Current-year player view shows current-year projected value, current-year cap hit, and current-year surplus
- [ ] 3-year player view shows average annual projected value, average annual cap hit, and average annual surplus across the relevant 3-year window
- [ ] 5-year player view shows average annual projected value, average annual cap hit, and average annual surplus across the relevant 5-year window
- [ ] League Analysis Contract Surplus view has a control for selecting valuation window
- [ ] League Analysis Cap Health view has a control for selecting valuation window
- [ ] Default valuation window is current year
- [ ] Existing “PV TV” and “PV Cap” labels are removed from user-facing app surfaces
- [ ] Replacement metric names are human-readable and consistently applied across UI
- [ ] Edge cases are handled cleanly when a player has fewer remaining contract years than the selected analysis window
- [ ] Tests are updated for window selection, surplus calculations, and label changes

**Notes for agent:**
- Keep this focused on improving interpretation and decision usefulness, not inventing a brand-new forecasting model
- Be explicit about how selected windows interact with contract years remaining
- Prefer one shared valuation-window abstraction used across player detail and league analysis views
- Use naming that matches how a fantasy manager would naturally think, such as current-year surplus, 3-year annualized surplus, and 5-year annualized surplus
- Watch for hidden dependencies in charts or downstream tables that still expect legacy PV/TV field names


### League Config Screen in app for manual adjustments

**Outcome:** User can manually enter team-level cap adjustment inputs that are not captured in the roster export so app-level cap calculations match League Tycoon more closely.

**Description:** Current cap remaining is partly implied from roster data, but the export does not capture all components required to match actual league cap space. To close that gap, we should add a League Config screen where a user can input team-level cap adjustment values directly. For now, this is preferable to reconstructing those values from transaction history.

Initial manual adjustment inputs should include:
- Dead Money
- Cap Transactions
- Rollover from previous year

These values should be persisted in the backend and incorporated into cap calculations used by league analysis outputs. The most important downstream surface is the Cap Health dashboard, which should show a cap remaining figure aligned to the configured values.

This ticket is about creating a durable manual adjustment workflow, not building a full transaction ledger.

**Done when:**
- [ ] League Config screen allows manual input of cap adjustment fields for every team
- [ ] User can save cap adjustment inputs and reload them later
- [ ] Backend stores team-level values for dead money, cap transactions, and rollover
- [ ] App recalculates relevant outputs after config changes without requiring manual code edits
- [ ] Cap Health screen shows Cap Remaining using configured adjustments
- [ ] Cap Remaining is calculated as: Starting Team Cap - Current Contract Value - Dead Money - Cap Transactions + Rollover
- [ ] Inputs are validated to prevent invalid or malformed values
- [ ] UI clearly indicates what each cap lever means
- [ ] Tests cover persistence, recalculation, and displayed cap remaining values

**Notes for agent:**
- Treat these values as league configuration inputs and make them easy to update over time
- Keep the schema extensible in case future manual cap levers need to be added
- Make sure recalculation behavior is predictable after edits; avoid requiring the user to run opaque backend steps if the app can do it directly
- Confirm whether Cap Transactions should support positive and negative values depending on league convention, and implement consistently
- Surface these adjustments in a way that makes debugging mismatches against League Tycoon straightforward

### Add Draft Pick Ownership Management

Outcome: User can assign and persist rookie draft pick ownership by team for the current league year and future draft years, and that information is visible in the app for later valuation work.

Description: We need a foundational system for managing draft picks before building draft pick valuation. The app should support tracking who owns each rookie pick, starting with the current league year plus the next 2 league years. That horizon should be configurable from league settings rather than hardcoded. There is already repo context for the rookie pick pay scale, so this ticket is focused on pick ownership management, storage, and display rather than pricing or valuation logic.

This should include a League Config workflow where a user can assign each pick to a team, a backend representation for storing and loading that ownership data, and initial surfacing of pick ownership on the League Analysis page so that future trade / asset views can build on it.

Done when:

  * User can view draft pick inventory for the current league year and future league years on a League Config page
  * User can assign each pick to a team from the UI
  * Pick ownership is persisted in the backend and survives app reloads
  * Number of future draft years tracked is configurable in league settings
  * Default tracked horizon is current league year + next 2 league years
  * Data model cleanly supports one owner per pick per year/round/slot
  * Existing rookie pick pay scale context is not duplicated or hardcoded in a second place
  * League Analysis page shows each team’s owned picks in a readable format
  * Tests cover config/load/save behavior and at least one UI or integration path

Notes for agent:

  * Scope this as pick ownership only, not pick valuation
  * Keep source-of-truth league settings in config, consistent with existing repo conventions
  * Design the schema so future tickets can attach pick value, trade history, and pick-based surplus outputs without reworking storage
  * Consider representing picks at the individual pick level (for example: 2026 1.01, 2026 1.02, etc.) if that aligns with the existing rookie pay scale structure
  * League Analysis display can be simple at first, but should clearly answer “which picks does each team own?”

### Remove WMSV vs. ESV Historical Analysis Chart

Outcome: The historical analysis module no longer includes the WMSV vs. ESV chart, reducing maintenance burden and keeping the module focused on durable long-term analysis views.

Description: The WMSV vs. ESV chart was useful as a one-time validation artifact while testing the framework, but it is not intended to be a permanent analysis surface. We should remove it from the historical analysis module so the product only exposes analysis frames we expect to maintain and rely on over time.

This ticket is about removing the chart from the user-facing historical analysis experience and cleaning up any related code paths, wiring, and tests that only exist to support this visualization.

Done when:

  * WMSV vs. ESV chart no longer appears anywhere in the historical analysis module
  * Any UI controls, labels, or explanatory copy tied only to this chart are removed
  * Underlying code paths, data transforms, and component wiring used exclusively for this chart are removed or simplified
  * Historical analysis module still renders correctly without layout or navigation regressions
  * Tests are updated to reflect the removed chart
  * Documentation or notes referencing this as a maintained analysis view are updated if applicable

Notes for agent:

  * Treat this as removal of a validation artifact, not a redesign of the broader historical analysis module
  * Preserve any reusable calculations only if they are still used elsewhere
  * Favor deleting dead code rather than leaving dormant feature flags unless the repo already has a strong convention for that

### Tighten Comparable Players Modal Window

Outcome: The comparable players tab in the player modal shows a focused comparison set with only the 5 players directly above and 5 directly below the selected player under the active evaluation framework.

Description: The comparable players tab is currently too crowded, which makes it harder to quickly understand the most relevant nearby player comps. We should narrow the displayed comparison set so that, for the currently selected evaluation framework, the modal only shows the 5 players immediately above and the 5 players immediately below the target player in the ranking order.

This should be framework-aware, so the displayed neighbors update based on whichever evaluation framework is currently selected. The selected player should remain the anchor point, and edge cases near the top or bottom of the rankings should be handled cleanly.

Done when:

  * Comparable players tab shows only the 5 players ranked directly above and 5 directly below the selected player
  * Comparison set is derived from the currently selected evaluation framework
  * Selected player remains clearly identified as the anchor of the comparison window
  * Edge cases near the top or bottom of the rankings degrade gracefully without errors
  * UI remains readable and less crowded than the current implementation
  * Any tests covering comparable player selection or rendering are updated accordingly

Notes for agent:

  * Use the active framework ranking order as the source of truth for neighbor selection
  * Keep this scoped to narrowing the displayed comparison window, not redefining similarity logic
  * Confirm whether the selected player itself should remain visually included between the above/below groups, but do not include extra surrounding players beyond the intended window

## Later
### Import updated Roster CSV into app + Update Phase 2 and 3 Outputs
**Outcome:** User can upload new version of rosters file, and reports in Forecasted and League Analysis tabs update accordingly

**Done when:**
- [ ] 

**Notes for agent:**
- Should be a one-stop shop for all player analysis
- Feel free to add other views you think would be valuable within the context of the league

---

## Icebox
