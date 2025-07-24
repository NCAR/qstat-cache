#!/usr/bin/env python3

import os, sys, re, json, collections, time, subprocess, grp
import configparser, socket, argparse, getpass, textwrap

from signal import signal, SIGPIPE, SIG_DFL
from datetime import datetime
from timeit import default_timer as timer


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

DT_NOW=datetime.now()

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
    def __init__(self, dictionary, **kwargs):
        if "fill_value" in kwargs:
            self.fill_value = kwargs["fill_value"]
        else:
            self.fill_value = ""

        for key, value in dictionary.items():
            if isinstance(value, dict):
                dictionary[key] = altair_dict(value, **kwargs)
            elif key == "comment":
                dictionary[key] = altair_string(value, suffix = "...")
            elif key == "start_time" and "process_start" in kwargs:
                start_time = datetime.strptime(value, "%c")
                elapsed_secs = start_time.timestamp() - DT_NOW.timestamp()

                if kwargs["process_start"] == "default":
                    if elapsed_secs <= 0:
                        dictionary[key] = altair_string("--")
                    elif start_time.day == DT_NOW.day:
                        dictionary[key] = altair_string(start_time.strftime("%H:%M"))
                    elif (start_time.day - DT_NOW.day) < 7:
                        tmp_str = start_time.strftime("%a%H")
                        dictionary[key] = altair_string(tmp_str[:2] + " " + tmp_str[3:])
                    elif start_time.year == DT_NOW.year:
                        dictionary[key] = altair_string(start_time.strftime("%b"))
                    elif elapsed_secs <= 157680000:
                        dictionary[key] = altair_string(start_time.strftime("%Y"))
                    else:
                        dictionary[key] = altair_string(">5yrs")
                else:
                    if elapsed_secs <= 0:
                        dictionary[key] = altair_string("--")
                    elif start_time.day == DT_NOW.day:
                        dictionary[key] = altair_string("Today " + start_time.strftime("%H:%M"))
                    elif (start_time.day - DT_NOW.day) < 7:
                        dictionary[key] = altair_string(start_time.strftime("%a %H:%M"))
                    elif start_time.year == DT_NOW.year:
                        dictionary[key] = altair_string(start_time.strftime("%a %b %d %H:%M"))
                    else:
                        dictionary[key] = altair_string(value)
            elif key != "walltime":
                dictionary[key] = altair_string(value)

        super().__init__(dictionary)

    def __missing__(self, key):
        if key in ["resources_used", "Resource_List", "estimated"]:
            if "{}" in self.fill_value:
                return altair_dict({}, fill_value = "{}.{{}}".format(key))
            else:
                return altair_dict({}, fill_value = self.fill_value)
        elif "{}" in self.fill_value:
            return self.fill_value.format(key)
        elif key == "start_time":
            return "--"
        else:
            return self.fill_value

def log_usage(config, used_cache, info = ""):
    if "log" in config["run"]:
        timestamp = DT_NOW.strftime("%H:%M:%S")

        with open(config["run"]["log"], "a") as lf:
            lf.write("{:10} {:20} {:10} {:10} {:15} {}\n".format(timestamp, config["run"]["host"],
                    config["run"]["pid"], f"cache={used_cache}", info, " ".join(sys.argv[1:])))

def bypass_cache(config, reason, delay = 1):
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

    proc = subprocess.run(args)
    sys.exit(proc.returncode)

def read_config(path, pkg_root, server = "site"):
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
            "history"               : {
                    "maxage"        : "600"
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

def get_mapped_server(config, server, request = "key"):
    if server in config["servermap"]:
        return server, config["servermap"][server]
    else:
        return [s for s in config["servermap"] if config["servermap"][s] == server][0], server

def get_server_info(config, server, source):
    if source == "active":
        max_age = config["cache"]["maxage"]
    else:
        max_age = config[source]["maxage"]

    age_path = "{}/{}-{}.age".format(config["paths"]["data"], server, source)
    start_time = timer()

    while True:
        try:
            with open(age_path, "r") as uf:
                try:
                    server_info = json.load(uf)
                    break
                except json.decoder.JSONDecodeError:
                    if (timer() - start_time) > int(config["cache"]["maxwait"]):
                        print("No data found at configured path. Bypassing cache...\n", file = sys.stderr)
                        bypass_cache(config, "nodata")
                    time.sleep(1)
        except FileNotFoundError:
            print("Empty cache found for cached qstat. Bypassing cache...\n", file = sys.stderr)
            bypass_cache(config, "nodata")

    try:
        if (int(time.time()) - int(server_info["timestamp"])) >= int(max_age) and "QSCACHE_IGNORE_AGE" not in os.environ:
            print("{} data is more than {} seconds old. Bypassing cache...\n".format(source, max_age), file = sys.stderr)
            bypass_cache(config, "olddata", config["cache"]["agedelay"])
        else:
            return server_info
    except ValueError:
            print("{} cache has metadata errors. Bypassing cache...\n".format(source), file = sys.stderr)
            bypass_cache(config, "metadata", config["cache"]["agedelay"])

def get_job_data(config, server, source, process_env = False, select_ids = None):
    get_server_info(config, server, source)
    data_path = "{}/{}-{}.dat".format(config["paths"]["data"], server, source)
    start_time = timer()

    while True:
        with open(data_path, "r", errors = "ignore") as data_file:
            try:
                for line in data_file:
                    data = line.rstrip("\n").split("|-")
                    job_id = data[0].split(" ")[-1]

                    # Let's not do anything else if not a requested ID
                    if select_ids:
                        if not any(job_id.startswith(sid) for sid in select_ids):
                            continue

                    job_info = {}

                    for item in data[1:]:
                        key, value = item.split("=", maxsplit = 1)

                        if "." in key:
                            main_key, sub_key = key.split(".")

                            try:
                                job_info[main_key][sub_key] = value
                            except KeyError:
                                job_info[main_key] = {sub_key : value}
                        elif process_env and key == "Variable_List":
                            job_info[key] = {}
                            use_re = False

                            # Try to avoid using lookback-expression, as it is expensive!
                            for env_var in value.split(","):
                                try:
                                    ek, ev = env_var.split("=", maxsplit = 1)
                                    job_info[key][ek] = ev
                                except ValueError:
                                    use_re = True
                                    break

                            if use_re:
                                for env_var in re.split(r"(?<!\\),", value):
                                    ek, ev = env_var.split("=", maxsplit = 1)
                                    job_info[key][ek] = ev
                        else:
                            job_info[key] = value

                    yield job_id, job_info

                break
            except FileNotFoundError:
                if (timer() - start_time) > int(config["cache"]["maxwait"]):
                    print("No data found at configured path. Bypassing cache...\n", file = sys.stderr)
                    bypass_cache(config, "nodata")
                time.sleep(1)

def check_job(job_id, job_info, select_queue = None, filters = None, subjobs = []):
    if select_queue:
        name, server = select_queue.split("@")

        if name:
            if job_info["queue"] != name or not job_info["server"].startswith(f"{server}"):
                return False
        else:
            if not job_info["server"].startswith(f"{server}"):
                return False

    if filters.u and not job_info["Job_Owner"].startswith(f"{filters.u}@"):
        return False

    if filters.status and not job_info["job_state"] in filters.status:
        return False

    if filters.t:
        if filters.J and not re.search(r"\[[0-9]+\]", job_id):
            return False
    elif job_id not in subjobs and re.search(r"\[[0-9]+\]", job_id):
        return False

    return True

def process_jobs(config, data_server, source, header, limit_user, args, ids, subjobs, process_env):
    if ids:
        jobs = {}

        for job_id, job_info in get_job_data(config, data_server, source, process_env, ids):
            if check_job(job_id, job_info, filters = args, subjobs = subjobs):
                jobs[job_id] = job_info

        try:
            for job_id in jobs:
                print_job(job_id, jobs[job_id], args, header, limit_user)
                header = False
        except KeyError:
            pass

def check_privilege(config, user):
    my_groups = [g.gr_name for g in grp.getgrall() if user in g.gr_mem]

    if config["privileges"]["active"] == "True":
        privilege = "default"

        for level in ["all", "env"]:
            if config[f"priv.{level}"]["users"] == "*" or config[f"priv.{level}"]["groups"] == "*":
                privilege = level
            elif user in config[f"priv.{level}"]["users"].split():
                privilege = level
            elif any((g for g in config[f"priv.{level}"]["groups"].split() if g in my_groups)):
                privilege = level
    else:
        privilege = "env"

    return privilege

def print_job(job_id, job_info, settings, header = False, limit_user = None):
    if settings.f:
        if limit_user:
            if not job_info["Job_Owner"].startswith(f"{limit_user}@"):
                job_info["Variable_List"] = "Hidden"

        if settings.F == "json":
            global first_job

            if first_job:
                print(',\n    "Jobs":{')
                first_job = False
            else:
                print(",")

            print(textwrap.indent(json.dumps({job_id : job_info}, indent = 4, separators=(',', ':'))[2:-2], "    "), end = "")
        elif settings.F == "dsv":
            print("{}{}".format(f"Job Id: {job_id}{settings.D}", dsv_output(job_info, settings.D)))
        else:
            full_output(job_id, job_info, settings.w)
    else:
        comments = None
        unified = getattr(settings, '1')

        if settings.s:
            if settings.w:
                comments = "   {comment:113.113}"
            else:
                comments = "   {comment:73.73}"

        if settings.T:
            if settings.w:
                process_mode = "wide"
            else:
                process_mode = "default"
        else:
            process_mode = None

        if settings.a or settings.u or settings.s or settings.n or settings.T:
            column_output(job_id, job_info, settings.format, "alt", header, settings.n, comments, unified, process_start = process_mode)
        elif settings.w:
            column_output(job_id, job_info, settings.format, "default", header, settings.n, comments, unified, keep_dashes = True)
        else:
            column_output(job_id, job_info, settings.format, "default", header, settings.n, comments, unified)

def print_nodes(nodes):
    while len(nodes) > 71:
        chunk = nodes[:71].rsplit("+", 1)[0] + "+"
        nodes = nodes[len(chunk):]
        print("    {}".format(chunk))

    print("    {}".format(nodes))

def column_output(job_id, job_info, fields, mode, header, nodes, comment_format, unified, keep_dashes = False, process_start = None):
    fields = re.sub(r":([<>]*)([0-9]+)", r":\1\2.\2", fields)

    if header:
        label_fields = fields.replace(">", "")

        if mode == "default":
            labels = altair_dict({
                    "Job_Id"                : "Job id",
                    "Job_Name"              : "Name",
                    "Job_Owner"             : "User",
                    "resources_used"        : {
                            "cput"          : "Time Use"
                        },
                    "job_state"             : "S",
                    "queue"                 : "Queue"
                    }, fill_value = "{}")
        else:
            l0_labels = altair_dict({
                    "estimated"             : {
                            "start_time"    : "Est"
                        }
                    })
            l1_labels = altair_dict({
                    "resources_used"        : {
                            "walltime"      : "Elap"
                        },
                    "Resource_List"         : {
                        "mem"               : "Req'd",
                        "walltime"          : "Req'd"
                        },
                    "estimated"             : {
                            "start_time"    : "Start"
                        }
                    })
            l2_labels = altair_dict({
                    "Job_Id"                : "Job ID",
                    "Job_Name"              : "Jobname",
                    "Job_Owner"             : "Username",
                    "resources_used"        : {
                            "walltime"      : "Time"
                        },
                    "job_state"             : "S",
                    "queue"                 : "Queue",
                    "session_id"            : "SessID",
                    "Resource_List"         : {
                            "nodect"        : "NDS",
                            "ncpus"         : "TSK",
                            "mem"           : "Memory",
                            "walltime"      : "Time"
                        },
                    "estimated"             : {
                            "start_time"    : "Time"
                        }
                    }, fill_value = "{}")

        dashes = 100 * "-"

        if mode == "default":
            print(label_fields.format_map(labels))
        else:
            print("\n{}:".format(job_info["server"].split(".", maxsplit = 1)[0]))

            if "estimated" in fields:
                print(label_fields.format_map(l0_labels))

            print(label_fields.format_map(l1_labels))
            print(label_fields.format_map(l2_labels))

        if keep_dashes:
            print(re.sub(r"{[^:}]*", r"{0", fields).format(dashes))
        else:
            dash_fields = re.sub(r"{[^:}]*", r"{0", fields.rsplit(maxsplit = 1)[0]) + " {0:5.5}"
            print(dash_fields.format(dashes))

    if process_start:
        job = altair_dict(job_info, fill_value = " -- ", process_start = process_start)
    else:
        job = altair_dict(job_info, fill_value = " -- ")

    job["Job_Id"] = altair_string(job_id)
    job["Job_Owner"] = job["Job_Owner"].split("@")[0]

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

def full_output(job_id, job_info, wide):
    print("Job Id: {}".format(job_id))

    for field in job_info.keys():
        if not isinstance(job_info[field], dict):
            print_wrapped("{} = {}".format(field, job_info[field]), wide)
        else:
            if field == "Variable_List":
                first_line = True

                for subfield in job_info[field]:
                    try:
                        if "," in job_info[field][subfield][1:]:
                            job_info[field][subfield] = job_info[field][subfield][0] + job_info[field][subfield][1:].replace(",", r"\,")
                    except TypeError:
                        pass

                    if first_line:
                        line = "{} = {}={}".format(field, subfield, job_info[field][subfield])
                        first_line = False
                    else:
                        line = "{},{}={}".format(line, subfield, job_info[field][subfield])

                print_wrapped(line, wide, 1)
            else:
                for subfield in job_info[field]:
                    print_wrapped("{}.{} = {}".format(field, subfield, job_info[field][subfield]), wide)

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

    return line[:-len(delimiter)]

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

def process_custom_format(format_str):
    old_specs = [spec.group(1) for spec in re.finditer("{([^}]*)}", format_str)]


    for format_spec in old_specs:
        if ":" in format_spec:
            key, spec = format_spec.split(":", 1)
        elif format_spec != old_specs[-1]:
            print("Error: custom format fields must have width (e.g., {queue:8})", file = sys.stderr)
            sys.exit(1)
        else:
            key = format_spec

        if "." in key:
            main_key, sub_key = key.split(".", 1)
            format_str = format_str.replace(key, f"{main_key}[{sub_key}]")

    return format_str

def main():
    my_root = os.path.dirname(os.path.realpath(__file__))
    my_username = getpass.getuser()

    # Prevent pipe interrupt errors
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
                 "-T"           : "displays estimated start time for queued jobs",
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

    args, unsupported = parser.parse_known_args()

    if args.format == "help":
        print(format_help)
        sys.exit()
    elif args.format:
        args.format = process_custom_format(args.format)

    # Get configuration information
    try:
        server = os.environ["QSCACHE_SERVER"]
    except KeyError:
        server = "site"

    config = read_config("{}/cfg/{}.cfg".format(my_root, server), my_root, server)

    if config["paths"]["logs"]:
        config["run"]["log"] = "{}/{}-{}.log".format(config["paths"]["logs"], my_username, DT_NOW.strftime("%Y%m%d"))

    if "QSCACHE_BYPASS" in os.environ:
        bypass_cache(config, "manual")

    if unsupported:
        bypass_cache(config, "args")

    my_host = socket.gethostname()
    my_privilege = check_privilege(config, my_username)
    limit_user = None
    process_env = False
    source = "active"

    if args.x or args.H:
        source = "history"

    if args.H:
        args.status = "FMX"

    if my_privilege not in ["all", "env"]:
        args.u = my_username

        if my_privilege != "env":
            limit_user = my_username

    header = not args.noheader
    host_data_server, host_pbs_server = get_mapped_server(config, server)
    data_server, pbs_server = host_data_server, host_pbs_server
    server_info = get_server_info(config, data_server, source)

    # Only process environment if full-output (expensive)
    if args.f:
        process_env = True

        # If JSON output, need to read in header fields
        if args.F == "json":
            print("\n".join(json.dumps(server_info, indent = 4, separators=(', ', ':')).splitlines()[0:4]), end = "")
            global first_job
            first_job = True
    else:
        if not args.format:
            if args.a or args.u or args.s or args.n or args.T:
                if args.w:
                    args.format =  "{Job_Id:30} {Job_Owner:15} {queue:15} {Job_Name:15} {session_id:>8} "
                    args.format += "{Resource_List[nodect]:>4} {Resource_List[ncpus]:>5} {Resource_List[mem]:>6} "
                    if args.T:
                        args.format += "{Resource_List[walltime]:>5} {job_state:1} {estimated[start_time]}"
                    else:
                        args.format += "{Resource_List[walltime]:>5} {job_state:1} {resources_used[walltime]}"
                else:
                    args.format =  "{Job_Id:15} {Job_Owner:8} {queue:8} {Job_Name:10} {session_id:>6} "
                    args.format += "{Resource_List[nodect]:>3} {Resource_List[ncpus]:>3} {Resource_List[mem]:>6} "
                    if args.T:
                        args.format += "{Resource_List[walltime]:>5} {job_state:1} {estimated[start_time]:>5}"
                    else:
                        args.format += "{Resource_List[walltime]:>5} {job_state:1} {resources_used[walltime]:>5}"
            elif args.w:
                args.format =  "{Job_Id:30} {Job_Name:15} {Job_Owner:15} {resources_used[cput]:>8} "
                args.format += "{job_state:1} {queue:15}"
            else:
                args.format =  "{Job_Id:17} {Job_Name:16} {Job_Owner:16} {resources_used[cput]:>8} "
                args.format += "{job_state:1} {queue:16}"

    if args.filters:
        ids, subjobs = [], []

        for ft in args.filters:
            ft = ft.replace("@", ".")

            if "." in ft:
                ft_name, ft_server = ft.split(".")

                try:
                    ft_data_server, ft_pbs_server = get_mapped_server(config, ft_server)
                except IndexError:
                    continue
            else:
                ft_name = ft
                ft_data_server = host_data_server
                ft_pbs_server = host_pbs_server

            if ft_data_server != data_server:
                process_jobs(config, data_server, source, header, limit_user, args, ids, subjobs, process_env)
                header, ids = not args.noheader, []
                data_server = ft_data_server

            if ft_name and ft_name[0].isdigit():
                if args.t and ft_name.endswith("[]"):
                    ids.append(ft_name[:-2])
                else:
                    ids.append(f"{ft_name}.{ft_pbs_server}")

                    if "[" in ft_name:
                        subjobs.append(ids[-1])
            else:
                if ids:
                    process_jobs(config, data_server, source, header, limit_user, args, ids, subjobs, process_env)
                    header, ids = False, []

                for job_id, job_info in get_job_data(config, data_server, source, process_env):
                    if check_job(job_id, job_info, select_queue = f"{ft_name}@{ft_pbs_server}", filters = args):
                        print_job(job_id, job_info, args, header, limit_user)
                        header = False

        process_jobs(config, data_server, source, header, limit_user, args, ids, subjobs, process_env)
    else:
        for job_id, job_info in get_job_data(config, data_server, source, process_env):
            if check_job(job_id, job_info, select_queue = f"@{pbs_server}", filters = args):
                print_job(job_id, job_info, args, header, limit_user)
                header = False

    if args.f and args.F == "json":
        print("\n    }\n}")

    log_usage(config, "yes")

    if "QSCACHE_DEBUG" in os.environ:
        cache_date = datetime.fromtimestamp(server_info["timestamp"])
        print("\nCached at: {}".format(cache_date.strftime("%a %d %b %Y %I:%M:%S %p")), file = sys.stderr)

if __name__ == "__main__":
    main()
