# Schema definitions for the QC monitoring database

# Excpected schema for the Pipelinen QC database table
TABLE_SCHEMA = {
    "night start date": "TEXT NOT NULL",
    "obs_date_utc": "TEXT NOT NULL",
    "eso seq arm": "TEXT NOT NULL",
    "soxspipe_recipe": "TEXT NOT NULL",
    "qc_name": "TEXT NOT NULL",
    "qc_value": "REAL NOT NULL",
    "qc_order": "TEXT NOT NULL DEFAULT '-1'",
    "qc_unit": "TEXT",
    "qc_flag": "TEXT",
    "qc_value_min": "REAL",
    "qc_value_max": "REAL",
    "sof_name": "TEXT",
    "file": "TEXT",
    "status": "TEXT",
    "binning": "TEXT",
    "rospeed": "TEXT",
    "slit": "TEXT",
    "slitmask": "TEXT",
    "lamp": "TEXT",
    "exptime": "REAL",
    "template": "TEXT",
    "object": "TEXT",
    "filepath": "TEXT",
}


# Columns that uniquely identify a QC metric in the upstream database
UNIQUE_COLUMNS = [
    "obs_date_utc",
    "soxspipe_recipe",
    "qc_name",
    "eso seq arm",
    "qc_order",
    "file",
]