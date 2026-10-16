# Design System — EOIP v4

> **v4 (2026-10-09) sets the current visual direction.** A warm, low-glare operations console inspired by Riyadh and Expo 2030. The ground is cream `#f5f1e8`; panels are warm white `#fffefa`; the navigation and primary identity use deep green `#123d35`; restrained brass `#c6a66b` marks secondary details. Red and amber remain reserved for priority and warning states. The login page pairs a local Riyadh-inspired panorama with a separate cream authentication card.
> - **Signature element: the incident strip.** It is modelled on air-traffic flight strips: a solid priority block at the inline start, then the type, the zone · location chip, the code and the top reason, then sources, status and age. The strip is used on the Overview, Incidents and Map pages; a large variant marks the top P1.
> - **Map:** three zones (soft fill = occupancy), six location nodes (colour = highest open priority, number = open incidents), quiet walkways and small team-count badges. It is labelled as illustrative.
> - **Simulation:** gauges show now / no action / with option against a capacity line at 100%. Staff bars show before and after against each zone's minimum.
> - **Decision support:** an operator bar ("Deciding as") sits above every decision.
> - The source of truth is `static/css/eoip.css`.

**v2 direction (superseded):** an operations instrument printed on limestone. It uses a light, low-glare ground that projects well in a lit hall. One dark ink rail holds the navigation. Colour is reserved for meaning: the four priority levels, EOIP's own voice (teal), and approval (green). There are no gradients, glows, glass panels or decorative card grids.

**Signature element:** the **site plan** (`static/js/siteplan.js`):
- **Hatch density** shows how full a zone is (5 steps).
- **A ring** shows the highest open priority in that zone.
- **A pin** shows the number of open incidents.
- **Dots** show response teams, at their base or at the incident they are assigned to.

The plan appears small on the Overview and full size on the Operations map. Clicking a zone opens its detail.

## Colour tokens (`static/css/eoip.css :root`)

| Token | Hex | Use |
|---|---|---|
| `--ground` | #f5f1e8 | page and login backdrop |
| `--paper` / `--paper-2` | #fffefa / #eee9df | warm-white panels / secondary surfaces |
| `--ink` / `--ink-2` / `--ink-3` | #1c302a / #52635b / #748078 | text levels |
| `--rule` / `--rule-2` | #d9d6cb / #e9e5db | borders / row dividers |
| `--console` / `--console-2` | #123d35 / #1d5549 | navigation rail, mobile bottom bar, primary identity |
| `--voice` / `--voice-bg` | #1d5a4b / #e3eee7 | EOIP's voice: linked reasons, recommendations, primary actions |
| `--p1` | #b92e1c | P1 Critical, failed checks |
| `--p2` | #a9620a | P2 High, warnings |
| `--p3` | #7a6c22 | P3 Medium |
| `--p4` | #5f6e75 | P4 Low |
| `--ok` | #28664b | approved, resolved, passed checks |
| `--sand` | #c6a66b | quiet secondary details and synthetic-data marks |

Each priority colour has a matching `-bg` tint for its badge. Priority is never shown by colour alone: badges always carry the text ("P1 Critical").

## Type
- **Display** (page and section titles): Noto Kufi Arabic when installed.
- **Text:** IBM Plex Sans Arabic when installed; local/system fallbacks include Segoe UI, SF Arabic, Noto Sans Arabic and Tahoma.
- No web-font download is required; the local stack remains available offline.
- Numbers are tabular everywhere.
- Scale: 12 / 13.5 / 15 / 18 / 24 / 40 px.
- No all-caps labels.

## Components
- **Priority badge** `.prio.P1–P4`: a dot, the code and the label.
- **Tags** `.tag`:
  - `ok`, `warn`, `fail`
  - `intel`
  - `live_cv` (red), `replay_cv` (sand), `voice`
  - `mock` (dashed: "Synthetic")
- **Tables** `.table`: full-row links (`data-href`). They scroll horizontally inside their panel on small screens.
- **Why-linked chips** `.why-chips`: one chip per correlation reason, plus a numeric rule score.
- **Priority scale** `.scale`: P4 to P1 bands with a needle at the score; each reason is listed with its signed points.
- **Option** `.option`:
  - title, plain-language description
  - before/after table (`.ba`: now, no action, with this option, queue, net flow; the arrows mirror in RTL)
  - checks (ok / warn / fail)
  - trade-offs
  - Approve / Reject
- **Crew list** `.crew`: team, base zone, hops, ETA.
- **What-if builder** `.whatif`: action, target and amount inputs. Results are recomputed by the server on each change.
- **Toasts:** a critical P1 toast stays until clicked or closed; the others time out.

## Layout
- **Rail:** 236 px plus a main column.
- At **1180 px** the side columns stack.
- At **860 px** the rail becomes a bottom navigation bar.
- At **520 px** lists switch to a stacked layout.
- Logical CSS properties throughout, so RTL and LTR mirror. The site plan does not mirror, because geography must stay true.

## Motion
None beyond the live dot and the toast entrance. `prefers-reduced-motion` is respected.

## Icons
A local inline-SVG stroke set (`static/js/icons.js`), so the pages work offline.
