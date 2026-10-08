#!/bin/tcsh
# Activate the scientific environment first, or set QC_PYTHON to its interpreter.
set ROOT = "$0:h"
if (! $?QC_PYTHON) then
    setenv QC_PYTHON python
endif
"$QC_PYTHON" "${ROOT}/scripts/batch.py" run --root "$ROOT"
set EXIT_CODE=$status
exit $EXIT_CODE
