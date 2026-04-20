# NEXT_WORK.md

## Ready

### Add Rookie Pick Activation Curve and Effective Cap Treatment

Outcome: Draft picks have an effective current-year cap hit and effective current-year value contribution that reflect the probability a rookie is activated off the practice squad, rather than treating every pick as either fully active or always discounted.

Description: We now have draft-pick value logic available elsewhere in the app, but the cap-health side of the system still needs a realistic way to translate rookie picks into current-year cap burden and value contribution. In League Tycoon terms, rookie picks will eventually become players on rookie-scale deals, and those players may either remain on the practice squad at the 25% cap rate or be activated such that their full cap counts against team salary cap. For current cap-health projections, we need a simple first-pass model for that activation risk.

For v1, implement a naive activation curve by pick slot using a hard-tailed log-style decay. The core behavior should be:
- 1.01 is very likely to be activated, and activated early
- late 1st-round picks should still carry meaningful activation probability
- 2nd-round picks should tail off sharply
- later rounds should have materially lower activation likelihoods

That activation probability should be used symmetrically to discount both:
- the pick’s current-year cap hit burden
- the pick’s current-year value-added contribution

This should produce an expected effective cap hit and expected effective value contribution for each pick. The implementation should be structured so the activation curve can be replaced later by a more evidence-based model without reworking downstream consumers.

This ticket is about the backend economics and cap-treatment logic, not the Cap Health dashboard presentation.

Done when:

  * Backend computes an activation probability for each rookie pick based on pick slot
  * Activation curve is directionally consistent with league expectations, especially steep drop after Round 1
  * Each pick has an effective current-year cap hit derived from rookie-scale cap and activation probability
  * Each pick has an effective current-year value-added contribution derived from pick value and the same activation probability
  * Full-cap vs practice-squad-discount behavior is modeled explicitly rather than implicitly
  * Logic uses existing rookie-scale / pick-structure config rather than duplicating salary assumptions
  * Logic is written so the activation curve can be tuned or replaced later without breaking downstream consumers
  * Tests cover curve monotonicity, 1.01 high-activation behavior, sharp round-2 dropoff, and effective cap/value discounting

Notes for agent:

  * Keep league rules sourced from config rather than hardcoding constants that already exist elsewhere
  * Use one shared activation-probability function for both cap-hit discounting and value-added discounting
  * Be explicit about whether the expected cap hit is modeled as:
    expected cap = p_activate * full_cap + (1 - p_activate) * discounted_ps_cap
  * Preserve a clean distinction between intrinsic pick value and current-year realized cap/value expectation
  * Favor an intentionally simple curve in v1, but make the function shape and parameters easy to inspect and tune

### Wire Draft Pick Value and Effective Cap Burden into Cap Health Dashboard

Outcome: The Cap Health dashboard includes draft-pick value and draft-pick cap burden in team projections instead of showing picks as TBD.

Description: The app already has enough pick-value logic to surface dollar values for draft picks in other workflows, including trade analysis. The Cap Health dashboard should now consume that logic so teams’ projected outlooks include the effect of owned draft capital. Today that area still shows draft picks as TBD, which understates both future value and cap obligations.

This work should wire pick economics into the Cap Health dashboard using the effective outputs produced by the rookie activation / cap-treatment layer. Team-level cap-health outputs should therefore reflect both:
- value added from owned picks
- cap consumed by those picks

This is especially important because picks are not “free” assets in this league context. Their associated rookie contracts consume cap, and that cost should reduce cap available in the dashboard. The dashboard should therefore show a more complete team outlook by incorporating both the upside and the burden of draft capital.

For v1, use the newly available pick-value and effective-cap logic as-is. The goal is to replace the current TBD placeholder and correctly wire picks into team-level projections, not to perfect the underlying pick model in the same ticket.

Done when:

  * Cap Health dashboard no longer shows draft-pick contribution as TBD
  * Team-level projections include owned draft-pick value using the existing pick value framework
  * Team-level projections include owned draft-pick effective cap burden using the activation-discounted cap logic
  * Draft-pick cap burden is backed out of available cap in the Cap Health view
  * Dashboard clearly distinguishes player-contract burden from draft-pick burden if both are shown
  * Pick-related value and pick-related cap impact roll up correctly at the team level
  * Output is directionally consistent with owned-pick inventory across teams
  * Tests cover dashboard integration and at least one end-to-end case where owned picks change both projected value and available cap

Notes for agent:

  * Reuse the same pick value source already powering trade-related views rather than re-implementing valuation in the dashboard layer
  * Treat this as a wiring/integration ticket; the dashboard should consume backend outputs, not embed its own pick math
  * Make the presentation legible enough that users can tell why a team’s cap available changed after pick costs are included
  * Be careful about double counting when combining player value, player cap burden, pick value, and pick cap burden
  * If there is a current-year vs multi-year split inside Cap Health, make sure pick treatment is applied consistently to the intended horizon

### Add Draft Year Lifecycle State for Spent Picks After the Draft

Outcome: User can mark a draft year as completed after the rookie draft occurs, and the app will treat that year’s picks as spent while relying on updated roster data to reflect the resulting player-team assignments.

Description: Once the rookie draft has happened, the current-year picks are no longer active assets. We need a way to indicate that a draft year has been completed so those picks are no longer treated as available inventory in the app. Updated roster data will handle assigning drafted players to teams, so this workflow is primarily about pick lifecycle state rather than player ingestion.

This should let the app distinguish between:
- future draft picks that are still active assets
- current-year picks before the draft
- current-year picks after the draft has been completed and spent

The transition should be explicit and durable so downstream analysis does not continue showing already-used picks as tradable or available.

This ticket is about draft-year lifecycle state and post-draft cleanup behavior, not about parsing draft results from transaction history.

Done when:

  * App supports marking a draft year as completed after the draft occurs
  * Completed draft year no longer shows its picks as active tradeable inventory
  * League Analysis and related pick views treat completed-year picks as spent
  * Draft completion state persists across reloads
  * Workflow is compatible with refreshed roster CSV uploads that assign drafted players to teams
  * UI clearly indicates whether a draft year is active, finalized, or completed
  * Tests cover draft-year completion state and removal of spent picks from active views

Notes for agent:

  * Treat this as lifecycle state for picks, not as player assignment logic
  * Keep the transition explicit rather than inferring it automatically from roster uploads alone
  * Make sure downstream consumers do not continue valuing or surfacing spent current-year picks once the year is completed
  * Design the lifecycle state so future tickets can support richer draft-history views if needed



## Later

---

## Icebox
