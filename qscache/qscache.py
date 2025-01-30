#!/usr/bin/env python3

import os, sys, re, json, collections
from datetime import datetime

help_text = """This command provides a lightweight alternative to qstat. Data
are queried and updated every minute from the PBS job scheduler. Options not
listed here will be forwarded to the scheduler. Please use those options
sparingly. Job IDs, if provided, should be numeric only and space delimited. If
a destination is provided, it should be a valid execution queue on the chosen
server. This cached version of qstat does not allow mixed queries from multiple
servers - only one server may be specified per request."""

format_help = """This option allows you to provide a format string that
specifies a custom set of fields to display, along with column widths. All
fields are string type, so only string formatting is allowed. Any field shown
by the -f option can be used.

The default format string for default mode output is:

{Job_Id:17} {Job_Name:16} {Job_Owner:16} {resources_used[cput]:>8} {job_state:1} {queue:16}
"""

def log_usage(config, used_cache, info):
    if "log" in config["run"]:
        timestamp = datetime.now().strftime("%H:%M:%S")

        with open(config["run"]["log"], "a") as lf:
            lf.write("{:10} {:20} {:10} {:10} {:15} {}\n".format(timestamp, config["run"]["host"],
                    config["run"]["pid"], f"cache={used_cache}", info, " ".join(sys.argv[1:])))

def bypass_cache(config, reason, delay = 1):
    import time, subprocess

    if not os.path.isfile(config["pbs"]["qstat"]):
        print("Error: PBS cannot be found on this system", file = sys.stderr)
        sys.exit(1)

    time.sleep(int(delay))
    log_usage(config, "no", "reason={}".format(reason))

    args = [config["pbs"]["qstat"]]
    skip_next = False

    for arg in sys.argv[1:]:
        if arg.startswith("--"):
            skip_next = True
        elif not skip_next or "-" in arg:
            args.append(arg)
            skip_next = False

    status = subprocess.check_call(args)
    sys.exit(status)

def read_config(path, pkg_root, server = "site"):
    import configparser, socket

    config = configparser.ConfigParser(interpolation = configparser.ExtendedInterpolation())
    config.read_dict({
            "paths"                 : {
                    "install_dir"   : pkg_root,
                    "data"          : f"{pkg_root}/data/{server}",
                    "temp"          : f"{pkg_root}/temp/{server}",
                    "logs"          : ""
                    },
            "cache"                 : {
                    "maxwait"       : "20",
                    "maxage"        : "300",
                    "agedelay"      : "5",
                    "frequency"     : "60"
                    },
            "pbs"                   : {
                    "qstat"         : "/opt/pbs/bin/qstat"
                    },
            "privileges"            : {
                    "active"        : "False"
                    },
            "priv.all"              : {
                    "users"         : "",
                    "groups"        : ""
                    },
            "priv.env"              : {
                    "users"         : "",
                    "groups"        : ""
                    },
            "run"                   : {
                    "pid"           : str(os.getpid()),
                    "host"          : socket.gethostname()
                    }
            })

    try:
        with open(path, "r") as config_file:
            config.read_file(config_file)
    except FileNotFoundError:
        print("No site config found for cached qstat. Bypassing cache...\n", file = sys.stderr)
        bypass_cache(config, "nocfg")

    return config

def server_checks(config, server_list, server):
    if server in config["servermap"]:
        if server not in server_list:
            server_list.append(server)

        return config["servermap"][server]
    else:
        map_key = [s for s in config["servermap"] if config["servermap"][s] == server][0]

        if map_key not in server_list:
            server_list.append(map_key)

        return server

def update_dict(my_dict, new_dict):
    import collections.abc

    for k, v in new_dict.items():
        if isinstance(v, collections.abc.Mapping):
            my_dict[k] = update_dict(my_dict.get(k, {}), v)
        else:
            my_dict[k] = v

    return my_dict

def read_data(config, server, sources):
    from timeit import default_timer as timer
    from time import time

    for source in sources:
        if source == "active":
            max_age = config["cache"]["maxage"]
        else:
            max_age = config[source]["maxage"]

        json_path = "{}/{}-{}.dat".format(config["paths"]["data"], server, source)
        age_path = "{}/{}-{}.age".format(config["paths"]["data"], server, source)
        start_time = timer()

        while True:
            with open(json_path, "r") as jf:
                try:
                    if "data" in locals():
                        data = update_dict(data, json.load(jf, object_pairs_hook=collections.OrderedDict, strict = False))
                    else:
                        data = json.load(jf, object_pairs_hook=collections.OrderedDict, strict = False)
                    break
                except json.decoder.JSONDecodeError:
                    if (timer() - start_time) > int(config["cache"]["maxwait"]):
                        print("No data found at configured path. Bypassing cache...\n", file = sys.stderr)
                        bypass_cache(config, "nodata")
                    time.sleep(1)

        with open(age_path, "r") as uf:
            cache_time = int(uf.read())

        if (int(time()) - cache_time) >= int(max_age):
            print("{} data is more than {} seconds old. Bypassing cache...\n".format(source, max_age), file = sys.stderr)
            bypass_cache(config, "olddata", config["cache"]["agedelay"])

    return data

def select_by_id(jobs, data, job_ids):
    jobs.update({ job : data["Jobs"][job] for job in job_ids if job not in jobs and job in data["Jobs"] and data["Jobs"][job]["server"].startswith(job_ids[job]) })
    return jobs

def select_by_queue(jobs, data, queues):
    for q in queues:
        queue, server = q.split("@")

        if queue:
            jobs.update({ job : data["Jobs"][job] for job in data["Jobs"] if job not in jobs and data["Jobs"][job]["queue"] == queue and data["Jobs"][job]["server"].startswith(f"{server}") })
        else:
            jobs.update({ job : data["Jobs"][job] for job in data["Jobs"] if job not in jobs and data["Jobs"][job]["server"].startswith(f"{server}") })

    return jobs

def check_privilege(config, user):
    import grp

    my_groups = [g.gr_name for g in grp.getgrall() if user in g.gr_mem]

    if config["privileges"]["active"] == "True":
        privilege = "default"

        for level in ["all", "env"]:
            if user in config[f"priv.{level}"]["users"].split():
                privilege = level
            elif any((g for g in config[f"priv.{level}"]["groups"].split() if g in my_groups)):
                privilege = level
    else:
        privilege = "env"

    return privilege

def filter_jobs(jobs, user = None, status = None, arrays = False, jobs_only = False):
    if user:
        jobs = { job : jobs[job] for job in jobs.keys() if jobs[job]["Job_Owner"].startswith("{}@".format(user)) }

    if status:
        jobs = { job : jobs[job] for job in jobs.keys() if jobs[job]["job_state"] in status }

    if arrays:
        if jobs_only:
            jobs = { job : jobs[job] for job in jobs.keys() if re.search("\[[0-9]+\]", job) }
    else:
        jobs = { job : jobs[job] for job in jobs.keys() if not re.search("\[[0-9]+\]", job) }

    return jobs

def strip_env(jobs, user):
    for job in jobs:
        if not jobs[job]["Job_Owner"].startswith(f"{user}@"):
            jobs[job]["Variable_List"] = "Hidden"

    return jobs

def print_nodes(nodes):
    while len(nodes) > 71:
        chunk = nodes[:71].rsplit("+", 1)[0] + "+"
        nodes = nodes[len(chunk):]
        print("    {}".format(chunk))

    print("    {}".format(nodes))

def column_output(jobs, fields, mode, header, nodes, comment_format, unified, keep_dashes = False):
    class altair_string(collections.UserString):
        def __init__(self, value, suffix = "*"):
            self.value = str(value)
            self.suffix = suffix
            self.suffix_width = len(suffix)

            super().__init__(value)

        def __format__(self, fmt):
            if "." in fmt:
                allowed_length = int(fmt.rsplit(".")[-1])

                if len(self.value) > allowed_length:
                    self.value = self.value[:(allowed_length - self.suffix_width)] + self.suffix

            return self.value.__format__(fmt)

    class altair_dict(collections.UserDict):
        def __init__(self, dictionary, /, **kwargs):
            if "fill_value" in kwargs:
                self.fill_value = kwargs["fill_value"]
            else:
                self.fill_value = ""

            for key, value in dictionary.items():
                if isinstance(value, dict):
                    dictionary[key] = altair_dict(value)
                elif key == "comment":
                    dictionary[key] = altair_string(value, suffix = "...")
                elif key != "walltime":
                    dictionary[key] = altair_string(value)

            super().__init__(dictionary)

        def __missing__(self, key):
            if key in ["resources_used", "Resource_List"]:
                if "{}" in self.fill_value:
                    return altair_dict({}, fill_value = "{}.{{}}".format(key))
                else:
                    return altair_dict({}, fill_value = self.fill_value)
            elif "{}" in self.fill_value:
                return self.fill_value.format(key)
            else:
                return self.fill_value

    fields = re.sub(r":([<>]*)([0-9]+)", r":\1\2.\2", fields)

    if header:
        label_fields = fields.replace(">", "")

        if mode == "default":
            labels = altair_dict({
                    "Job_Id"            : "Job id",
                    "Job_Name"          : "Name",
                    "Job_Owner"         : "User",
                    "resources_used"    : {
                            "cput"      : "Time Use"
                        },
                    "job_state"         : "S",
                    "queue"             : "Queue"
                    }, fill_value = "{}")
        else:
            l1_labels = altair_dict({
                    "resources_used"    : {
                            "walltime"  : "Elap"
                        },
                    "Resource_List"     : {
                        "mem"       : "Req'd",
                        "walltime"  : "Req'd"
                        }
                    })
            l2_labels = altair_dict({
                    "Job_Id"            : "Job ID",
                    "Job_Name"          : "Jobname",
                    "Job_Owner"         : "Username",
                    "resources_used"    : {
                            "walltime"  : "Time"
                        },
                    "job_state"         : "S",
                    "queue"             : "Queue",
                    "session_id"        : "SessID",
                    "Resource_List"     : {
                            "nodect"    : "NDS",
                            "ncpus"     : "TSK",
                            "mem"       : "Memory",
                            "walltime"  : "Time"
                        }
                    }, fill_value = "{}")

        dashes = 100 * "-"
        previous_server = None

    for jid in jobs:
        job = altair_dict(jobs[jid], fill_value = " -- ")
        job["Job_Id"] = altair_string(jid)
        job["Job_Owner"] = job["Job_Owner"].split("@")[0]

        if header:
            if previous_server != job["server"]:
                previous_server = job["server"]

                if mode == "default":
                    print(label_fields.format_map(labels))
                else:
                    print("\n{}:".format(previous_server.split(".")[0]))
                    print(label_fields.format_map(l1_labels))
                    print(label_fields.format_map(l2_labels))

                if keep_dashes:
                    print(re.sub(r"{[^:}]*", r"{0", fields).format(dashes))
                else:
                    dash_fields = re.sub(r"{[^:}]*", r"{0", fields.rsplit(maxsplit = 1)[0]) + " {0:5.5}"
                    print(dash_fields.format(dashes))

        try:
            job_line = fields.format_map(job)
        except TypeError:
            print(job)
            sys.exit()

        if unified:
            if nodes:
                job_line += " {exec_host}".format_map(job)
            elif comment_format:
                job_line += " " + comment_format.format_map(job)

        print(job_line)

        if nodes and not unified:
            print_nodes(job["exec_host"])

        if comment_format and (not unified or nodes):
            print(comment_format.format_map(job))

def full_output(jobs, wide):
    for jid, job in jobs.items():
        print("Job Id: {}".format(jid))

        for field in job.keys():
            if not isinstance(job[field], dict):
                print_wrapped("{} = {}".format(field, job[field]), wide)
            else:
                if field == "Variable_List":
                    first_line = True

                    for subfield in job[field]:
                        try:
                            if "," in job[field][subfield][1:]:
                                job[field][subfield] = job[field][subfield][0] + job[field][subfield][1:].replace(",", "\,")
                        except TypeError:
                            pass

                        if first_line:
                            line = "{} = {}={}".format(field, subfield, job[field][subfield])
                            first_line = False
                        else:
                            line = "{},{}={}".format(line, subfield, job[field][subfield])

                    print_wrapped(line, wide, 1)
                else:
                    for subfield in job[field]:
                        print_wrapped("{}.{} = {}".format(field, subfield, job[field][subfield]))

        print()

def dsv_output(my_dict, delimiter, prefix = ""):
    line = ""

    for key, value in my_dict.items():
        if isinstance(value, dict):
            if key == "Variable_List":
                line += "{}={}{}".format(key, dsv_output(value, ","), delimiter)
            else:
                line += "{}{}".format(dsv_output(value, delimiter, f"{key}."), delimiter)
        else:
            line += f"{prefix}{key}={value}{delimiter}"

    return line[:-1]

def print_wrapped(line, wide = False, extra = 0):
    indent = "    "
    ilen = 4
    my_extra = extra

    if not wide:
        while len(line) > (79 - ilen):
            if "," in line[:(79 - ilen)]:
                chunk = line[:(79 - ilen)].rsplit(",", 1)[0] + ","
                line = line[len(chunk):]
                my_extra = extra
            else:
                chunk = line[:(79 - ilen - my_extra)]
                line = line[(79 - ilen - my_extra):]
                my_extra = 0

            print("{}{}".format(indent, chunk))
            indent = "\t"
            ilen = 8

    print("{}{}".format(indent, line))

def main(my_root):
    import argparse, socket, getpass

    my_username = getpass.getuser()

    # Prevent pipe interrupt errors
    from signal import signal, SIGPIPE, SIG_DFL
    signal(SIGPIPE,SIG_DFL)

    arg_dict = { "filters"      : "job IDs or queues",
                 "-1"           : "display node or comment information on job line",
                 "-a"           : "display all jobs (default unless -f specified)",
                 "-D"           : "specify a delimiter if using -Fdsv (default = '|')",
                 "-f"           : "display full output for a job",
                 "-F"           : "full output (-f) in custom format",
                 "--format"     : "column output in custom format (=help for more)",
                 "-H"           : "all moved or finished jobs / specific job of any state",
                 "-J"           : "only show information for jobs (or subjobs with -t)",
                 "--noheader"   : "disable labels (no header)",
                 "-n"           : "display a list of nodes at the end of the line",
                 "-s"           : "display administrator comment on the next line",
                 "--status"     : "filter jobs by specific single-character status code",
                 "-t"           : "show information for both jobs and array subjobs",
                 "-u"           : "filter jobs by the submitting user",
                 "-w"           : "use wide format output (120 columns)",
                 "-x"           : "all job records in recent history"    }

    parser = argparse.ArgumentParser(prog = "qstat", description = help_text)

    for arg in arg_dict:
        if arg == "filters":
            parser.add_argument(arg, help = arg_dict[arg], nargs="*")
        elif arg == "-D":
            parser.add_argument(arg, help = arg_dict[arg], default = "|", metavar = "DELIMITER")
        elif arg == "-F":
            parser.add_argument(arg, help = arg_dict[arg], choices = ["json", "dsv"])
        elif arg in ["--status", "--format"]:
            parser.add_argument(arg, help = arg_dict[arg])
        elif arg in ["-u"]:
            parser.add_argument(arg, help = arg_dict[arg], metavar = "USER")
        else:
            parser.add_argument(arg, help = arg_dict[arg], action = "store_true")

    args = parser.parse_args()

    if args.format == "help":
        print(format_help)
        sys.exit()

    # Get configuration information
    try:
        server = os.environ["QSCACHE_SERVER"]
    except KeyError:
        server = "site"

    config = read_config("{}/etc/{}.cfg".format(my_root, server), my_root, server)

    if config["paths"]["logs"]:
        config["run"]["log"] = "{}/{}-{}.log".format(config["paths"]["logs"], my_username, datetime.now().strftime("%Y%m%d"))

    if "QSCACHE_BYPASS" in os.environ:
        bypass_cache(config, manual)

    my_host = socket.gethostname()
    jobs = collections.OrderedDict()

    if server in config["servermap"]:
        host_server = config["servermap"][server]
    else:
        host_server = server

    sources = ["active"]

    if args.x or args.H:
        sources = ["history"] + sources

    if args.filters:
        ids = {}
        queues = []
        servers = [server]

        for ft in args.filters:
            if ft[0].isdigit():
                if "." in ft:
                    job_id, job_server = ft.split(".")
                    job_server = server_checks(config, servers, job_server)
                else:
                    job_id = ft
                    job_server = host_server

                ids[f"{job_id}.{job_server}"] = job_server
            else:
                if "@" in ft:
                    queue_name, queue_server = ft.split("@")
                    queue_server = server_checks(config, servers, queue_server)
                else:
                    queue_name = ft
                    queue_server = host_server

                queues.append(f"{queue_name}@{queue_server}")

        for read_server in servers:
            if read_server == server:
                data = read_data(config, read_server, sources)
            else:
                temp = read_data(config, read_server, sources)
                data["Jobs"].update(temp["Jobs"])

        if ids:
            jobs = select_by_id(jobs, data, ids)

        if queues:
            jobs = select_by_queue(jobs, data, queues)
    else:
        data = read_data(config, server, sources)
        jobs = select_by_queue(jobs, data, [f"@{host_server}"])

    my_privilege = check_privilege(config, my_username)

    if args.H:
        status = "FMX"
    else:
        status = args.status

    if my_privilege in ["all", "env"]:
        jobs = filter_jobs(jobs, args.u, status, args.t, args.J)
    else:
        jobs = filter_jobs(jobs, my_username, status, args.t, args.J)

    if args.f:
        if my_privilege == "all":
            jobs = strip_env(jobs, my_username)

        if args.F == "json":
            data["Jobs"] = jobs
            print(json.dumps(data, indent = 4))
        elif args.F == "dsv":
            for job in jobs:
                print("{}{}".format(f"Job Id: {job}{args.D}", dsv_output(jobs[job], args.D)))
        else:
            full_output(jobs, args.w)
    else:
        comments = None
        header = not args.noheader
        unified = getattr(args, '1')

        if args.s:
            if args.w:
                comments = "   {comment:113.113}"
            else:
                comments = "   {comment:73.73}"

        if args.a or args.u or args.s or args.n:
            if args.format:
                column_output(jobs, args.format, "alt", header, False, False, False)
            elif args.w:
                fields =    "{Job_Id:30} {Job_Owner:15} {queue:15} {Job_Name:15} {session_id:>8} "
                fields +=   "{Resource_List[nodect]:>4} {Resource_List[ncpus]:>5} {Resource_List[mem]:>6} "
                fields +=   "{Resource_List[walltime]:>5} {job_state:1} {resources_used[walltime]}"
                column_output(jobs, fields, "alt", header, args.n, comments, unified)
            else:
                fields =    "{Job_Id:15} {Job_Owner:8} {queue:8} {Job_Name:10} {session_id:>6} "
                fields +=   "{Resource_List[nodect]:>3} {Resource_List[ncpus]:>3} {Resource_List[mem]:>6} "
                fields +=   "{Resource_List[walltime]:>5} {job_state:1} {resources_used[walltime]:5}"
                column_output(jobs, fields, "alt", header, args.n, comments, unified)
        elif args.format:
            column_output(jobs, args.format, "default", header, False, False, False)
        elif args.w:
            fields =    "{Job_Id:30} {Job_Name:15} {Job_Owner:15} {resources_used[cput]:>8} "
            fields +=   "{job_state:1} {queue:15}"
            column_output(jobs, fields, "default", header, args.n, comments, unified, keep_dashes = True)
        else:
            fields =    "{Job_Id:17} {Job_Name:16} {Job_Owner:16} {resources_used[cput]:>8} "
            fields +=   "{job_state:1} {queue:16}"
            column_output(jobs, fields, "default", header, args.n, comments, unified)

if __name__ == "__main__":
    main()
