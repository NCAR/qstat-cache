#!/bin/bash

TMPPATH=/dev/shm
ENDPATH=/glade/work/csgteam/qs_cache

mkdir -p $ENDPATH
cd $TMPPATH

# Get data from PBS (must run as csgteam)
sudo -u csgteam /opt/pbs/bin/qstat -a -1 -n -s -w -x | sed '1,5d' > newlist-wide.dat &
sudo -u csgteam /opt/pbs/bin/qstat -1 -n -s -x | sed '1,5d' > newlist-info.dat &
sudo -u csgteam /opt/pbs/bin/qstat -x | sed '1,5d' > newlist-default.dat &

time wait

# Poor-man's sync
mv newlist-wide.dat commlist-wide-nodes.dat
mv newlist-info.dat commlist-info-nodes.dat
mv newlist-default.dat joblist-default.dat

# Get versions without admin comment
grep -v '^ ' commlist-wide-nodes.dat > joblist-wide-nodes.dat &
grep -v '^ ' commlist-info-nodes.dat > joblist-info-nodes.dat &

time wait

# Get versions without nodelist
sed -r 's/([0-9].*) [-,r].*/\1/' commlist-wide-nodes.dat > commlist-wide.dat &
sed -r 's/([0-9].*) [-,r].*/\1/' commlist-info-nodes.dat > commlist-info.dat &
sed -r 's/([0-9].*) [-,r].*/\1/' joblist-wide-nodes.dat > joblist-wide.dat &
sed -r 's/([0-9].*) [-,r].*/\1/' joblist-info-nodes.dat > joblist-info.dat &

time wait

# Move files to final storage
mv *.dat $ENDPATH
