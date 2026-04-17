# NEXT_WORK.md

## Ready

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

### Add Scalable League Config and League Data Management Screen

Outcome: User can manage league-level configuration, upload refreshed roster data, persist those changes back to the backend source-of-truth files, and trigger a refresh of downstream analytical outputs from the UI.

Description: We need a scalable way to manage league configuration and core league data without manually editing backend files. The app should include a dedicated League Config management screen that acts as the operational control center for league-level settings and key uploaded inputs.

This screen should read from backend source-of-truth files, expose supported configuration fields in a structured UI, allow users to save changes back to the backend config, support uploading a refreshed Rosters file via file drop, and provide a clear action to update all downstream analytical outputs after edits are made.

This should serve as the long-term home for league-level settings and manual overrides that affect analysis. That includes both broader configuration controls and team-level cap adjustment inputs that are not reliably available from roster exports.

Initial manual adjustment inputs should include:
- Dead Money
- Cap Transactions
- Rollover from previous year

These values should be persisted in the backend config layer and incorporated into downstream calculations. The most important immediate downstream surface is Cap Health, which should show Cap Remaining using the configured values.

The screen should also support replacing or refreshing the backend Rosters source via file drop so users can update league data without manual backend intervention. After config changes or file uploads, the user should be able to trigger a recomputation of analytical outputs so the app reflects the latest configuration and roster state.

This ticket is about the config management workflow, backend synchronization, roster file ingestion entry point, and recompute pattern. It is not about building a full transaction ledger or redesigning every config field at once.

Done when:

  * App has a dedicated League Config / league data management screen for league-level settings and operational inputs
  * Screen reads current values from the backend config source of truth
  * User can edit supported config fields from the UI
  * League Config screen supports team-level manual cap adjustment inputs for every team
  * Initial cap adjustment fields include Dead Money, Cap Transactions, and Rollover from previous year
  * Saving from the UI writes config changes back to the backend config source of truth
  * Screen supports file drop upload for refreshing the backend Rosters file
  * Uploaded roster file is validated before being accepted
  * Successful roster upload updates the backend roster source of truth for supported workflows
  * Screen includes a clear action to update or recompute analytical outputs after config changes or roster uploads
  * Analytical outputs reflect updated config values and roster inputs after recomputation
  * Cap Health screen shows Cap Remaining using configured adjustments
  * Cap Remaining is calculated as: Starting Team Cap - Current Contract Value - Dead Money - Cap Transactions + Rollover
  * App provides clear feedback for save success, roster upload success, recompute success, validation issues, and failure states
  * Validation prevents invalid config values or malformed roster files from being written
  * Config editing and roster refresh workflows do not require manual backend file edits for supported operations
  * Tests cover config load, config save, roster upload validation, roster persistence, recomputation behavior, and displayed cap remaining values

Notes for agent:

  * Keep backend config and backend roster data files as source-of-truth inputs, but add an app-layer workflow for editing and replacing supported inputs safely
  * Separate “save config changes,” “upload roster file,” and “refresh analytical outputs” into distinct actions unless the existing architecture strongly favors combining some of them
  * Treat manual cap adjustments as league configuration inputs, not as a transaction-history reconstruction system
  * Keep the schema and screen structure extensible so additional config sections and uploaded league data sources can be added over time without rebuilding the whole screen
  * Validate uploaded roster files against the expected shape before replacing the backend source
  * Confirm whether Cap Transactions should support positive and negative values depending on league convention, and implement consistently
  * Make failure states debuggable, especially when config save succeeds but recomputation fails, or roster upload succeeds but downstream parsing fails
  * Surface values and upload results in a way that makes debugging mismatches against League Tycoon straightforward

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
