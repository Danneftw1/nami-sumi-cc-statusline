#!/usr/bin/env python3
"""Background collector: which localhost ports are listening, for which repo,
and which of them actually serve a page. Detached, never prints.

Writes ~/.cache/neon-sumi/ports.json:
  {"fetched_at", "last_attempt", "ports": [{port, owner, service, project, dir, http}]}

`http` is the status a GET / returned (0 = no answer). The status line only
makes a port clickable when that is 2xx or 3xx: most listeners on a laptop
(AirPlay, sync daemons, editor bridges, proxies) answer 403/404/407 or nothing,
and a link to an error page is worse than no link. Each (port, pid) is probed
once and re-checked every PROBE_TTL seconds.

Sources: `docker ps` for published container ports (compose labels name the
project), then `lsof` (macOS) or `ss` (Linux) for everything else; a process's
working directory maps it to a repo.
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

HOME = os.path.expanduser("~")
CACHE_DIR = os.environ.get("NEON_SUMI_CACHE") or os.path.join(HOME, ".cache", "neon-sumi")
CACHE = os.path.join(CACHE_DIR, "ports.json")
LOCK = os.path.join(CACHE_DIR, ".ports.lock")
TIMEOUT = 5
PROBE_TIMEOUT = 0.4
PROBE_TTL = 60
SKIP_PORTS = {53}
SEP = "\x1f"
DOCKER_FMT = SEP.join(["{{.Names}}", "{{.Ports}}", "{{.Image}}", '{{.Label "com.docker.compose.project"}}',
                       '{{.Label "com.docker.compose.project.working_dir"}}'])
RE_PUBLISHED = re.compile(r"(?:[\d.]+|\[::\]):(\d+)(?:-(\d+))?->(\d+)(?:-\d+)?/tcp")
RE_SS = re.compile(r"^LISTEN\s+\S+\s+\S+\s+(\S+):(\d+)\s+\S+(?:\s+users:\(\(\"([^\"]+)\",pid=(\d+))?")


# ── pure helpers ───────────────────────────────────────────────────────────────
def project_for_dir(path):
    """Directory -> (label, dir): the git repo it sits in, else its own name."""
    if not path or path == "/":
        return "", path or ""
    p = os.path.normpath(path)
    probe = p
    for _ in range(12):
        if os.path.exists(os.path.join(probe, ".git")):
            name = os.path.basename(probe)
            if "/worktrees/" in p:
                name += " wt:" + p.rstrip("/").split("/worktrees/")[-1].split("/")[0]
            return name, probe
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    return os.path.basename(p), p


def parse_docker(text):
    out = {}
    for line in (text or "").splitlines():
        f = line.split(SEP)
        if len(f) < 5:
            continue
        name, ports, image, cproj, wdir = f[:5]
        project, directory = project_for_dir(wdir)
        for m in RE_PUBLISHED.finditer(ports):
            lo = int(m.group(1))
            for port in range(lo, int(m.group(2) or lo) + 1):
                out.setdefault(port, {"port": port, "owner": "docker", "service": image.split("/")[-1].split(":")[0] or name,
                                      "project": project or cproj or name, "dir": directory})
    return out


def parse_ss(text):
    out = []
    for line in (text or "").splitlines():
        m = RE_SS.match(line.strip())
        if m and int(m.group(2)) not in SKIP_PORTS:
            out.append((int(m.group(2)), m.group(3), int(m.group(4)) if m.group(4) else None))
    return out


def parse_lsof(text):
    """`lsof -nP -iTCP -sTCP:LISTEN -Fpcn` -> [(port, command, pid)], one per port."""
    out, seen, pid, cmd = [], set(), None, None
    for line in (text or "").splitlines():
        tag, val = line[:1], line[1:]
        if tag == "p":
            pid = int(val) if val.isdigit() else None
        elif tag == "c":
            cmd = val
        elif tag == "n" and ":" in val:
            port = val.rsplit(":", 1)[1]
            if port.isdigit() and int(port) not in seen and int(port) not in SKIP_PORTS:
                seen.add(int(port))
                out.append((int(port), cmd, pid))
    return out


def pid_cwds(pids):
    """{pid: working directory}: /proc on Linux; on macOS ONE lsof for every pid
    (one per pid cost ~30 ms each)."""
    out = {}
    if sys.platform != "darwin":
        for pid in pids:
            try:
                out[pid] = os.readlink("/proc/%d/cwd" % pid)
            except OSError:
                pass
        return out
    if not pids:
        return out
    pid = None
    for line in run(["lsof", "-a", "-d", "cwd", "-p", ",".join(str(p) for p in sorted(pids)), "-Fpn"]).splitlines():
        if line.startswith("p") and line[1:].isdigit():
            pid = int(line[1:])
        elif line.startswith("n") and pid is not None:
            out[pid] = line[1:]
    return out


def merge(listeners, docker_map, cwds):
    ports = dict(docker_map)
    for port, cmd, pid in listeners:
        if port in ports:
            continue
        entry = {"port": port, "owner": "proc" if pid else "?", "service": cmd or "", "project": "", "dir": "", "pid": pid}
        cwd = cwds.get(pid)
        if cwd:
            entry["project"], entry["dir"] = project_for_dir(cwd)
        ports[port] = entry
    return [ports[p] for p in sorted(ports)]


# ── io ─────────────────────────────────────────────────────────────────────────
def run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT).stdout
    except Exception:
        return ""


NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def probe(port):
    """HTTP status of GET / on localhost:port, 0 when nothing answers."""
    req = urllib.request.Request("http://127.0.0.1:%d/" % port, headers={"User-Agent": "neon-sumi-probe"})
    try:
        with NO_PROXY.open(req, timeout=PROBE_TIMEOUT) as resp:
            return int(resp.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)
    except Exception:
        return 0


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "%s.tmp.%d" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, separators=(",", ":"))
    os.replace(tmp, path)


def main():
    os.makedirs(CACHE_DIR, exist_ok=True)
    try:
        os.mkdir(LOCK)
    except FileExistsError:
        try:
            if time.time() - os.stat(LOCK).st_mtime < 30:
                return
        except OSError:
            return
    except OSError:
        return
    try:
        now = int(time.time())
        try:
            with open(CACHE, "r", encoding="utf-8") as fh:
                prev = json.load(fh)
        except Exception:
            prev = {}
        prev["last_attempt"] = now
        write_json(CACHE, prev)
        docker = parse_docker(run(["docker", "ps", "--format", DOCKER_FMT]))
        if sys.platform == "darwin":
            listeners = parse_lsof(run(["lsof", "-nP", "-iTCP", "-sTCP:LISTEN", "-Fpcn"]))
        else:
            listeners = parse_ss(run(["ss", "-ltnpH"]))
        ports = merge(listeners, docker, pid_cwds({pid for port, _, pid in listeners if pid and port not in docker}))
        known = {(p.get("port"), p.get("pid")): p for p in prev.get("ports") or []}
        for p in ports:
            old = known.get((p["port"], p.get("pid")))
            if old and now - (old.get("probed_at") or 0) < PROBE_TTL:
                p["http"], p["probed_at"] = old.get("http", 0), old.get("probed_at")
            else:
                p["http"], p["probed_at"] = probe(p["port"]), now
        write_json(CACHE, {"fetched_at": now, "last_attempt": now, "ports": ports})
    finally:
        try:
            os.rmdir(LOCK)
        except OSError:
            pass


if __name__ == "__main__":
    try:
        sys.stdout = open(os.devnull, "w")
        sys.stderr = open(os.devnull, "w")
        main()
    except Exception:
        pass
    finally:
        sys.exit(0)
