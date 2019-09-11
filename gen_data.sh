#!/bin/bash

TMPPATH=/dev/shm/qscache-$$
ENDPATH=/glade/work/vanderwb/qs_cache

cd /dev/shm

# Don't run if already running
if [[ -f qscache-pcpid ]]; then
    # If a minute has passed, end previous cycle
    TELAP=$(($(date +%s) - $(date +%s -r qscache-pcpid)))

    if [[ $TELAP -gt 60 ]]; then
        PCPID=$(cat qscache-pcpid >& /dev/null)
        
        if kill -0 $PCPID 2> /dev/null; then
            kill $PCPID
        fi

        rm -rf qscache-pcpid /dev/shm/qscache-$PCPID
    fi

    exit
fi

echo $$ > qscache-pcpid
mkdir -p $TMPPATH $ENDPATH
cd $TMPPATH

# Get data from PBS (must run as csgteam)
sudo -u csgteam /opt/pbs/bin/qstat -a -1 -n -s -w -x | sed '1,5d' > newlist-wide.dat &
sudo -u csgteam /opt/pbs/bin/qstat -1 -n -s -x | sed '1,5d' > newlist-info.dat &
sudo -u csgteam /opt/pbs/bin/qstat -x | sed '1,5d' > newlist-default.dat &

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
sed -r 's/([0-9].*) [-,r].*/\1/' commlist-wide-nodes.dat > commlist-wide.dat &
sed -r 's/([0-9].*) [-,r].*/\1/' commlist-info-nodes.dat > commlist-info.dat &
sed -r 's/([0-9].*) [-,r].*/\1/' joblist-wide-nodes.dat > joblist-wide.dat &
sed -r 's/([0-9].*) [-,r].*/\1/' joblist-info-nodes.dat > joblist-info.dat &

wait

# Move files to final storage
mv *.dat $ENDPATH
cd ../
rm -rf qscache-pcpid $TMPPATH
