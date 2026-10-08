#!/bin/tcsh
# Stop the scheduler and preserve the previous environment before updating.
# See docs/operations.md for staged updates and restoration.
set ROOT = "$0:h"
if (! $?QC_PYTHON) then
    setenv QC_PYTHON python
endif
"$QC_PYTHON" "${ROOT}/scripts/batch.py" update --root "$ROOT"
set EXIT_CODE=$status
exit $EXIT_CODE
