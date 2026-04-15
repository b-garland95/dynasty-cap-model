# NEXT_WORK.md

## Ready
### Improve retry handling for import job
**Outcome:** Import job survives transient upstream failures without manual reruns.

**Why now:** This is causing the most avoidable operational friction.

**Done when:**
- [ ] Retries use exponential backoff
- [ ] Final failure is logged clearly
- [ ] Tests cover transient failure and terminal failure

**Notes for agent:**
- Likely files: `src/import/*`, `lib/http_client.*`
- Check whether retry logic already exists elsewhere before adding new code
- Prefer small refactor over introducing a new dependency

### Add dry-run mode for migration command
**Outcome:** I can preview migration actions without changing state.

**Why now:** Reduces risk while iterating on migration behavior.

**Done when:**
- [ ] Command supports `--dry-run`
- [ ] Output clearly shows intended changes
- [ ] Tests cover no-write behavior

**Notes for agent:**
- Reuse existing logging/output style
- Make sure dry-run path cannot write accidentally

---

## Later
### Split config parsing from runtime boot
**Outcome:** Startup logic is easier to test and reason about.

**Why later:** Helpful, but not blocking current work.

**Done when:**
- [ ] Parsing is isolated from app startup
- [ ] Core config behavior has focused tests

**Notes for agent:**
- Watch for environment-variable coupling

---

## Icebox
### Explore webhook-based sync instead of polling
**Outcome:** Lower latency and fewer unnecessary sync runs.

**Why parked:** Worth exploring only after core flow is stable.

**Notes for agent:**
- Need to compare complexity, reliability, and provider support
