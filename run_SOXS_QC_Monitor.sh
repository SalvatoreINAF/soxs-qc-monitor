#!/bin/tcsh

# =========================================================
# SOXS QC Monitor batch execution script
# =========================================================

# ---------------------------------------------------------
# Enter script directory and resolve ROOT
# ---------------------------------------------------------

# !!! If you move the script from the QC root,
# make sure to update the CONFIG path below accordingly.
pushd `dirname $0` > /dev/null
set ROOT=`pwd`

# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

set CONFIG=${ROOT}/configs/qc_monitor.yaml
set LOG_DIR=${ROOT}/logs
setenv QC_MONITOR_ROOT ${ROOT}
set PYTHON_CMD=python

# Make sure the correct python environment is activated before running this script
# and the qc-monitor package is installed in that environment.
# Otherwise set the correct absolute path below to point to the desired python executable.

# Optional custom python executable (same as pipeline)
# set QC_MONITOR=/path/to/conda/env/bin/qc-monitor

set QC_MONITOR=qc-monitor

# ---------------------------------------------------------
# Create log directory
# ---------------------------------------------------------

mkdir -p ${LOG_DIR}

set DATE=`date -u +%Y%m%dT%H%M%SZ`
set LOG_FILE=${LOG_DIR}/qc_monitor_${DATE}.log

# ---------------------------------------------------------
# Start logging
# ---------------------------------------------------------

echo "==================================================" >>& ${LOG_FILE}
echo "SOXS QC Monitor batch execution" >>& ${LOG_FILE}
echo "UTC start time: `date -u +%Y-%m-%dT%H:%M:%SZ`" >>& ${LOG_FILE}
echo "ROOT: ${ROOT}" >>& ${LOG_FILE}
echo "CONFIG: ${CONFIG}" >>& ${LOG_FILE}
echo "QC_MONITOR: ${QC_MONITOR}" >>& ${LOG_FILE}
echo "QC_MONITOR_ROOT: ${QC_MONITOR_ROOT}" >>& ${LOG_FILE}
echo "==================================================" >>& ${LOG_FILE}

# ---------------------------------------------------------
# Environment and configuration checks
# ---------------------------------------------------------

if (! -e ${CONFIG}) then
    echo "ERROR: configuration file not found: ${CONFIG}" >>& ${LOG_FILE}
    popd > /dev/null
    exit 2
endif

which ${QC_MONITOR} >>& ${LOG_FILE}
if ($status != 0) then
    echo "ERROR: qc-monitor command not found: ${QC_MONITOR}" >>& ${LOG_FILE}
    popd > /dev/null
    exit 2
endif

which ${PYTHON_CMD} >>& ${LOG_FILE}
if ($status != 0) then
    set PYTHON_CMD=python3
    which ${PYTHON_CMD} >>& ${LOG_FILE}
    if ($status != 0) then
        echo "ERROR: neither python nor python3 was found in PATH" >>& ${LOG_FILE}
        popd > /dev/null
        exit 2
    endif
endif

echo "" >>& ${LOG_FILE}
echo "Python version:" >>& ${LOG_FILE}
${PYTHON_CMD} --version >>& ${LOG_FILE}

echo "" >>& ${LOG_FILE}
echo "Package versions:" >>& ${LOG_FILE}
${PYTHON_CMD} -c "import qc_monitor; print('qc_monitor', qc_monitor.__version__)" >>& ${LOG_FILE}
${PYTHON_CMD} -c "import soxspipe; print('soxspipe', getattr(soxspipe, '__version__', 'unknown'))" >>& ${LOG_FILE}

# ---------------------------------------------------------
# Preflight checks
# ---------------------------------------------------------

echo "" >>& ${LOG_FILE}
echo "Running QC Monitor preflight" >>& ${LOG_FILE}

${QC_MONITOR} \
    --config ${CONFIG} \
    --preflight \
    --verbose \
    >>& ${LOG_FILE}

set EXIT_CODE=$status

if (${EXIT_CODE} != 0) then
    echo "" >>& ${LOG_FILE}
    echo "ERROR: QC Monitor preflight failed" >>& ${LOG_FILE}
    echo "Exit code: ${EXIT_CODE}" >>& ${LOG_FILE}
    popd > /dev/null
    exit ${EXIT_CODE}
endif

# ---------------------------------------------------------
# Execute QC monitor
# ---------------------------------------------------------

${QC_MONITOR} \
    --config ${CONFIG} \
    --verbose \
    >>& ${LOG_FILE}

set EXIT_CODE=$status

# ---------------------------------------------------------
# Web publication step
# ---------------------------------------------------------
#
# The QC monitor produces a static HTML page and PNG plots.
# Publication to the web area is intentionally left disabled
# in this first release.
#
# set WEB_USER="user"
# set WEB_PASSWORD="password"
# set WEB_URL="https://webserver.example.org/upload"
#
# Upload HTML page
#
# curl -k \
#      --fail \
#      --silent \
#      --show-error \
#      -u ${WEB_USER}:${WEB_PASSWORD} \
#      -F "file=@${ROOT}/index.html" \
#      ${WEB_URL} \
#      >>& ${LOG_FILE}
#
# if ($status != 0) then
#     echo "ERROR: failed to upload index.html" >>& ${LOG_FILE}
#     set EXIT_CODE=1
# endif
#
# Upload PNG plots
#
# foreach PNG (${ROOT}/plots/*.png)
#
#     curl -k \
#          --fail \
#          --silent \
#          --show-error \
#          -u ${WEB_USER}:${WEB_PASSWORD} \
#          -F "file=@${PNG}" \
#          ${WEB_URL} \
#          >>& ${LOG_FILE}
#
#     if ($status != 0) then
#         echo "ERROR: failed to upload ${PNG}" >>& ${LOG_FILE}
#         set EXIT_CODE=1
#     endif
#
# end
#
# ---------------------------------------------------------

# Restore original directory
popd > /dev/null

# ---------------------------------------------------------
# Log final status
# ---------------------------------------------------------

if (${EXIT_CODE} != 0) then

    echo "" >>& ${LOG_FILE}
    echo "ERROR: QC Monitor execution failed" >>& ${LOG_FILE}
    echo "UTC end time: `date -u +%Y-%m-%dT%H:%M:%SZ`" >>& ${LOG_FILE}
    echo "Exit code: ${EXIT_CODE}" >>& ${LOG_FILE}
    echo "==================================================" >>& ${LOG_FILE}

    exit ${EXIT_CODE}

endif

echo "" >>& ${LOG_FILE}
echo "QC Monitor completed successfully" >>& ${LOG_FILE}
echo "UTC end time: `date -u +%Y-%m-%dT%H:%M:%SZ`" >>& ${LOG_FILE}
echo "==================================================" >>& ${LOG_FILE}

exit 0
