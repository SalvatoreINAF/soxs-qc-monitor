"""Read-only diagnostics, except for an explicit SQLite backup destination."""
import os
import re
import sqlite3
import sys
from pathlib import Path

import yaml

repo = Path(os.environ["REPO"])
session = Path(os.environ["SESSION"])
with Path(os.environ["CONFIG"]).open() as stream:
    cfg = yaml.safe_load(stream)


def path(value):
    value = Path(value).expanduser()
    return (value if value.is_absolute() else repo / value).resolve()


def connect(db):
    return sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)


def backup():
    db = path(cfg["paths"]["qc_database"])
    print("QC database:", db)
    if db.exists():
        source = connect(db)
        destination = sqlite3.connect(session / "qc.sqlite")
        try:
            source.backup(destination)
            result = destination.execute("PRAGMA integrity_check").fetchall()
            if result != [("ok",)]:
                raise RuntimeError(f"Backup integrity check failed: {result}")
        finally:
            destination.close()
            source.close()
        print("SQLite backup verified.")
    else:
        print("QC archive missing; the monitor will create a new one.")


def inputs():
    from qc_monitor.acquisition import find_dispersion_solution_fits_files
    root = path(cfg["paths"]["reduced_root"])
    mode = cfg.get("acquisition", {}).get("reduced_products_search", "observing_day_dirs")
    found = find_dispersion_solution_fits_files(root, mode)
    print("Products root:", root)
    print("Dispersion FITS files discovered:", len(found))
    if not found:
        print("WARNING: no new dispersion data will be acquired.")
        sibling = root.parent / "qc"
        if sibling.is_dir():
            examples = list(sibling.rglob("*DSOL_PINHOLE*SOXS_FITTED_LINES.fits"))
            print("FITS files in the adjacent qc directory:", len(examples))
            for item in examples[:5]:
                print(item)
        print("Check the paths; rebuilding does not fix undiscovered files.")


def verify():
    issues = []
    db = path(cfg["paths"]["qc_database"])
    connection = connect(db)
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchall()
        print("SQLite integrity:", integrity)
        if integrity != [("ok",)]:
            issues.append("SQLite integrity check failed")
        tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        for (table,) in tables:
            quoted = '"' + table.replace('"', '""') + '"'
            count = connection.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0]
            print(f"{table}: {count} rows")
            if table == "dispersion_solution_lines" and count == 0:
                issues.append("Dispersion archive empty: check whether this is expected for this dataset")
    finally:
        connection.close()
    report = path(cfg["plots"]["html_output"])
    plots = path(cfg["plots"]["output_dir"])
    print("Report:", report)
    print("PNG plots:", len(list(plots.glob("*.png"))))
    if not report.is_file() or report.stat().st_size == 0:
        issues.append("Report missing or empty")
    if not any(plots.glob("*.png")):
        issues.append("No PNG plots found")
    lines = (session / "run.log").read_text(errors="replace").splitlines()
    for line in lines:
        if re.search(r"ERROR|CRITICAL|Traceback|remains open|acquisition failed", line):
            issues.append(line)
        elif "WARNING" in line:
            print(line)
    if issues:
        print("\nREVIEW REQUIRED:")
        for issue in issues:
            print(issue)
        raise SystemExit(1)
    print("Checks passed; visual inspection of the report is still required.")


if __name__ == "__main__":
    actions = {"backup": backup, "inputs": inputs, "verify": verify}
    if len(sys.argv) != 2 or sys.argv[1] not in actions:
        raise SystemExit("Usage: diagnostics.py backup|inputs|verify")
    actions[sys.argv[1]]()
