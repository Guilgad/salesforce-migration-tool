# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project state

This is a greenfield Python project in the **planning phase**. No source code, `requirements.txt`, or folder structure exists yet. The planning effort was **restarted** — the original planning docs are archived under `planning/_ארכיון/` (`תוכנית פיתוח.md`, `פרומפט ראשוני.md`) as reference only, and a fresh plan is being written into `planning/`. Do not start writing implementation code until the new plan has been agreed with the user. See "Pre-coding workflow" below.

Planning docs live in `planning/` (Obsidian notes); settings notes live in `Settings/`. Project planning documents are written in Hebrew. The user is new to this domain and treats the plan as a starting point, not a fixed spec — questions and pushback are wanted.

## Git workflow (agreed with user)

Commit at **logical milestones** — each module or fix that has passed the user's review — **never on a timer**. At each such checkpoint, **proactively propose** the commit ("we finished X, worth committing — approve?") and commit only after the user says yes. Do not auto-commit silently, and do not commit mid-work. Pushing stays manual / on request.

## What the tool does

A generic Python utility that turns a customer's raw data (Google Sheets) into Salesforce-ready load sheets, with dedup and insert/upsert decisions baked in. Key design constraints:

- **No direct Salesforce connection.** Everything flows through files. Salesforce data comes in via exports (Google Sheets), and the tool's output is a Google Sheet the user loads manually via Salesforce Inspector.
- **Google Sheets is the only I/O surface.** Inputs and outputs are all Sheets, accessed via the Sheets API with a service account.
- **Generic and modular.** The tool must not assume any specific customer schema; column-to-field mapping is data-driven via a "migration map" sheet the user fills in.

## Architecture (planned)

Five inputs feed a pipeline that produces one output Sheet with multiple tabs:

**Inputs**
1. Customer raw data Sheet (free-form, possibly multi-tab)
2. Salesforce environment-structure Sheet — produced by running a generated SOQL query against `FieldDefinition` in Salesforce Inspector and saving the result
3. Migration-map Sheet — user-authored: defines column→API-name mapping, which columns form the unique key, and load order/dependencies
4. Per-object Salesforce export Sheets (existing records, used for upsert-vs-insert decisions)
5. Existing-relationships export Sheet

**Pipeline stages**
- **Step 0 (SOQL builder):** user types object API names into a cell; the tool emits a `SELECT EntityDefinition.Label, EntityDefinition.QualifiedApiName, Label, QualifiedApiName, DataType FROM FieldDefinition WHERE EntityDefinition.QualifiedApiName IN (...)` query. The user runs it in Inspector and re-imports the result as input #2.
- **Dedup engine:** unique key is configurable per object — single column OR a composite (e.g., name + phone + DOB). Runs twice: (a) internal dedup within the input, (b) comparison against the Salesforce export → match means upsert (carry the existing Id), no match means insert.
- **Relationship handler:** uniqueness is symmetric — `A↔B` and `B↔A` are the same edge. Output excludes relationships that already exist in the relationships export.
- **Output writer:** one tab per load, in dependency order. Every output tab includes these meta columns: `__Action` (Insert/Upsert), `__Id` (empty for insert, filled for upsert), `__Status`, `__Errors`.

**Planned module layout** (from the plan doc — subject to revision):

```
main.py
config/settings.py
modules/
  sheets_reader.py         # Google Sheets read
  sheets_writer.py         # Google Sheets write
  soql_builder.py          # Step 0 SOQL generation
  dedup_engine.py          # internal + cross-source dedup
  mapper.py                # column → SF API name mapping
  relationship_handler.py  # bidirectional edge dedup
templates/migration_map_template.xlsx
requirements.txt
```

## Google credentials

- `credentials.json` is a Google Cloud service-account key for project `sheets-automation-497917`. **It must never be committed.** Add to `.gitignore` before the first commit.
- Service-account email: `python-worker@sheets-automation-497917.iam.gserviceaccount.com` (see `Settings/Google Service Account.md`). Every Sheet the tool needs to read or write must be shared with this address as **Editor**. Mention this to the user any time a new Sheet is introduced — it's the most common foot-gun.
- Sheets API is already enabled on the GCP project.

## Pre-coding workflow (per user's initial brief)

The user's instructions in `planning/_ארכיון/פרומפט ראשוני.md` are explicit and override the default "start coding" instinct:

1. Read the archived plan `planning/_ארכיון/תוכנית פיתוח.md` for context (it is being superseded, not followed verbatim).
2. Enter plan mode.
3. Propose improvements, ask questions, flag anything unclear or worth changing — the user expects pushback, not compliance.
4. Create the planned folder structure plus a `.gitignore` (with `credentials.json` excluded) only after alignment.
5. **Do not write implementation code before the final plan is agreed.**

## Open questions noted in the plan

These are flagged by the user as undecided — surface them when relevant:
- Exact schema of the migration-map Sheet
- Error handling and logging strategy
- Whether to support multiple input sheets in parallel (one customer with several source tables)
