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
echo "==================================================" >>& ${LOG_FILE}

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