# qstat-cache
A cached version of the PBS Pro qstat command that reduces load on the scheduler's database

## Details
Most users run the qstat command at reasonable intervals and things work well. However, with the advent of workflow managers more users are running qstat at frequencies much too high for current versions of PBS Pro to support well. This utility creates a simple text-based cache of common qstat output and provides a script to serve that data to users. If an option is not cached (e.g., -f output), the query is sent to PBS's version of qstat for processing. Usage:

```
Usage: qstat [OPTIONS] [JOBID1 JOBID2...]

This command provides a lightweight alternative to qstat. Data
are queried and updated every minute from the PBS job scheduler.
Options not listed here will be forwarded to the scheduler.
Please use those options sparingly.

Job IDs, if provided, should be numeric only and space delimited.

Options:
    -h, --help      display this help and exit
    -l              disable labels (no header)
    -n              display a list of nodes at the end of the line
    -s              display administrator comment on the next line
    -S, --status    filter jobs by specific single-character status code
    -u, --user      filter jobs by the submitting user
    -w, --wide      use wide format output (120 columns)
    -x              include recently finished jobs in output
```

## Installation

1. Clone this repository on your system.
2. Copy or rename the site.cfg.example file to site.cfg and edit the configuration settings.
3. Run the `validate.sh` script to ensure your site.cfg is set up properly (*optional, but recommended*).
4. Schedule the gen_data.sh script to run at regular intervals (typically every minute via a cron job).
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

# Specify the location of the actual qstat command

QSTATBIN=/opt/pbs/bin/qstat

# Some sites may need to prefix calls to PBS with another
# command (e.g., a sudo operation). Use this variable to
# specify a prefix for PBS calls

PBSPREFIX=

# Specify the sub-minute frequency to generate data
# in seconds

GENFREQ=10
```

### Example crontab

Here is a sample crontab that will run the gen_data.sh script every minute (sub-minute scheduled is recommended and enabled via the site.cfg). The idea here is to run often enough that users and their workflows are satisfied, but not so often that we put our own load on PBS.

```
#   Run qstat cache generation script every minute
#       Added by Joe User on 4 Dec 2019
* * * * * /path/to/qstat_cache/gen_data.sh
```

## Debugging

There are two environment variables you may set to assist in debugging. Setting `QSCACHE_DEBUG` to `true` will cause qstat to print the error stream from the cache read command if it fails (otherwise this output is suppressed). It will also print the age of the cache, assuming it can be found.

If you set `QSCACHE_BYPASS` to `true`, the cache will be bypassed regardless of which options are set, and the scheduler version of qstat will instead be called.
