#!/usr/bin/env python3

import sys, os, signal, time, argparse, subprocess, shutil, socket, random
from datetime import datetime
from timeit import default_timer as timer

def check_paths(config):
    for path in ["data", "temp", "logs"]:
        if path != "logs" or config["paths"][path]:
            if not os.path.isdir(config["paths"][path]):
                try:
                    os.makedirs(config["paths"][path])
                except OSError:
                    print("Error: configured {} path already exists and is not a directory".format(path), file = sys.stderr)
                    sys.exit(1)

def run_cache_cycle(config, server, cycle = "cache"):
    # Don't run if already running
    host_file = "{}/qscache-host.{}".format(config["paths"]["temp"], cycle)
    pid_file = "{}/qscache-pcpid.{}".format(config["paths"]["temp"], cycle)
    max_age = int(config[cycle]["maxage"])

    try:
        # If we are past the max age, then kill this cycle
        with open(pid_file, "r") as pf:
            pc_pid = pf.read()

        if not subprocess.call(("kill", "-0", pc_pid), stderr = subprocess.DEVNULL):
            pc_age = int(subprocess.check_output(("ps", "--noheaders", "-p", pc_pid, "-o", "etimes")))

            if pc_age >= max_age:
                os.kill(pc_pid, signal.SIGTERM)

                try:
                    os.remove(pid_file)
                    os.remove(host_file)
                except FileNotFoundError:
                    pass
        else:
            try:
                os.remove(pid_file)
                os.remove(host_file)
                shutil.rmtree("{}/qscache-{}".format(config["paths"]["temp"], pc_pid))
            except FileNotFoundError:
                pass

        sys.exit(0)
    except IOError:
        pass

    with open(host_file, "w") as hf:
        hf.write(socket.gethostname())

    cycle_temp = "{}/qscache-{}".format(config["paths"]["temp"], config["run"]["pid"])

    with open(pid_file, "w") as pf:
        pf.write(config["run"]["pid"])

    os.mkdir(cycle_temp)
    cycle_time = timer()

    pbs_args = [config["pbs"]["qstat"], "-t", "-f", "-Fdsv", r"-D\|-"]
    pbs_time = [config["pbs"]["qstat"], "1", "-f", "-Fjson"]

    if cycle == "history":
        pbs_args.append("-x")

    with open(f"{cycle_temp}/{cycle}", "w") as tf:
        if config["pbs"]["prefix"]:
            subprocess.run("{} {}".format(config["pbs"]["prefix"], " ".join(pbs_args)), shell = True, stdout = tf)
        else:
            subprocess.run(pbs_args, stdout = tf)

    with open(f"{cycle_temp}/{cycle}.age", "w") as uf:
        if config["pbs"]["prefix"]:
            subprocess.run("{} {}".format(config["pbs"]["prefix"], " ".join(pbs_time)), shell = True, stdout = uf, stderr = subprocess.DEVNULL)
        else:
            subprocess.run(pbs_time, stdout = uf, stderr = subprocess.DEVNULL)

    if "log" in config["run"]:
        timestamp = datetime.now().strftime("%H:%M:%S")

        with open(config["run"]["log"], "a") as lf:
            cycle_time = timer() - cycle_time
            lf.write("{:10} cycle={:9} type={:7} {:>10.2f} seconds\n".format(timestamp, config["run"]["pid"], cycle, cycle_time))

    shutil.move(f"{cycle_temp}/{cycle}", "{}/{}-{}.dat".format(config["paths"]["data"], server, cycle))
    shutil.move(f"{cycle_temp}/{cycle}.age", "{}/{}-{}.age".format(config["paths"]["data"], server, cycle))

    try:
        os.remove(pid_file)
        os.remove(host_file)
        shutil.rmtree(cycle_temp)
    except FileNotFoundError:
        pass

def main(remote = False, util_path = ""):
    my_root = os.path.dirname(os.path.realpath(__file__))
    from qscache.qscache import read_config

    arg_dict = { "--history"    : "run qstat with -x (expensive)" }

    parser = argparse.ArgumentParser(prog = "gen_data", description = "Generate data for jobs cache.")

    for arg in arg_dict:
        parser.add_argument(arg, help = arg_dict[arg], action = "store_true")

    args = parser.parse_args()

    try:
        server = os.environ["QSCACHE_SERVER"]
    except KeyError:
        server = "site"

    config = read_config("{}/cfg/{}.cfg".format(my_root, server), my_root, server)
    check_paths(config)

    if args.history:
        cycle = "history"
    else:
        cycle = "cache"

    if remote:
        if "Hosts" not in config["cache"]:
            print("Error: 'Hosts' key missing from cache settings; cannot use remote mode", file = sys.stderr)
            sys.exit(1)

        # If a cycle is running, make sure we go to the same host
        host_file = "{}/qscache-host.{}".format(config["paths"]["temp"], cycle)

        try:
            with open(host_file, "r") as hf:
                host = hf.read().rstrip("\n")
        except IOError:
            host = random.choice(config["cache"]["hosts"].split())

        # Call the regular gen_data script on the remote host
        status = subprocess.call(("ssh", host, "{}/gen_data {}".format(util_path, " ".join(sys.argv[1:]))))
    else:
        if config["paths"]["logs"]:
            config["run"]["log"] = "{}/PBS-{}-{}.log".format(config["paths"]["logs"], server.upper(),
                    datetime.now().strftime("%Y%m%d"))

        start_time = timer()
        cycle_freq = int(config[cycle]["frequency"])

        while (timer() - start_time) < 60:
            run_cache_cycle(config, server, cycle)

            if cycle_freq < 60:
                time.sleep(cycle_freq)
            else:
                break

if __name__ == "__main__":
    main()
