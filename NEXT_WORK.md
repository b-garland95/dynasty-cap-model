# NEXT_WORK.md

## Ready
### Update Player Forecasted Valuation Framework
**Outcome:** Players are evaluated on 1, 3 and 5 year value windows, all converted to per-year averages to keep basis of analysis consistent. 

**Description:** The current PV TV Framework is confusing and not helpful. As a user, I want to understand the value players are going to offer over particular windows of their career. For instance, on the cap health dashboard, plotting PV TV and PV Cap against eachother doesn't mean very much to me right now. I want to be able to see how the teams stack up against eachother when just looking at this year, or the long-range forecasts, but all of this normalized to per-season value so I'm not constantly having to change my frame of reference. 

**Done when:** 
- [ ] Can view player's Current Year Value Walk Down (Projected - Cap Hit = Surplus)
- [ ] Can view player's year 0 to year 2 contract value (Projected on contract years remaining per year - cap hit per year = surplus per year)
- [ ] Can view player's year 0 to year 4 contract value (Projected on contract years remaining per year - cap hit per year = surplus per year)
- [ ] League Analysis Contract Surplus and Cap Health views have drop down to select analysis window. Default is current year. 
- [ ] References to "PV TV" and "PV Cap" are removed from app. We need more human readable names for these metrics. 

### League config Screen in app for manual adjustments
**Outcome:** User can adjust each team's components of salary cap calculation to ensure it matches League Tycoon exactly

**Description:** Right now, the salary cap remaining for teams is somewhat implied. Unfortunately, there are a few details not captured in the roster export that further influence a team's cap. They are: 
1) Dead Money
2) Cap Transactions (cap included in trades)
3) Rollover from previous year

Instead of trying ot calculate this based on a previous transaction log, for now it will likely be easiest to just create a screen where a user can input these numbers for each team in the league and then that get included on the backend to calculate the actual cap available to a team, a metric we should definitely include in the Cap Health dash if it isn't ther already. 

**Done when:**
- [ ] User can manually input cap levers for each team in a UI on the front end
- [ ] User can trigger whatever backend scripts are necessary to recalculate relevant outputs
- [ ] User can see Cap Remaining (Starting Team Cap - Current Contract Value - Dead Money - Cap Transactions + Rollover) on the Cap Health screen

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