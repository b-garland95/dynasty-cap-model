# NEXT_WORK.md

## Ready

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

### Display Value Team Lost through Roster Clogs as part of the stacked bar to help identify trade candidates

---

## Icebox
