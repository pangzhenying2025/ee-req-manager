# Working on EE-Req Manager

## Start here

- Run `git status --short --branch`; preserve unrelated changes.
- Read `docs/development.md` for the development loop and commands.
- Production runs via `启动.bat`. Development runs via `开发.bat` with `.dev/demo.db`.
- Do not use customer data as test fixtures, commit databases, or rewrite approved/baselined objects silently.

## Boundaries

- `app.py`: legacy pages and routing. Put new workspaces in `workspaces/` and reusable logic in `services/`.
- `services/signal_endpoints.py`: project-scoped endpoint changes and audit history.
- `signal_flow.py`: Streamlit component adapter. Existing imports are maintained for compatibility.
- `services/traceability.py`: pure trace-tree calculation.
- `services/requirement_policy.py`: requirement levels, labels and audit text.
- `services/dbc_import.py`: DBC parsing. No Streamlit imports.
- `signal_flow_component/src/`: React Flow source; `dist/` is the shipped build.

## Engineering invariants

- Queries and mutations must be scoped to `project_id`.
- Keep SQLite foreign keys, original DBC provenance and field-level audit records.
- One signal can have several active receiving ECU endpoints.
- Schema migrations require named column mapping, backup and a disposable migration test.
- Keep all graph editing paths consistent with edit ownership checks.

## Checks

- Python: `.venv\Scripts\python.exe scripts/dev.py check`
- Frontend changes: add `--frontend`; browser-visible changes: add `--ui`.
- For new business operations, test actual invariants rather than implementation details.
- Rebuild `dist/` for release when canvas source changes. Node.js is not required to run the shipped app.
- Never claim CI or a live-browser result passed unless it was run.
