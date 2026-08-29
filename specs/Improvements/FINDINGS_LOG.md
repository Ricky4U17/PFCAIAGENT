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

## 1b. A test that asks "did it MOVE?" never asks "is it RIGHT?"

C268. Section 6.4 printed a fabricated oscillator equation — `f_SW = 1.2e9/(R_RI + 3430)`, a form
present in none of the four reference PDFs in the repo — and specified 13.7 kΩ for a 70 kHz design.
That resistor runs the part at 58.4 kHz. It survived because:

- **The guard was anchored on the wrong formula's own artefacts.** `test_the_r_ri_worked_equation_
  tracks_the_switching_frequency` searched for `"3430"` and the `17.143 k` intermediate. It built
  twice, at 70 and 60 kHz, and correctly proved the number was live rather than hardcoded — which
  is all it was ever asked. A tracking test written against a wrong equation **pins the wrong
  equation in place**, and reads as a passing check on that section forever.
- **Internal consistency cannot see it.** `fsw_at_selected` is display-only; every downstream
  chapter used the *target* f_SW. The design was perfectly self-consistent at 70 kHz, and only the
  BOM resistor was wrong. No cross-check inside the repo could have caught it.
- **The capture covered three of four text sinks.** `_capture` patched `eq_box` and `body` but not
  `annotation` — and the hardcoded `"Use R_RI = 13.7 kΩ"` DECISION line lived in `annotation`. A
  harness that covers most sinks silently exempts the rest, and the exempt one is invisible.

**What works:** check the equation against the *source*, not against itself. The datasheet gave two
electrical-table test cases (25 kΩ → 32 kHz, 12.5 kΩ → 62 kHz) and AN4165-D a worked example
(40 kHz at 20 kΩ). The correct form reproduces all three exactly; the fabricated one missed all
three and mapped the datasheet's own 10.7 kΩ minimum past the part's 75 kHz ceiling. Any of these
would have caught it on day one. When a value comes from a vendor document, the test anchor belongs
in that document.

**Corollary — scaling pairs must move together.** R_RI also sets `I_ILIMIT`, and the clamp
threshold depends on the RATIO `R_ILIMIT/R_RI`. The wrong pair was internally consistent at 1.81×;
correcting R_RI alone would have pushed the realised clamp to 2.16×, outside its window, silently,
with both numbers still looking plausible.

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

## 4b. A persisted choice outlives the calculation that justified it

C269. Screen 2 offered **100 pF** for C_ILIMIT2 where the engine said 91 nF — and the engine had
been right the whole time. 100 pF is the FIRST entry in the options list, which is the signature:

> **A `<select>` whose `value` matches no `<option>` displays its first option**, while state still
> holds the unmatched value. The screen and the state disagree, and neither is flagged.

That is why picking a valid value by hand appeared to "fix the calculation" — it did not fix a
number, it gave the widget something it could match. **Treat "the displayed value is suspiciously
the first option in the list" as a matching failure, never as a bad calculation.**

The unmatched value arrived through **persistence**: selections rehydrate from stored params, and
defaults were applied only when there was no stored selection *at all*, so a stale, zero or absent
stored value survived unchecked. C268 had just moved R_ILIMIT2 (4.87 k → 3.65 k), which invalidated
every previously stored companion capacitor — the stored value was fine when written and wrong
afterwards, and nothing re-examined it.

This is C242's defect through a new door. C242 was an E6 options subset that left four selects
unmatched; the fix widened the grid. The class returned through persistence instead. **So guard the
invariant, not the value that was wrong:** every default must be one of its own offered options,
plus a negative control that fails if all defaults collapse to the first option.

**The general question:** when an upstream number changes, what stored downstream choices does it
invalidate — and does anything recheck them, or do they just persist looking plausible?

**C270 follow-up — the C269 fix above did not work, and the reason is instructive.** It tested
MEMBERSHIP: reset anything that is not an offered option. But 100 pF *is* an offered option — the
first one — so the stale value passed and survived. The invariant I asserted was **true**, and it
still did not cover the case, because the failure was not the one the invariant described. A
capacitor sits at a pole the engine chose, so the right test is physical: a stored value more than
a **decade** from the engine's is debris, not a preference. **Being right about an invariant is not
the same as having chosen the invariant that matches the defect.**

---

## 4c. The quantity that is DERIVED tracks the design; the one that is PASSED goes stale

C270. Screen 2 computed the ILIMIT thresholds from the reference-design peak currents (16.76 /
17.51 A) while the report used the designer's real ones (24.37 / 22.80 A), because
`_control_corner_currents` was called on the report path and not on the GUI path. R_ILIMIT was
**correct** and R_ILIMIT2 **wrong** in the same table — because R_ILIMIT's crest command is derived
from power, which was passed, while the peaks arrive as direct inputs and silently kept their
defaults. One right number beside one wrong one is what made the screen credible.

**The tell was internal physics, needing no reference value at all:** the engine reported a
per-phase *peak* of 17.51 A beside a command *crest* of 18.29 A. The peak carries half the ripple
on top of the crest and cannot be the smaller of the two. That inequality is now a test — no
fixture, no vendor document, no golden number, and it fails the instant a default is used against a
real design.

**Ask of any defaulted input:** if this silently kept its default, would anything downstream
contradict it? Prefer the contradiction that is internal — those guards never go stale.

**C270 round 2 — a parity test that controls its own inputs tests nothing.** Fixing the *call* was
not enough: Screen 2 still said 4.12 kΩ against the report's 3.83 kΩ, because the two paths were
handed **different data**. The parity test I had just written ran both paths with *identical*
inputs and asserted they agreed — and they always did. It could never have failed on the actual
defect.

> If a parity test constructs the inputs for both sides, it is comparing two calls to the same
> function. Real parity means each side fetching its inputs the way it does in production.

Replaced with a **wiring** test: change a field, and the answer must move. A field that is accepted
and ignored is the same defect one layer down.

**And a two-variable interaction beat single-variable testing.** I reported that `vin_min` alone
explained the gap — from a one-variable sweep. It did not: raising `vin_min` *also* makes the engine
re-pick R_CS (12 → 13 mΩ), and the two effects cancel back to the original answer. Only holding
R_CS *and* passing the line limit reproduces the report. **When two inputs both feed the result,
sweeping one at a time can show "no effect" for something that matters.**

Note also that this predated C268/C269 and became visible only when C269 first put R_ILIMIT2 on a
screen. **Displaying a computed value is itself a test**: numbers nobody looks at are where wrong
ones live.

---

## 4d. "Not found" that returns something else instead

C271. `/step7/run-sizing` resolves the chosen wire by designation, and on no match it does not
raise — it takes `wire_opts[0]`, the largest wire in the list:

```python
wire = next((w for w in wire_opts if w["designation"] == req.wire_designation), None)
if wire is None and wire_opts:
    wire = wire_opts[0]        # no error, no warning
```

This turned a routine data cleanup into a trap. Collapsing the duplicate vendor rows (TRW
`0.1x200`, Rupalit `VS0.1x200`, Pack `200x0.1` are one wire) would have stranded any design saved
against a vendor code — and instead of failing, the sizing run would have **quietly rewound it onto
a different wire**. The fix keeps every vendor name resolvable, and the test aims at the
substitution rather than at the lookup.

**Before removing or renaming any catalog entry, find out what happens to a saved reference to it.**
If the answer is a fallback rather than an error, the cleanup is a silent data change.

**C272 closed it — and the fix was not the one-liner it looked like.** Deleting the fallback would
have broken two legitimate callers sharing that branch: `wire_designation: None` (the documented
auto-pick), and any wire the *picker* offers but the *sweep* filters out — the picker lists the
catalog at `min_cu_fraction=0` while the sweep filters at 0.10, so four wires at 20 A are visible,
clickable, and absent from the sweep. A blunt raise would have 400'd on a legitimate pick, which is
just a different way of not doing what was asked.

> **Before removing a fallback, enumerate who is relying on it.** A fallback that is wrong for one
> caller is often load-bearing for another, and "make it strict" usually means *three* behaviours,
> not two.

Related, from the same finding: **the obvious dedupe key is usually wrong.** Cu area and OD look
like they identify a wire; `0.1x800` and `0.2x200` share *both* (3.33 mm, 6.2832 mm²) and are
different wires. The real key was (strands, strand diameter, OD) — the last term only there to keep
dual-bundle constructions apart. Assert the things that must *not* merge, not just the ones that
must.

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
  a commit message — and then, at C267, ate every backticked identifier out of the changelog entry
  that was *documenting this list*, leaving prose full of holes and a cheerful "logged" on stdout.
  Five occurrences. Use the Edit tool or a Python file written via Write for anything containing
  backticks; never pass prose through a shell string. Note the failure is SILENT in the exit code:
  the script reported success because the substitutions merely produced empty strings.
- **Probe Vite on `localhost:5173`, never `127.0.0.1:5173`.** Vite binds IPv6 loopback (`::1`)
  only, so a `127.0.0.1` curl returns connection-refused against a perfectly healthy dev server.
  Cost one restart hunt at C267 — and a false "the frontend is down" is worse than no check, since
  the reflex it triggers is to restart something that was working. Uvicorn binds `127.0.0.1`, so
  the backend is reachable either way. `Get-NetTCPConnection` shows the true binding. A behaviour
  check aimed at the wrong address is not a behaviour check.
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
