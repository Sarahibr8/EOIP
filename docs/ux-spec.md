# UX Spec — EOIP

## 1. User and context
- **Primary user:** the duty operator / shift supervisor in the Expo operations center, watching one large screen during a live event, under time pressure, possibly Arabic- or English-first.
- **Secondary user:** a field supervisor with a phone (simulating a radio).
- **Job:** in under 10 seconds, know what is critical, where it is, why, and what to do. Then decide, and have that decision recorded.

## 2. The eight operator questions → where the app answers them (v2 pages)

| Question | Page → element |
|---|---|
| What is happening? | **Overview**: triage numbers (received → attention → incidents → critical) + latest signals |
| What is critical? | Critical P1 toast (persistent); Overview "Needs a decision"; **Incidents** filter "Critical" |
| Where? | **Operations map**: shading = occupancy, ring = priority, pin = incident count; zone name on every row |
| Which alerts are related, and why? | **Incident details** → linked reports with *why linked* chips (type, zone, time gap, open, new or repeated source) and a rule score; duplicates say which report they repeat |
| Why does it matter? | Incident details → "Why this priority": reasons with points, on a P4–P1 scale |
| What should I do? | **Decision support**: response plan + nearest available team and ETA, or ranked options |
| What happens if I choose this? | Decision support: before/after table and capacity / minimum-staff checks per option; **what-if** builder for the operator's own option |
| What was approved? | Approval banner; status on Incidents; **Decision log** |

## 3. Information architecture

```
Rail (dark):  EOIP · Overview · Operations map · Incidents (count) · Decision support (count awaiting) · Decision log
              · Field reporting · synthetic-data note · Presenter tools · AR/EN
Event bar:    live state · signals · open incidents · critical · awaiting decision · "Synthetic demo data" · Riyadh clock
Pages:        #/  #/map[/zone]  #/incidents  #/incident/:id  #/decide[/:id]  #/log      (+ /field on the phone)
```

Reading order follows the decision: *what* (Overview / Incidents) → *why linked, why this priority* (Incident details) → *what to do and what it causes* (Decision support) → *record* (Decision log). Every incident row opens its details, and every details page has "Open decision support".

## 4. Key flows
1. **Escalation:** a new P1 raises a red toast that names it; clicking it opens its decision page. The app never switches pages under the operator.
2. **Emergency:** Decision support shows the plan steps, the teams to dispatch (nearest free team of each kind, with ETA) and why. The operator chooses "Activate response plan" or "Close as false alarm" (reason required). Activating assigns the teams; if a team was taken in the meantime, EOIP re-plans with the next free team and says so. "Mark resolved" releases the teams.
3. **Operational:** compare the ranked options (the recommended one is outlined), or build one in "Try your own option" (divert / move staff / meter). The numbers recompute on the server and are labelled "nothing is saved". "Add as option" saves it; then Approve, or Reject with a reason.
4. **Routine:** assign to the owning team (facilities / IT). Routine incidents (P4) are kept off the Overview's "Needs a decision" list.
5. **Field report (phone):** tap the mic → speak → EOIP shows what it understood (type, location, confidence) → correct it → Send → the confirmation shows the incident code and priority.

## 5. States
- **Empty:** queue, stream, log and detail each say what will appear and what to do ("Start the live event…").
- **Errors:** a network toast with a fix; a missing reason is an inline message next to the field; closed incident or already-decided option get specific toasts.
- **Mic unavailable / denied:** the button is disabled, and an explanation points to typing or keyboard dictation.

## 6. Bilingual rules
- Every visible string comes from `static/i18n/{ar,en}.json`; both files have the same keys (a test enforces this).
- `dir` switches on `<html>`; CSS uses logical properties (`inset-inline-start`, `padding-inline-start`), so bars, stripes and borders mirror correctly.
- Digits are Latin in both languages (`ar-SA-u-nu-latn`), which suits mixed-script ops screens and codes like INC-0010. Time is shown in Riyadh time, 24 h.
- Codes inside Arabic sentences are bidi-isolated (U+2068/2069).

## 7. Usability evaluation
See `testing.md §4`: a structured expert walkthrough, explicitly **not** a user study.

## v3 changes (2026-10-09)
- **Incidents page:** filter by priority (chips), type, zone and status; sort by priority, latest update or zone; a "needs review" filter for signals.
- **Incident details:** each linked report shows its zone · location, time received (and the time said, if different), why it was linked (incl. same / different / unstated location) and a rule score.
- **Decision support:**
  - "Deciding as" must hold a name before any approve, reject or close. The name is remembered in this browser only and is not an identity check.
  - Tabs: Ranked options / Crowd simulation (receiving zone + share) / Staffing simulation (from zone, receiving zone, count).
- **Decision log:** operator, decision, incident (code, type, zone · location), option, teams, simulation result, priority then, reason. Split into *this event run* and *earlier runs*; filter by decision type.
- **Field page:**
  - **Voice report:** text → "What EOIP understood" shows event, zone and location, each marked *from what you said*, *from the location* or *not mentioned*, plus review reasons (negation, two events, two zones, mismatch).
  - Locations are filtered by zone, with "Other location…" and a details field.
  - Sending without a zone stores the report for review.
  - **Camera:** live analysis or video file, with status messages for opening, starting the detector, watching (person upright / lying), detection and errors. The honest-method note is always visible.
