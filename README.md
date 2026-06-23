# EE-Req Manager — Automotive E/E Architecture Requirements Management

A Streamlit-based web application for managing vehicle **functions**, **CAN signals**, and their **relationships** — built for automotive E/E architects and DRE engineers.

## Features

### Function Management
- CRUD for vehicle functions with domain/ECU categorization
- Priority, status, and ASIL level tracking
- Filter by domain / ECU

### Signal Management
- Full CAN signal definition: message, DLC, bit layout, factor, offset, unit
- Motorola / Intel byte order support
- DBC file import (Vector/CANdb++ format)
- Excel communication matrix parsing (s/r matrix auto-analysis)

### Function-Signal Binding
- Bind signals to functions with direction (Input / Output / Feedback)
- Signal search with auto-complete
- Required/optional flag

### Logic Relations
- 7 relation types: Trigger, Interlock, Linkage, Dependency, Timing, Condition, Data Flow
- Visual **vis.js network graph** (dark theme, drag, zoom, click-detail)
- JSON condition editor with AND/OR/NOT support
- Signal-Function trigger relations
- Auto-generate data-flow relations from signal database

### Traceability Matrix
- Full function↔signal coverage view
- Summary / detail display modes
- CSV export

### Multi-Vehicle Support
- Vehicle project isolation (通用 = base library, project vehicles = independent copies)
- Data borrowing between vehicle projects
- Configurable dropdown lists (ECU, domain, priority, status, ASIL)

### i18n
- Chinese / English language switching in sidebar

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Streamlit |
| Database | SQLite + SQLAlchemy ORM |
| DBC Parsing | cantools |
| Excel Parsing | openpyxl |
| Data Display | Pandas |
| Network Graph | vis.js (vis-network) |

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Launch
streamlit run app.py
```

Open http://localhost:8501 — the app auto-creates `ee_req.db` on first run.

## Project Structure

```
ee-req-manager/
├── app.py          # Streamlit main application
├── db.py           # SQLAlchemy models + DB migration
├── i18n.py         # Internationalization (zh/en)
├── requirements.txt
└── README.md
```

## For International Users

Select **us English** in the sidebar language switcher. All UI labels, titles, and messages switch to English. Sidebar navigation, function/signal management, DBC import, traceability matrix — fully bilingual.

## License

MIT
