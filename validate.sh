#!/bin/bash
#
#   Simple set of tests for cached qstat command
#
#   Assumes that:
#       - site.cfg has been created (many tests will fail otherwise)
#

# Pretty colors
GCOL="\033[0;32m" BCOL="\033[0;31m" WCOL="\033[0;33m" DCOL="\033[0m"

# Section header
function section {
    echo -e "\n======================================"
    echo " $1"
    echo -e "======================================\n"
}

# Test function
function run_test {
    echo -n "Checking if $1 ... "

    if [[ ${SKIP}z != z ]]; then
        echo -e "${WCOL}SKIP ($SKIP)${DCOL}"
        return
    fi

    eval "$2" >& output; RESULT=$?

    if [[ $RESULT == 0 ]]; then
        echo -e "${GCOL}YES${DCOL}"
    elif [[ $3 == warn ]]; then
        echo -e "${WCOL}NO (ok?)${DCOL}"
    else
        echo -e "${BCOL}NO${DCOL}"
        echo -e "\n    Output: $2"
        echo -e "             $(cat output)\n"
    fi

    rm -f output
}

# ----- site.cfg

section 'RUNNING SITE CONFIG TESTS'

run_test 'site.cfg exists' '[[ -f site.cfg ]]'
source site.cfg 2> /dev/null

# Check if settings are defined
run_test 'DATAPATH is set' '[[ ! -z $DATAPATH ]]'
run_test 'TMPPATH is set' '[[ ! -z $TMPPATH ]]'
run_test 'LOGPATH is set' '[[ ! -z $LOGPATH ]]' warn
run_test 'MAXWAIT is set' '[[ ! -z $MAXWAIT ]]' warn
run_test 'QSTATBIN is set' '[[ ! -z $QSTATBIN ]]'
run_test 'GENFREQ is set' '[[ ! -z $GENFREQ ]]' warn

# ----- gen_data.sh

section 'RUNNING CACHE GENERATION TESTS'

# Run gen_data using current site config
DEBUG_CYCLE=true ./gen_data.sh

run_test 'gen_data.sh runs without error' "[[ $? == 0 ]]"

# Make sure all data files were generated
TESTFILES='joblist-info.dat joblist-wide.dat commlist-info.dat commlist-wide.dat joblist-default.dat joblist-info-nodes.dat joblist-wide-nodes.dat commlist-info-nodes.dat commlist-wide-nodes.dat'

for TF in $TESTFILES; do
    run_test "$TF exists" '[[ -f $DATAPATH/$TF ]]'
done

# ----- qstat

section 'RUNNING CACHED QSTAT TESTS'

run_test 'cached qstat succeeds' './qstat'

export QSCACHE_BYPASS=true

run_test 'PBS qstat succeeds' './qstat'

echo -e "\nTests complete\n"
