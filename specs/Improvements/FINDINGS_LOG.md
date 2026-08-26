# Findings log — recurring defect classes

Every entry here is a defect that actually happened in this codebase, generalised into the shape it
will take next time. Kept separate from `IMPLEMENTATION_LOG.md` (what was done, newest last) and
`PENDING_ITEMS.md` (what is open) because those answer different questions. This one answers:
**what keeps going wrong, and what would have caught it.**

Ordered by how often each has recurred.

---

## 1. A check that verifies PRESENCE does not protect CONTENT

The most expensive pattern of the last week, by a distance.

| Instance | What passed while it was wrong |
|---|---|
| `notes.dcm_basis` claimed the engines disagreed at 29.0 % | its test checked the note **existed** and mentioned Chapter 7 |
| `test_payload_notes_are_true.py` v1 called itself "every note a payload publishes" | it scanned only the top-level `notes`; a probe in the capacitor note passed cleanly |
| Combined-report page count sat at 178-190 against a 212-page document | the check ran and printed OUT OF RANGE; nobody read it |
| `_SUP` superscript table described as "renders correctly" | nothing rendered it |

**The question to ask of any new guard:** *does this verify the claim, or only that the claim
exists?* If a test would still pass with the subject replaced by plausible nonsense, it is a
presence check.

**What works:** generate the prose from the data (`DCM_AGREEMENT_TOLERANCE_PCT` → note text →
imported by the test), publish the figure as data next to the prose, and have a test read the
number back **out of the published text** and measure reality against it.

---

## 2. A list of sites goes stale; a count does not

| Instance | Named | Actual |
|---|---|---|
| C2 download paths | 7 | 8 — `downloadCh7` written after the fix |
| C3 sandboxed iframes | 2 | 3 — `SimulationAgent.tsx` written after the entry |
| A10 untracked workbooks | 1 | 2 — `Power_Relays_Database.xlsx` |

All three were written down correctly and all three grew a new member nobody re-counted.

**What works:** guards that **enumerate from the tree** and fail on anything unlisted, never
assertions against a fixed list. `test_downloads_go_through_helper` counts download sites;
`test_every_studio_iframe_allows_downloads` counts iframes.

---

## 3. A green check on a built artefact only covers the branches one fixture takes

The combined report read **zero black squares for months** while two page footers printed one on
every page — the reference design simply never took those branches.

**What works:** pair every rendered-output check with a source scan. The rendered check has no false
positives; the source scan reaches the conditional branches. Neither alone is sufficient.

---

## 4. Two copies of a mapping agree until the day one is edited

| Instance | Consequence |
|---|---|
| `control_design.html` in `public/` and `src/assets/` | two rounds of "fixed" never reached the browser (C244) |
| FAN9672 schematic context, in the report builder and again in its test | R_RLPK drawn at a defaulted 15 kΩ while the BOM said 12.1 (C235) |
| Standalone Ch7 vs combined report inputs | flat 127 µH against a 134–154 µH bias curve (C255) |

**What works:** one definition with a test pinning any surviving copy to it
(`test_the_schematic_context_has_one_definition`). Where the duplication cannot be removed yet,
the test is what makes leaving it safe.

---

## 5. A docstring asserting an invariant is where nobody looks

> *"This is the same builder the combined report calls, so the two cannot disagree — it is the same
> chapter, not a second rendering of it."*

Same builder, different **inputs**. That sentence sat directly above the endpoint missing the
enrichment, and is why the divergence went unexamined for months.

**What works:** if a property matters, test it. A comment claiming it actively suppresses the check.

---

## 6. A diagnosis written from reading code, not from measuring it

**PENDING B23** blamed an `L_eff` back-out and a current-definition mismatch. Measured at C263:
no ripple target is supplied, so the back-out never fires, and the two currents agree to within
rounding. **Both stated causes were inert.** The real cause was per-angle versus per-operating-point
inductance.

It read as authoritative for two days because it was specific, plausible and written in the right
vocabulary.

**What works:** measure before believing a diagnosis — including one's own, especially when it
sounds right. Scoping estimates were wrong three times this week and a measurement corrected each.

---

## 7. Absence and zero look identical downstream

| Instance | Consequence |
|---|---|
| missing `selected_cap` | Chapter 5 silently dropped ~7 pages; 171 pp read as a complete report |
| missing `semiconductor` payload | the whole of Chapter 7 absent under HTTP 200 |
| an unapproved chapter rendering as an empty card | reads as "designed, and zero" |

**What works:** report the absence explicitly — `available: false` with a `reason`, a gate that
names what is missing, a caption that says "not modelled for this part". Never a default that
looks like a result.

---

## 8. A stale check is worse than no check

The `verify_combined_report` page bound sat at 178-190 while the document was 212 pages, so the
script the docs told you to run printed **OUT OF RANGE on a correct report**. A guard that cries
wolf gets ignored, and the next real regression goes through.

**What works:** when a bound lives in two places, comment each with the other's location; when a
guard fires, either fix the subject or fix the guard the same day.

---

## 9. Shell and numpy traps that have each cost real time

- **Backticks in a bash heredoc are command substitution.** Ate field names out of three docs and
  a commit message. Use the Edit tool or a Python file for anything containing backticks.
- **`\n` in a heredoc** produced unterminated string literals repeatedly. Use `chr(10)` or Edit.
- **`arr or []` on numpy output** raises *"truth value of an array is ambiguous"*. Never use `or`
  as a None-guard on engine output.
- **Unbounded table regex** crosses table boundaries and silently compares cells from the wrong
  table — produced a "200 °C junction temperature" once. Always cut at the next caption.
- **`Table 4.2` is 11 tokens per row, not 10** (`F(D)` wraps). Positional indexing on extracted PDF
  text is a guess unless the row length is asserted.

---

## 10. Crest is not maximum, and per-phase is not system

Distinct quantities that share a unit and get compared by accident:

- `dIL_pp_A` is the ripple **at the line crest**; the cycle maximum is 4.7× larger at 264 Vac
- the recovery band (±3.93 V) is smaller than the bus ripple (±10 V), so the band belongs on the
  **cycle-average**, not the instantaneous trace
- `P_FET_rr` is the **system** total; the engine expression is per channel — a factor of `nch`
- gate drive is in the **loss budget** but not the **thermal path**

**What works:** label the basis wherever the number appears, and publish both when both exist.

---

*Maintained alongside `IMPLEMENTATION_LOG.md`. Add an instance when a defect matches an existing
class; add a class when one does not.*
