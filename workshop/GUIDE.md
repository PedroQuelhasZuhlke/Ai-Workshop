# AI Workshop Guide

You are working on **PCB Parts Picking**, an internal tool that turns a PCB bill of materials (BOM) into purchase plans and supplier import files. Backend: Python (FastAPI). Frontend: React + TypeScript.

You do not need to know Python. The point of this workshop is to use your AI assistant to read, understand and change code you did not write.

## Rules

1. Use the AI for everything: finding the problem, understanding it, fixing it.
2. Describe the symptom to the AI the way it is written below. Do not go hunting through files yourself first.
3. Ask the AI to explain any change before you accept it. If you cannot say in one sentence what a change does, ask again.
4. Do not edit tests to make them pass. The tests are the spec.
5. Keep a note of your best prompt for each challenge. We compare them at the end.

## Setup

```powershell
uv sync
cd web; npm install; cd ..
./scripts/start-dev.ps1        # backend + frontend, opens on http://localhost:5173
```

Sample BOM for the UI challenges: `demo/boms/mock_suppliers_demo.csv`.
Run any test with `uv run pytest <path>`. Do not run the whole suite and try to fix everything; each challenge names its own tests.

## Challenges

Start with 1 and 2. Then pick any two more. 5 and 6 are the hardest.

### 1. Projects do not show up

Register or log in, type a project name and click **Create project**. The create call works, but the project never appears in the list.

**Done when:** a new project appears in the list.

**Check:** `uv run pytest tests/api/test_project_deletion.py tests/api/test_key_recovery.py`

### 2. Blank page after finding candidates

Upload `demo/boms/mock_suppliers_demo.csv`, confirm the mapping, resolve requirements, then click to find candidates. The page goes completely white instead of showing the candidate review table.

**Done when:** the candidate review step renders with the table and a board-quantity box, and the warning about the offline catalog is still shown.
**Check:** reload the page and walk the demo BOM through to the candidate step. The browser console is your friend; ask the AI what to do with it.

### 3. Missing reference designators

A BOM line lists its parts as a range, for example `R1-R4`. Upload `demo/boms/mock_suppliers_demo.csv`, confirm the mapping, and look at the Refdes column in the **Resolve requirements** step. The `R1-R4` line shows only `R1, R2, R3` and the `C1-C2` line shows only `C1`. The last part of every range is dropped.

**Done when:** every range expands to include both of its ends, and the Refdes column shows `R1, R2, R3, R4` and `C1, C2`.
**Check:** `uv run pytest tests/stages/test_ingest.py`, then re-upload the demo BOM and look at the Refdes column.

### 4. Add "Rename project"

The projects list has **Delete** but no way to rename a project. Add it, end to end: an owner-only API endpoint and a Rename control on the Projects page. Follow how Delete is built.

**Done when:** the API tests pass and you can rename a project in the browser.
**Check:** `uv run pytest tests/api/test_project_rename.py`, then try it in the UI.

### 5. Farnell export is missing

Approve a plan and export it for Mouser or DigiKey: fine. Export for Farnell fails. Someone removed the Farnell export format. Rebuild it so it behaves like the other suppliers, using the tests as the specification.

**Done when:** Farnell exports work in CSV and XLSX.
**Check:** `uv run pytest tests/stages/test_exporters.py`

### 6. One user can read another user's data

Two users, Alice and Mallory. Alice has a project with a run. Mallory has her own, separate project. If Mallory takes Alice's run id and puts it behind **her own** project id in a URL, some data comes back instead of "not found". This must never happen.

**Done when:** every read for a run through the wrong project returns 404.
**Check:** `uv run pytest tests/api/test_cross_project_reads.py`

## Stuck?

Try these in order. Only open the next one if the previous one did not help.

<details>
<summary>Hint 1: where to look</summary>

1. The backend project routes.
2. The candidate review screen in the React run page.
3. The code that reads reference designators from a BOM.
4. The new endpoint goes next to the existing project routes; the UI goes on the Projects page.
5. The export code and its templates.
6. The run routes in the backend API.

</details>

<details>
<summary>Hint 2: a prompt to try</summary>

Paste the symptom, the check command and its failing output into your AI chat and ask: "Find the cause. Explain it before changing anything."

For 2: also paste the browser console error.
For 5: ask it to compare the Mouser and DigiKey export code and tell you what Farnell is missing.
For 6: ask it to compare how each run route checks that the run belongs to the project.

</details>

<details>
<summary>Hint 3: what the problem is</summary>

1. A condition is the wrong way round.
2. Something is assumed to always have a value, and sometimes does not.
3. A loop stops one item too early.
4. Mirror the Delete flow: schema, route, client call, button.
5. There is no Farnell column list and no Farnell row mapping.
6. Two read routes skip the check that the run belongs to the project in the URL.

</details>

## Stretch

Finished early? Ask your AI to review the whole repository for places where a number is calculated with the wrong type, or where an access check is missing. Check whether what it finds is real before you act on it.
