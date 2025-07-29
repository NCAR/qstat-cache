# qstat-cache
A cached version of the PBS Pro qstat command that reduces load on the
scheduler's database

## Details
Most users run the qstat command at reasonable intervals and things work well.
However, with the advent of workflow managers more users are running qstat at
frequencies much too high for current versions of PBS Pro to support well. This
utility creates a simple text-based cache of common qstat output and provides a
script to serve that data to users. If an option is not cached (e.g., -Q
output), the query is sent to PBS's version of qstat for processing. Usage:

```
usage: qstat [-h] [-1] [-a] [-D DELIMITER] [-f] [-F {json,dsv}]
             [--format FORMAT] [-H] [-J] [--noheader] [-n] [-s]
             [--status STATUS] [-t] [-T] [-u USER] [-w] [-x]
             [filters ...]

This command provides a lightweight alternative to qstat. Data are queried and
updated every minute from the PBS job scheduler. Options not listed here will
be forwarded to the scheduler. Please use those options sparingly. Job IDs, if
provided, should be numeric only and space delimited. If a destination is
provided, it should be a valid execution queue on the chosen server. This
cached version of qstat does not allow mixed queries from multiple servers -
only one server may be specified per request.

positional arguments:
  filters          job IDs or queues

options:
  -h, --help       show this help message and exit
  -1               display node or comment information on job line
  -a               display all jobs (default unless -f specified)
  -D DELIMITER     specify a delimiter if using -Fdsv (default = '|')
  -f               display full output for a job
  -F {json,dsv}    full output (-f) in custom format
  --format FORMAT  column output in custom format (=help for more)
  -H               all moved or finished jobs / specific job of any state
  -J               only show information for jobs (or subjobs with -t)
  --noheader       disable labels (no header)
  -n               display a list of nodes at the end of the line
  -s               display administrator comment on the next line
  --status STATUS  filter jobs by specific single-character status code
  -t               show information for both jobs and array subjobs
  -T               displays estimated start time for queued jobs
  -u USER          filter jobs by the submitting user
  -w               use wide format output (120 columns)
  -x               all job records in recent history
```

## Installation

There are two methods for installing **qstat-cache** - using the included
`Makefile` or with `pip`.

### Makefile method

1. Clone this repository on your system.
2. Install at your desired path using `make install
   PREFIX=/path/to/qstat-cache`.

### pip method

1. If desired, first create a virtual environment with `venv` or `conda/mamba`
   and activate it.
2. Now run `python3 -m pip install qstat-cache`.

### Site setup

In either case, the following steps are required to finish configuration.

3. In `$PREFIX/lib/qscache/cfg` or `lib/python3.x/site-packages/qscache/cfg`,
   copy the `site.cfg.example` file to `site.cfg` and customize settings as
   described below. Alternatively, copy the example to `<system>.cfg` and then
   set the environment variable `QSCACHE_SERVER=<system>`. The latter approach
   allows you to cache multiple servers in a complex at the same time.
4. Schedule the `util/gen_data.sh` script to run at regular intervals (typically
   every minute via a cron job).
7. Add the cached version of `qstat` to your (and your users') environment PATH.

### site.cfg settings

```
[paths]
# Temporary data path used by gen_data when creating
# cached output from qstat (fast file system is best)
Temp = ${install_dir}/temp/derecho

# Path where cached data will be stored and accessed
Data = ${install_dir}/data

# Optional path for logging qstat invocations
# If set, a log will be created for each user on each day
#   that records calls to qstat along with arguments
# If blank, logging will be disabled
Logs = ${install_dir}/test/logs

[cache]
# The maximum wait time in seconds before the cache is
# bypassed and the real qstat is called
MaxWait = 20

# The maximum allowed age in seconds of cache data. Beyond
# this age we bypass the cache and call the true qstat
MaxAge = 300

# Delay in seconds to impose on qstat calls that bypass
# the cache due to aged data. Increasing this value can help
# the scheduler when under high load
AgeDelay = 5

# Specify the sub-minute frequency to generate data
# in seconds
Frequency = 60

[pbs]
# Specify the location of the actual qstat command
Qstat = /opt/pbs/bin/qstat

# Some sites may need to prefix calls to PBS with another
# command (e.g., a sudo operation). Use this variable to
# specify a prefix for PBS calls
Prefix = sudo -u adminuser

[servermap]
# Mapping of long-form server names for peer-scheduling
# user queries (use qstat -Bf to get server names)
casper = casper-pbs
derecho = desched1

[privileges]
# Enable privilege checking according to following user and
# group settings. If false, all queries allowed.
Active = True

[priv.all]
# Permit users and groups from these two lists respectively to
# see "full" job output from other users excluding the user
# environment contained in a job's Variable_List
Users = vanderwb
Groups = csgteam

[priv.env]
# Permit users and groups from these two lists to view all full
# job output, including the user environment
Users = vanderwb
Groups =
```

### Example crontab

Here is a sample crontab that will run the `gen_data.sh` script every minute
(sub-minute scheduled is recommended and enabled via the site.cfg). The idea
here is to run often enough that users and their workflows are satisfied, but
not so often that we put our own load on PBS.

Here, we use the `QSCACHE_SERVER` variable to specify a particular system in a
multi-server complex.

```
#   Run qstat cache generation script every minute
#       Added by Joe User on 4 Dec 2019
* * * * * QSCACHE_SERVER=sitename /path/to/qstat_cache/util/gen_data.sh
```

## Debugging

There are two environment variables you may set to assist in debugging. Setting
`QSCACHE_DEBUG` will cause qstat to print the age of the cache, assuming it can
be found.

If you set `QSCACHE_BYPASS` to `true`, the cache will be bypassed regardless of
which options are set, and the scheduler version of qstat will instead be
called.
