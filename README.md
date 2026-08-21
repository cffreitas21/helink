# HELINK

HELINK is an offline desktop application for helicopter flight analysis and preventive maintenance. It imports Garmin G1000H CSV/ZIP files, stores flight information locally, and presents telemetry, alerts, exceedances, route data, and maintenance reports.

This project was developed for private academic use.

## Author

Carlos Fernando Garcia Freitas - 25959@stu.ipbeja.pt

## Main features

- Aircraft fleet management
- Garmin G1000H CSV and ZIP import
- Chronological flight records
- Flight overview with averages and maximum values
- Synchronized telemetry charts and timeline
- CAS alert and exceedance analysis
- Offline flight-route map for Portugal
- PDF maintenance report generation and preview
- SQLite database import and export
- Fully offline operation

## Technology

- Python 3.12
- PySide6
- SQLite
- pandas
- Matplotlib
- Leaflet and Protomaps
- OpenStreetMap data
- PyInstaller for Windows builds

## Project structure

```text
helink/
|-- main.py                     Application entry point
|-- build_exe.bat               Builds a standalone Windows executable
|-- run_windows.bat             Creates the environment and starts the app
|-- requirements.txt            Python dependencies
|-- helink/
|   |-- app.py                  Qt application startup
|   |-- bootstrap.py            Dependency construction and injection
|   |-- controllers/            Application use-case controllers
|   |-- models/                 Domain entities
|   |-- repositories/           SQLite persistence operations
|   |-- services/               Import, reporting, map and database services
|   |-- ui/                     Windows, pages, tabs, dialogs and widgets
|   |-- assets/images           Helink logo and icon
|   `-- assets/map              Offline map resources
```

## Installation

Python 3.12 or newer is recommended.

Open PowerShell in the project directory and run:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If PowerShell prevents activation, the virtual-environment Python can be used directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Running the application

With the virtual environment activated:

```powershell
python main.py
```

Alternatively, double-click:

```text
run_windows.bat
```

## Building the Windows executable

Double-click `build_exe.bat`, or run it from Command Prompt:

```bat
build_exe.bat
```

The script installs PyInstaller and produces one standalone executable:

```text
dist\HELINK.exe
```

The executable includes Python, PySide6, Matplotlib, Qt WebEngine, and the offline map. Because it is a one-file build, the first startup may take longer while bundled resources are extracted to a temporary directory.

## Local database

HELINK uses a persistent SQLite database stored outside the source directory:

```text
C:\Users\<username>\.helink\helink.db
```

The database is created only when it does not already exist. Subsequent application starts reuse the same file.

Database backup and transfer are available through:

```text
File > Import Database
File > Export Database
```

Do not delete `helink.db` unless the stored aircraft and flight records are no longer required.

## Importing flight data

Flight data is added only when files are selected through the application. Files inside `sample_data/` are examples of supported CSV structures and are not imported automatically or used to populate the database.

Supported import formats:

- `.csv`
- `.zip` containing CSV files

## Offline map

The flight-route page works without an internet connection. Its resources are stored in `helink/assets/`:

- `portugal_z12.pmtiles`
- `leaflet.js`
- `leaflet.css`
- `protomaps-leaflet.js`

These files must remain in the project when running from source and are included automatically by `build_exe.bat`.

Map data is attributed to OpenStreetMap contributors and licensed under the Open Database License (ODbL). Map rendering uses Protomaps and the interface uses Leaflet.

## Files not intended for Git

The `.gitignore` excludes generated or local files such as:

- `.venv/`
- `build/`
- `dist/`
- `__pycache__/`
- `*.pyc`
- `*.db`
- `*.spec`

## Application version

HELINK 2026 - v1.0

## Copyright

Copyright © 2026 Carlos Freitas. All rights reserved.

This project was developed as part of the HELINK project.
The source code is publicly available for viewing and portfolio purposes only.

No permission is granted to copy, modify, distribute, sublicense,
or use this software, in whole or in part, without prior written
permission from the author.
