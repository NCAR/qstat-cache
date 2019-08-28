#!/bin/bash

TMPPATH=/dev/shm
ENDPATH=/glade/work/csgteam/qs_cache

cd $TMPPATH

# Get data from PBS (must run as csgteam)
qstat -a -1 -n -s -w -x | sed '1,5d' > newlist-wide.qsdat &
qstat -1 -n -s -x | sed '1,5d' > newlist-default.qsdat &

time wait

# Poor-man's sync
mv newlist-wide.qsdat commlist-wide-nodes.qsdat
mv newlist-default.qsdat commlist-default-nodes.qsdat

# Get versions without admin comment
grep -v '^ ' commlist-wide-nodes.qsdat > joblist-wide-nodes.qsdat &
grep -v '^ ' commlist-default-nodes.qsdat > joblist-default-nodes.qsdat &

time wait

# Get versions without nodelist
sed -r 's/([0-9].*) [-,r].*/\1/' commlist-wide-nodes.qsdat > commlist-wide.qsdat &
sed -r 's/([0-9].*) [-,r].*/\1/' commlist-default-nodes.qsdat > commlist-default.qsdat &
sed -r 's/([0-9].*) [-,r].*/\1/' joblist-wide-nodes.qsdat > joblist-wide.qsdat &
sed -r 's/([0-9].*) [-,r].*/\1/' joblist-default-nodes.qsdat > joblist-default.qsdat &

time wait

# Move files to final storage
mv *.qsdat $ENDPATH
