#!/bin/bash

# Read in site-config (make edits in that file)
SECONDS=0 DATAPATH= TMPPATH= QSTATBIN= GENFREQ=60
MYPATH="$( cd "$(dirname "$0")" ; pwd )"

if [[ ! -e $MYPATH/${QSCACHE_CONFIG:=site.cfg} ]]; then
    echo "Fatal: No site config found for qstat-cache. ($(date))" >> $MYPATH/error.log
    exit 1
else
    source $MYPATH/$QSCACHE_CONFIG

    if [[ ! -d $TMPPATH ]]; then
        echo "Fatal: temporary storage path does not exist. ($(date))" >> $MYPATH/error.log
        exit 2
    fi

    if [[ ! -f $QSTATBIN ]]; then
        echo "Fatal: real qstat binary not found. ($(date))" >> $MYPATH/error.log
        exit 3
    fi
fi

cd $TMPPATH
TMPPATH=$TMPPATH/qscache-$$

function main_gen {
    # Don't run if already running
    if [[ -f qscache-pcpid ]]; then
        # If a minute has passed, end previous cycle
        TELAP=$(($(date +%s) - $(date +%s -r qscache-pcpid)))

        if [[ $TELAP -gt 60 ]]; then
            PCPID=$(cat qscache-pcpid >& /dev/null)
            
            if kill -0 $PCPID 2> /dev/null; then
                kill $PCPID
            fi

            rm -rf qscache-pcpid $TMPPATH/qscache-$PCPID
        fi

        exit
    fi

    echo $$ > qscache-pcpid
    mkdir -p $TMPPATH $DATAPATH
    cd $TMPPATH

    # Get data from PBS
    $PBSPREFIX $QSTATBIN -a -1 -n -s -w -x | sed '/^[0-9]/,$!d' > newlist-wide.dat &
    $PBSPREFIX $QSTATBIN -1 -n -s -x | sed '/^[0-9]/,$!d' > newlist-info.dat &
    $PBSPREFIX $QSTATBIN -x | sed '/^[0-9]/,$!d' > newlist-default.dat &

    wait

    # Poor-man's sync
    mv newlist-wide.dat commlist-wide-nodes.dat
    mv newlist-info.dat commlist-info-nodes.dat
    mv newlist-default.dat joblist-default.dat

    # Get versions without admin comment
    grep -v '^ ' commlist-wide-nodes.dat > joblist-wide-nodes.dat &
    grep -v '^ ' commlist-info-nodes.dat > joblist-info-nodes.dat &

    wait

    # Get versions without nodelist
    sed 's|^\([0-9].*\) [^ ].*|\1|' commlist-wide-nodes.dat > commlist-wide.dat &
    sed 's|^\([0-9].*\) [^ ].*|\1|' commlist-info-nodes.dat > commlist-info.dat &
    sed 's|^\([0-9].*\) [^ ].*|\1|' joblist-wide-nodes.dat > joblist-wide.dat &
    sed 's|^\([0-9].*\) [^ ].*|\1|' joblist-info-nodes.dat > joblist-info.dat &

    wait

    # Move files to final storage
    mv *.dat $DATAPATH
    cd ../
    rm -rf qscache-pcpid $TMPPATH

    # Update datestamp
    date +%s > $DATAPATH/updated
}

while [[ $SECONDS -lt 60 ]]; do
    main_gen &
    
    if [[ $DEBUG_CYCLE == true ]]; then
        break
    fi

    sleep $GENFREQ
done

wait
