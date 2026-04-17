# NEXT_WORK.md

## Ready

### Expand Draft Pick Data Model for Original Assignment, Ownership, and Comp Picks

Outcome: Draft pick records correctly represent original assignment, current ownership, configurable compensatory picks, and the distinction between known-order and unknown-order future picks.

Description: The current draft pick ownership framework is too simple for the league’s actual draft structure. We need to expand the model so a pick is not just “owned by” a team, but also has an original team assignment and, when known, a realized draft slot. This is important because picks originate with one team, draft order is determined later based on performance, and ownership can change through trades.

The model also needs to support compensatory picks. Comp picks should be configurable from league settings rather than hardcoded, but the current structure must support the existing extra picks at:
- 2.11
- 3.11
- 4.11
- 4.12

The default ownership of these comp-picks should be empty. 

For future draft years, the exact slot order is not yet known. That means the UI and backend should distinguish between:
- picks for years with a known draft order
- picks for years where only original team assignment is known

By default, a pick should be owned by the same team to which it was originally assigned. Ownership should then be independently editable when picks are traded.

This ticket is about correcting the underlying pick representation and app behavior, not about final pick valuation.

Done when:

  * Draft pick model distinguishes between original assignment and current owner
  * New picks default current owner to original assigned team
  * Ownership can be updated independently from original assignment
  * League settings support configurable compensatory pick structure
  * Current comp picks 2.11, 3.11, 4.11, and 4.12 can be represented correctly
  * Data model supports years with known slot order and years without known slot order
  * UI for future years does not require a finalized slot order when that order is not yet known
  * Pick representation remains compatible with future valuation work
  * Tests cover default ownership, traded ownership overrides, comp pick creation, and future-year unknown-order behavior

Notes for agent:

  * Treat original assignment and current ownership as separate first-class fields
  * Do not assume every future pick can be represented as a fixed slot like 1.03 or 2.07 before order is known
  * Keep comp pick configuration driven by league settings so the structure is reusable across leagues
  * Design the model so future tickets can attach valuation, trade history, and lifecycle state without reworking the schema

### Add Draft Order Submission Workflow for Annual Pick Slot Generation

Outcome: User can submit the finalized draft order for a league year and automatically generate the initial slot structure for that year’s draft across all rounds based on original team assignment and league settings.

Description: Pick slot order is not known until the prior season ends. Once that order is known, we need a workflow for submitting the finalized draft order so the app can build the initial state of that season’s picks. The submitted order should drive slot creation across each round, since the same team ordering repeats by round, with configured comp picks inserted where applicable.

This workflow should allow the app to move a draft year from an “order unknown” state into a “slot order known” state. After submission, each pick for that year should have a concrete round/slot identity based on the entered draft order and the configured league structure.

This ticket is about annual draft-order finalization and pick instantiation, not about managing post-trade ownership changes beyond preserving whatever ownership logic already exists.

Done when:

  * App supports submitting a finalized draft order for a specific league year
  * Submitted order generates the initial slot structure for each standard round in that year
  * Generated slot order repeats correctly across rounds based on the entered team ordering
  * Configured compensatory picks are inserted correctly for the affected rounds
  * Workflow applies to a draft year that previously had unknown future order
  * Generated picks preserve original assignment correctly
  * Existing ownership logic remains compatible after slot generation
  * User receives clear feedback when draft order submission succeeds or fails
  * Tests cover annual order submission, round replication, and comp-pick insertion

Notes for agent:

  * Think of this as a year-finalization workflow that converts abstract future picks into concrete slotted picks
  * Keep the entered draft order as an explicit input that can be inspected and, if necessary, corrected later
  * Make sure generated slot structure is deterministic and reproducible from the submitted order plus league settings
  * Be careful not to overwrite traded ownership state when turning a year into concrete slotted picks

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

### Add Contract Schedule Validation Workflow

Outcome: User can review players whose contract schedules are flagged for validation, confirm or correct their schedules in the app, and persist validated results to the backend override dataset with validation status updated accordingly.

Description: We need a dedicated workflow for validating contract schedules for players we have flagged as needing review. Rather than handling these one-off in backend files, the app should provide a screen that surfaces the outstanding validation queue, lets a user inspect and update the relevant contract schedule details, and then marks those players as validated once review is complete.

Edits made through this workflow should write to the override dataset stored on the backend, since validated schedules represent curated corrections or confirmations relative to raw source data. Validation status should also be persisted so the app can clearly distinguish between players still needing review and players whose contract schedules have already been validated.

This ticket is about the validation workflow, persistence, and status management, not about redesigning the contract ingestion pipeline.

Done when:

  * App has a dedicated screen for contract schedule validation
  * Screen shows players currently flagged as needing contract schedule validation
  * User can inspect the relevant contract schedule fields for a flagged player
  * User can edit or confirm contract schedule details from the UI
  * Saving writes updated schedule data to the backend override dataset
  * Completing validation updates the player’s status from needing validation to validated
  * Validation status persists across reloads and is reflected correctly when the screen is reopened
  * Screen clearly separates validated players from players still requiring review, or filters to only outstanding items by default
  * App provides clear save success and failure feedback
  * Tests cover queue loading, schedule editing, override persistence, and validation status transitions

Notes for agent:

  * Treat the backend override dataset as the source of truth for validated manual corrections
  * Keep the validation status model explicit and durable so future workflows can report on coverage and remaining backlog
  * Design the screen around a review queue pattern, since users will likely validate many players in sequence
  * Avoid coupling “validated” too tightly to “manually changed”; a player may be validated even if the raw schedule was simply confirmed as correct
  * Make sure downstream contract schedule consumers read from the override layer consistently after validation

## Later

---

## Icebox
