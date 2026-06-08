# PFC AI Design Agent — Claude Code Context



## Project Structure

- frontend/src/components/Step7Wizard.tsx

- frontend/src/api/client.ts

- backend/app/main.py

- backend/app/mode\_b/step7\_magnetic\_calc.py

- backend/app/mode\_b/generate\_steps13\_14.py

- backend/app/mode\_b/generate\_combined\_report.py

- backend/app/mode\_b/generate\_report.py



## Key Rules

1\. ALWAYS read the actual file before editing

2\. Make all changes to a file in ONE edit, never multiple patches

3\. client.ts uses BASE not API\_BASE as the URL variable

4\. enrichResult(raw, idx, np, wd) — nPar and winding are explicit params

5\. matKey is local to runSizing — use matType==='powder'?selMaterial:selGrade elsewhere

6\. numpy 2.0: use np.trapezoid() not np.trapz()

7\. Never use unicode subscripts in ReportLab — use sub tags

8\. REPORT COMPLETENESS: When a step's "Approve" button stores a result in App.tsx state,
   that result object MUST carry a complete selected\_xxx block containing all part/config
   data the backend needs to regenerate that step's full report (verified, thermal, etc.).
   The backend enriches step15\_result only when selected\_cap is present and non-empty —
   missing it silently drops sections 15.7+. Same pattern applies to every future step:
   approved result → carries full config → backend can rebuild all sub-sections.
   See CapacitorResult.selected\_cap in Step15Capacitor.tsx as the reference pattern.



## Backend

\- POST /mode-b/generate-full-report — combined Steps 1-14 PDF

\- POST /mode-b/step7/run-sizing — returns top\_5 candidates (up to 15: 5 per stack group)

\- POST /mode-b/step8/time-domain — time domain core loss



## Frontend State (Step7Wizard.tsx)

\- winding: single/bifilar/trifilar — component level state

\- nPar: winding===bifilar?2:winding===trifilar?3:1

\- mountDir: 'horizontal'|'vertical' — mounting orientation, drives installed\_height\_mm

\- selectedCandIdx: index-based candidate selection

\- allCandidates: any\[\] — full top-5×stacks list from backend (up to 15 items)

\- rptLoading: boolean — report generation in-flight state

\- enrichResult(raw, idx, np, wd): enriches backend result for display

### Helper functions (module level)

\- wireKey(w): normalises wire designation (designation ?? wire\_code ?? size ?? dia string)

\- fmtMat(key): formats material key → "Edge · µ=75"; ferrite keys pass through title-cased

\- matMu(key): extracts trailing permeability number from material key ("edge\_75" → "75")



## Backend DesignResult fields (step7\_magnetic\_calc.py)

New fields added beyond the reference document:

\- wound\_HT\_actual\_mm — assembled height: bare core stack + 2 × wire OD

\- wound\_OD\_actual\_mm — assembled OD: core OD + radial build scaled by (FFcu/0.40) from catalog ref

\- mounting — 'horizontal' | 'vertical' (from designer selection)

\- installed\_height\_mm — chassis height for chosen mounting (wound\_HT if horizontal, wound\_OD if vertical)



## rank\_candidates behaviour (step7\_magnetic\_calc.py)

\- Returns n\_top (default 5) candidates PER stack count, descending stack order (3→2→1)

\- Total output: up to n\_top × number\_of\_stack\_counts (e.g. 15 with max\_stacks=3)

\- Per-group labels assigned (first match wins within each group):

  "★ Best overall" (global), "★ Best N-stack", "Smallest N-stack",

  "Lowest loss N-stack", "Lowest ΔT N-stack", "Most economical N-stack"



## PDF Report (generate\_steps13\_14.py)

\- \_mat\_mu(key): extracts trailing permeability number from material key

\- \_sec\_13\_candidates(story, D, S): Step 13.0 candidates table with µ column;

  approved design row highlighted in blue-bold; label notes printed below table

\- all\_candidates passed from frontend in approved\_design payload → resolved in \_resolve\_params
