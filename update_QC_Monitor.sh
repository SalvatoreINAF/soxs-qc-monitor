#!/bin/tcsh

# =========================================================
# SOXS QC Monitor update script
# =========================================================

pushd `dirname $0` > /dev/null
set ROOT=`pwd`
setenv QC_MONITOR_ROOT ${ROOT}

set CONFIG=${ROOT}/configs/qc_monitor.yaml
set LOG_DIR=${ROOT}/logs
set QC_MONITOR=qc-monitor

mkdir -p ${LOG_DIR}

set DATE=`date -u +%Y%m%dT%H%M%SZ`
set LOG_FILE=${LOG_DIR}/qc_monitor_update_${DATE}.log
set CONFIG_BACKUP=${CONFIG}.${DATE}.bak

echo "==================================================" >>& ${LOG_FILE}
echo "SOXS QC Monitor update" >>& ${LOG_FILE}
echo "UTC start time: `date -u +%Y-%m-%dT%H:%M:%SZ`" >>& ${LOG_FILE}
echo "ROOT: ${ROOT}" >>& ${LOG_FILE}
echo "CONFIG: ${CONFIG}" >>& ${LOG_FILE}
echo "QC_MONITOR_ROOT: ${QC_MONITOR_ROOT}" >>& ${LOG_FILE}
echo "==================================================" >>& ${LOG_FILE}

if (! -e ${CONFIG}) then
    echo "ERROR: configuration file not found: ${CONFIG}" >>& ${LOG_FILE}
    popd > /dev/null
    exit 2
endif

cp ${CONFIG} ${CONFIG_BACKUP} >>& ${LOG_FILE}
if ($status != 0) then
    echo "ERROR: failed to back up configuration to ${CONFIG_BACKUP}" >>& ${LOG_FILE}
    popd > /dev/null
    exit 2
endif

echo "Backed up configuration to ${CONFIG_BACKUP}" >>& ${LOG_FILE}

echo "" >>& ${LOG_FILE}
echo "Updating git repository" >>& ${LOG_FILE}
git pull --ff-only >>& ${LOG_FILE}
set EXIT_CODE=$status

if (${EXIT_CODE} != 0) then
    echo "ERROR: git pull failed" >>& ${LOG_FILE}
    popd > /dev/null
    exit ${EXIT_CODE}
endif

echo "" >>& ${LOG_FILE}
echo "Installing QC Monitor package" >>& ${LOG_FILE}
pip install . >>& ${LOG_FILE}
set EXIT_CODE=$status

if (${EXIT_CODE} != 0) then
    echo "ERROR: pip install failed" >>& ${LOG_FILE}
    popd > /dev/null
    exit ${EXIT_CODE}
endif

echo "" >>& ${LOG_FILE}
echo "Running preflight after update" >>& ${LOG_FILE}
${QC_MONITOR} --config ${CONFIG} --preflight --verbose >>& ${LOG_FILE}
set EXIT_CODE=$status

if (${EXIT_CODE} != 0) then
    echo "ERROR: post-update preflight failed" >>& ${LOG_FILE}
    popd > /dev/null
    exit ${EXIT_CODE}
endif

echo "" >>& ${LOG_FILE}
echo "Running dry-run after update" >>& ${LOG_FILE}
${QC_MONITOR} --config ${CONFIG} --dry-run --verbose >>& ${LOG_FILE}
set EXIT_CODE=$status

if (${EXIT_CODE} != 0) then
    echo "ERROR: post-update dry-run failed" >>& ${LOG_FILE}
    popd > /dev/null
    exit ${EXIT_CODE}
endif

echo "" >>& ${LOG_FILE}
echo "QC Monitor update completed successfully" >>& ${LOG_FILE}
echo "UTC end time: `date -u +%Y-%m-%dT%H:%M:%SZ`" >>& ${LOG_FILE}
echo "==================================================" >>& ${LOG_FILE}

popd > /dev/null
exit 0
