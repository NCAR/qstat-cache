# qstat-cache
A cached version of the PBS Pro qstat command that reduces load on the
scheduler's database

## Details
Most users run the qstat command at reasonable intervals and things work well.
However, with the advent of workflow managers more users are running qstat at
frequencies much too high for current versions of PBS Pro to support well. This
utility creates a simple text-based cache of common qstat output and provides a
script to serve that data to users. If an option is not cached (e.g., -xf
output), the query is sent to PBS's version of qstat for processing. Usage:

```
Usage: qstat [OPTIONS] [JOBID1 JOBID2...|DESTINATION] [@SERVER]

This command provides a lightweight alternative to qstat. Data
are queried and updated every minute from the PBS job scheduler.
Options not listed here will be forwarded to the scheduler.
Please use those options sparingly.

Job IDs, if provided, should be numeric only and space delimited.
If a destination is provided, it should be a valid execution
queue on the chosen server. This cached version of qstat does not
allow mixed queries from multiple servers - only one server may
be specified per request.

Options:
    -h, --help      display this help and exit
    -a              display all jobs (default unless -f specified)
    -f              display full output for a job
    -Fjson          display full output in JSON format (use with -f)
    -H              job output regardless of state or all finished jobs
    -l              disable labels (no header)
    -n              display a list of nodes at the end of the line
    -s              display administrator comment on the next line
    --status        filter jobs by specific single-character status code
    -u              filter jobs by the submitting user
    -w              use wide format output (120 columns)
    -x              include recently finished jobs in output
```

## Installation

1. Clone this repository on your system.
2. Copy or rename the site.cfg.example file to site.cfg and edit the
   configuration settings.
3. Run the `validate.sh` script to ensure your site.cfg is set up properly
   (*optional, but recommended*).
4. Schedule the gen_data.sh script to run at regular intervals (typically every
   minute via a cron job).
5. Add the cached version of `qstat` to your (and your users') environment PATH.

### site.cfg settings

```
# Path where cached data will be stored and accessed

DATAPATH=

# Temporary data path used by gen_data when creating
# cached output from qstat (fast file system is best)

TMPPATH=/dev/shm

# Optional path for logging qstat invocations
# If set, a log will be created for each user on each day
#   that records calls to qstat along with arguments
# If blank, logging will be disabled

LOGPATH=

# The maximum wait time in seconds before the cache is
# bypassed and the real qstat is called

MAXWAIT=20

# The maximum allowed age in seconds of cache data. Beyond
# this age we bypass the cache and call the true qstat

MAXAGE=300

# Delay in seconds to impose on qstat calls that bypass
# the cache due to aged data. Increasing this value can help
# the scheduler when under high load

AGEDELAY=0

# Specify the location of the actual qstat command

QSTATBIN=/opt/pbs/bin/qstat

# Some sites may need to prefix calls to PBS with another
# command (e.g., a sudo operation). Use this variable to
# specify a prefix for PBS calls

PBSPREFIX="sudo -u pbsadmin"

# Specify the sub-minute frequency to generate data
# in seconds

GENFREQ=10

# Mapping of long-form server names for peer-scheduling
# user queries (use qstat -Bf to get server names)

SERVERMAP=

# Which potentially expensive options do you want to enable

CACHEFLAGS="f Fjson"

# Enable privilege checking according to following user and
# group settings. If false, all queries allowed.

PRIV_MODE=true

# Permit users and groups from these two lists respectively to
# see "full" job output from other users (can contain sensitive
# information if user is passing environment with -V)

PRIV_USERS="root"
PRIV_GROUPS="admins support"
```

### Example crontab

Here is a sample crontab that will run the gen_data.sh script every minute
(sub-minute scheduled is recommended and enabled via the site.cfg). The idea
here is to run often enough that users and their workflows are satisfied, but
not so often that we put our own load on PBS.

```
#   Run qstat cache generation script every minute
#       Added by Joe User on 4 Dec 2019
* * * * * QSCACHE_SERVER=sitename /path/to/qstat_cache/gen_data.sh
```

## Debugging

There are two environment variables you may set to assist in debugging. Setting
`QSCACHE_DEBUG` to `2` will cause qstat to print the error stream from the
cache read command if it fails (otherwise this output is suppressed). If set to
`1` or greater, qstat will also print the age of the cache, assuming it can be
found.

If you set `QSCACHE_BYPASS` to `true`, the cache will be bypassed regardless of
which options are set, and the scheduler version of qstat will instead be
called.
