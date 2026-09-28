#!/usr/bin/env python3
"""Background GitHub collector for the Neon Sumi status line. Detached, never
prints; needs an authenticated `gh` CLI. Four modes:

  gh_poller.py repo <toplevel> <base>   PR + CI + ticket + board column for the
                                         branch checked out at <toplevel>. Writes
                                         <base>.gh.json, appends PR/CI transitions
                                         to <base>.events.
  gh_poller.py refs <owner/name> <n,n>  classifies #N mentions as PR / issue /
                                         ticket (an issue on a project board).
  gh_poller.py notifications            unread notifications (cockpit).
  gh_poller.py work                     your open PRs everywhere (cockpit).

WHERE THE TICKET NUMBER COMES FROM, in order: the PR's closing issue; the
branch name (`task/519-x`, `519-x`, `epic/206-x`); for the epic, the issue's
GraphQL parent, else a PR base named `epic/NNN-slug`.

Fail-safe: any error keeps last-good data, sets `error` and a backoff. The
renderer only reads the cache; nothing here is on the render path.
"""
import json
import os
import re
import subprocess
import sys
import time

HOME = os.path.expanduser("~")
GLOBAL_DIR = os.environ.get("NEON_SUMI_CACHE") or os.path.join(HOME, ".cache", "neon-sumi")
NOTIF_CACHE = os.path.join(GLOBAL_DIR, "notifications.json")
GH = "/usr/bin/gh" if os.path.exists("/usr/bin/gh") else "gh"
TIMEOUT = 10
LOCK_STEAL_SECS = 60
BACKOFF = 120
MAX_EVENTS = 40

RE_TICKET = re.compile(r"(?:^|/)(\d{1,6})[-_]")
RE_EPIC_BRANCH = re.compile(r"^epic/(\d{1,6})(?:[-_]|$)")

PR_QUERY = """
query($o:String!,$n:String!,$b:String!){repository(owner:$o,name:$n){
 pullRequests(headRefName:$b,first:1,orderBy:{field:UPDATED_AT,direction:DESC}){nodes{
  number title url state isDraft reviewDecision baseRefName
  closingIssuesReferences(first:3){nodes{number}}
  commits(last:1){nodes{commit{statusCheckRollup{state contexts(first:80){nodes{
   __typename ... on CheckRun{status conclusion} ... on StatusContext{state}}}}}}}
 }}}}"""

ISSUE_FIELDS = """number title state url issueType{name}
 projectItems(first:3){nodes{project{title url}
  fieldValueByName(name:"Status"){... on ProjectV2ItemFieldSingleSelectValue{name}}}}"""


def issue_query(with_task, with_epic):
    parts = []
    if with_task:
        parts.append("t:issue(number:$t){%s parent{%s}}" % (ISSUE_FIELDS, ISSUE_FIELDS))
    if with_epic:
        parts.append("e:issue(number:$e){%s}" % ISSUE_FIELDS)
    vars_ = "$o:String!,$n:String!" + (",$t:Int!" if with_task else "") + (",$e:Int!" if with_epic else "")
    return "query(%s){repository(owner:$o,name:$n){%s}}" % (vars_, " ".join(parts))


# ── pure helpers (unit-tested) ─────────────────────────────────────────────────
def ticket_from_branch(branch):
    """-> (task_number|None, epic_number|None) from the branch name alone."""
    m = RE_EPIC_BRANCH.match(branch or "")
    if m:
        return None, int(m.group(1))
    m = RE_TICKET.search(branch or "")
    return (int(m.group(1)) if m else None), None


def epic_from_base(base):
    m = RE_EPIC_BRANCH.match(base or "")
    return int(m.group(1)) if m else None


def ci_counts(rollup):
    FAIL = {"FAILURE", "TIMED_OUT", "ACTION_REQUIRED", "STARTUP_FAILURE", "ERROR"}
    SKIP = {"SKIPPED", "NEUTRAL", "CANCELLED", "STALE"}
    c = {"pass": 0, "run": 0, "fail": 0, "skip": 0, "total": 0}
    for n in ((rollup or {}).get("contexts") or {}).get("nodes") or []:
        c["total"] += 1
        if n.get("__typename") == "StatusContext":
            st = (n.get("state") or "").upper()
            c["pass" if st == "SUCCESS" else "fail" if st in FAIL else "run"] += 1
        elif (n.get("status") or "").upper() != "COMPLETED":
            c["run"] += 1
        else:
            con = (n.get("conclusion") or "").upper()
            c["fail" if con in FAIL else "skip" if con in SKIP else "pass"] += 1
    return c


def pr_digest(node):
    if not node:
        return None
    commits = (node.get("commits") or {}).get("nodes") or []
    rollup = ((commits[0] if commits else {}).get("commit") or {}).get("statusCheckRollup")
    closing = [x.get("number") for x in ((node.get("closingIssuesReferences") or {}).get("nodes") or [])]
    return {"number": node.get("number"), "title": node.get("title") or "", "url": node.get("url") or "",
            "state": node.get("state") or "", "draft": bool(node.get("isDraft")),
            "review": node.get("reviewDecision") or "", "base": node.get("baseRefName") or "",
            "closing": [n for n in closing if isinstance(n, int)], "ci": ci_counts(rollup)}


def issue_digest(node):
    if not node:
        return None
    status, board, board_url = "", "", ""
    for item in ((node.get("projectItems") or {}).get("nodes") or []):
        fv = item.get("fieldValueByName") or {}
        if fv.get("name"):
            status = fv["name"]
            board = ((item.get("project") or {}).get("title")) or ""
            board_url = ((item.get("project") or {}).get("url")) or ""
            break
    return {"number": node.get("number"), "title": node.get("title") or "", "url": node.get("url") or "",
            "state": node.get("state") or "", "type": ((node.get("issueType") or {}).get("name")) or "",
            "status": status, "board": board, "board_url": board_url}


def transitions(prev, new):
    """Event lines for genuine PR/CI transitions between two cache payloads."""
    out = []
    p, n = (prev or {}).get("pr") or {}, (new or {}).get("pr") or {}
    if not n:
        return out
    num = n.get("number")
    if p.get("number") != num:
        out.append("PR #%s opened%s" % (num, " (draft)" if n.get("draft") else ""))
        p = {}
    if p.get("draft") and not n.get("draft"):
        out.append("PR #%s ready for review" % num)
    pc, nc = p.get("ci") or {}, n.get("ci") or {}
    if nc.get("fail", 0) and nc.get("fail") != pc.get("fail", 0):
        out.append("CI ✗ %d failed (%d ok)" % (nc["fail"], nc.get("pass", 0)))
    was_green = pc.get("total", 0) and not pc.get("run", 0) and not pc.get("fail", 0)
    if nc.get("total", 0) and not nc.get("run", 0) and not nc.get("fail", 0) and not was_green:
        out.append("CI ✓ passed %d/%d" % (nc.get("pass", 0), nc["total"]))
    if n.get("review") != p.get("review"):
        if n.get("review") == "APPROVED":
            out.append("PR #%s approved ✓" % num)
        elif n.get("review") == "CHANGES_REQUESTED":
            out.append("PR #%s changes requested" % num)
    if n.get("state") != p.get("state") and p.get("state"):
        if n.get("state") == "MERGED":
            out.append("PR #%s merged" % num)
        elif n.get("state") == "CLOSED":
            out.append("PR #%s closed" % num)
    return out


def web_url(api_url, kind):
    """api.github.com/repos/o/r/pulls/7 -> github.com/o/r/pull/7."""
    m = re.match(r"https://api\.github\.com/repos/([^/]+/[^/]+)/(pulls|issues|commits|releases)/(\w+)", api_url or "")
    if not m:
        return ""
    seg = {"pulls": "pull", "issues": "issues", "commits": "commit", "releases": "releases"}[m.group(2)]
    return "https://github.com/%s/%s/%s" % (m.group(1), seg, m.group(3))


def notif_digest(items):
    out = []
    for it in items or []:
        subj = it.get("subject") or {}
        repo = (it.get("repository") or {}).get("full_name") or ""
        url = web_url(subj.get("url"), subj.get("type")) or (
            "https://github.com/%s" % repo if repo else "https://github.com/notifications")
        out.append({"title": subj.get("title") or "", "type": subj.get("type") or "", "repo": repo,
                    "reason": it.get("reason") or "", "url": url, "updated": it.get("updated_at") or ""})
    return out


# ── io ─────────────────────────────────────────────────────────────────────────
def read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "%s.tmp.%d" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, separators=(",", ":"))
    os.replace(tmp, path)


def lock(path):
    try:
        os.mkdir(path)
        return True
    except FileExistsError:
        try:
            if time.time() - os.stat(path).st_mtime < LOCK_STEAL_SECS:
                return False
            os.rmdir(path)
            os.mkdir(path)
            return True
        except OSError:
            return False
    except OSError:
        return False


def gh(args, cwd=None):
    p = subprocess.run([GH] + args, cwd=cwd, capture_output=True, text=True, timeout=TIMEOUT)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or "gh failed").strip().splitlines()[-1][:80] if p.stderr else "gh failed")
    return p.stdout


def graphql(query, **variables):
    args = ["api", "graphql", "-f", "query=" + query]
    for k, v in variables.items():
        args += ["-F" if isinstance(v, int) else "-f", "%s=%s" % (k, v)]
    data = json.loads(gh(args))
    return (data.get("data") or {}).get("repository") or {}


def slug_of(top):
    try:
        url = subprocess.run(["git", "-C", top, "remote", "get-url", "origin"], capture_output=True,
                             text=True, timeout=3).stdout.strip()
    except Exception:
        return ""
    s = re.sub(r"^(git@[^:]+:|ssh://[^/]+/|https?://[^/]+/)", "", url)
    s = re.sub(r"\.git$", "", s).strip("/")
    return s if s.count("/") == 1 else ""


def append_events(path, lines, now):
    if not lines:
        return
    try:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                old = fh.read().splitlines()
        except OSError:
            old = []
        old += ["%d\t%s" % (now, ln) for ln in lines]
        tmp = "%s.tmp.%d" % (path, os.getpid())
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write("\n".join(old[-MAX_EVENTS:]) + "\n")
        os.replace(tmp, path)
    except Exception:
        pass


# ── modes ──────────────────────────────────────────────────────────────────────
def run_repo(top, base):
    cache_path = base + ".gh.json"
    lk = base + ".gh.lock"
    if not lock(lk):
        return
    try:
        now = int(time.time())
        prev = read_json(cache_path)
        if prev.get("backoff_until", 0) > now:
            return
        prev["last_attempt"] = now
        write_json(cache_path, prev)
        try:
            branch = subprocess.run(["git", "-C", top, "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True,
                                    text=True, timeout=3).stdout.strip()
            slug = slug_of(top)
            if not slug or not branch or branch == "HEAD":
                raise RuntimeError("no slug/branch")
            owner, name = slug.split("/")
            repo = graphql(PR_QUERY, o=owner, n=name, b=branch)
            nodes = ((repo.get("pullRequests") or {}).get("nodes")) or []
            pr = pr_digest(nodes[0] if nodes else None)
            task_n, epic_n = ticket_from_branch(branch)
            if pr and pr["closing"]:
                task_n = pr["closing"][0]
            if epic_n is None and pr:
                epic_n = epic_from_base(pr["base"])
            task = epic = None
            if task_n or epic_n:
                q = issue_query(bool(task_n), bool(epic_n))
                kw = {"o": owner, "n": name}
                if task_n:
                    kw["t"] = task_n
                if epic_n:
                    kw["e"] = epic_n
                data = graphql(q, **kw)
                t = data.get("t")
                task = issue_digest(t)
                if t and t.get("parent"):
                    epic = issue_digest(t["parent"])
                if not epic:
                    epic = issue_digest(data.get("e"))
                if task and task["type"].lower() == "epic" and not epic:
                    task, epic = None, task
            new = {"fetched_at": now, "last_attempt": now, "backoff_until": 0, "error": None,
                   "slug": slug, "branch": branch, "pr": pr, "task": task, "epic": epic}
        except Exception as exc:
            prev["error"] = str(exc)[:80] or type(exc).__name__
            prev["backoff_until"] = now + BACKOFF
            write_json(cache_path, prev)
            return
        if prev.get("branch") == new["branch"]:
            append_events(base + ".events", transitions(prev, new), now)
        write_json(cache_path, new)
    finally:
        try:
            os.rmdir(lk)
        except OSError:
            pass


def run_notifications():
    lk = os.path.join(GLOBAL_DIR, ".notifications.lock")
    os.makedirs(GLOBAL_DIR, exist_ok=True)
    if not lock(lk):
        return
    try:
        now = int(time.time())
        prev = read_json(NOTIF_CACHE)
        if prev.get("backoff_until", 0) > now:
            return
        prev["last_attempt"] = now
        write_json(NOTIF_CACHE, prev)
        try:
            raw = gh(["api", "-i", "notifications?per_page=50"])
            head, _, body = raw.partition("\r\n\r\n") if "\r\n\r\n" in raw else raw.partition("\n\n")
            m = re.search(r"(?im)^x-poll-interval:\s*(\d+)", head)
            items = json.loads(body or "[]")
            if not isinstance(items, list):
                raise ValueError("shape")
        except Exception as exc:
            prev["error"] = str(exc)[:80] or type(exc).__name__
            prev["backoff_until"] = now + BACKOFF
            write_json(NOTIF_CACHE, prev)
            return
        write_json(NOTIF_CACHE, {"fetched_at": now, "last_attempt": now, "backoff_until": 0, "error": None,
                                 "poll_interval": int(m.group(1)) if m else 60,
                                 "count": len(items), "items": notif_digest(items)[:20]})
    finally:
        try:
            os.rmdir(lk)
        except OSError:
            pass


REFS_DIR = os.path.join(GLOBAL_DIR, "refs")


def refs_cache_path(slug):
    return os.path.join(REFS_DIR, slug.replace("/", "__") + ".json")


def ref_digest(node):
    """issueOrPullRequest node -> {kind: pr|issue|ticket, ...}. A ticket is an issue
    that sits on a project board (has a Status); the column rides along."""
    if not node:
        return {"kind": "missing"}
    if node.get("__typename") == "PullRequest":
        state = "DRAFT" if node.get("isDraft") and node.get("state") == "OPEN" else node.get("state") or ""
        return {"kind": "pr", "title": node.get("title") or "", "url": node.get("url") or "", "state": state}
    d = issue_digest(node) or {}
    return {"kind": "ticket" if d.get("status") else "issue", "title": d.get("title", ""), "url": d.get("url", ""),
            "state": d.get("state", ""), "status": d.get("status", ""), "board": d.get("board", ""),
            "board_url": d.get("board_url", "")}


def run_refs(slug, numbers):
    """Classify #N mentions as PR / issue / board ticket. One GraphQL call for the
    batch; a number that does not exist comes back null next to the others, and
    gh exits non-zero for it, so stdout is parsed whatever the exit code."""
    owner, _, name = slug.partition("/")
    nums = sorted({int(n) for n in numbers.split(",") if n.isdigit()})[:12]
    if not owner or not name or not nums:
        return
    path = refs_cache_path(slug)
    lk = path + ".lock"
    os.makedirs(REFS_DIR, exist_ok=True)
    if not lock(lk):
        return
    try:
        now = int(time.time())
        cache = read_json(path)
        cache["last_attempt"] = now
        write_json(path, cache)
        body = " ".join("r%d:issueOrPullRequest(number:%d){__typename ... on Issue{%s} "
                        "... on PullRequest{number title url state isDraft}}" % (n, n, ISSUE_FIELDS) for n in nums)
        query = 'query{repository(owner:"%s",name:"%s"){%s}}' % (owner, name, body)
        p = subprocess.run([GH, "api", "graphql", "-f", "query=" + query], capture_output=True, text=True,
                           timeout=TIMEOUT)
        try:
            repo = (json.loads(p.stdout or "{}").get("data") or {}).get("repository")
        except ValueError:
            repo = None
        if repo is None:
            cache["error"] = ((p.stderr or "gh failed").strip().splitlines() or ["gh failed"])[-1][:80]
            cache["backoff_until"] = now + BACKOFF
            write_json(path, cache)
            return
        items = cache.get("items") or {}
        for n in nums:
            d = ref_digest(repo.get("r%d" % n))
            d["fetched_at"] = now
            items[str(n)] = d
        write_json(path, {"last_attempt": now, "backoff_until": 0, "error": None, "items": items})
    finally:
        try:
            os.rmdir(lk)
        except OSError:
            pass


WORK_CACHE = os.path.join(GLOBAL_DIR, "work.json")


def run_work():
    """Every open PR you authored, on any repo: the cockpit's work block."""
    lk = os.path.join(GLOBAL_DIR, ".work.lock")
    os.makedirs(GLOBAL_DIR, exist_ok=True)
    if not lock(lk):
        return
    try:
        now = int(time.time())
        prev = read_json(WORK_CACHE)
        if prev.get("backoff_until", 0) > now:
            return
        prev["last_attempt"] = now
        write_json(WORK_CACHE, prev)
        try:
            prs = json.loads(gh(["search", "prs", "--author", "@me", "--state", "open", "--limit", "100",
                                 "--json", "repository,number,title,url,updatedAt"]))
            if not isinstance(prs, list):
                raise ValueError("shape")
        except Exception as exc:
            prev["error"] = str(exc)[:80] or type(exc).__name__
            prev["backoff_until"] = now + BACKOFF
            write_json(WORK_CACHE, prev)
            return
        write_json(WORK_CACHE, {"fetched_at": now, "last_attempt": now, "backoff_until": 0, "error": None,
                                "prs": [{"repo": (p.get("repository") or {}).get("nameWithOwner") or "",
                                         "number": p.get("number"), "title": p.get("title") or "",
                                         "url": p.get("url") or "", "updated": p.get("updatedAt") or ""} for p in prs]})
    finally:
        try:
            os.rmdir(lk)
        except OSError:
            pass


def main(argv):
    if len(argv) >= 3 and argv[0] == "repo":
        run_repo(argv[1], argv[2])
    elif len(argv) >= 3 and argv[0] == "refs":
        run_refs(argv[1], argv[2])
    elif argv and argv[0] == "notifications":
        run_notifications()
    elif argv and argv[0] == "work":
        run_work()


if __name__ == "__main__":
    try:
        sys.stdout = open(os.devnull, "w")
        sys.stderr = open(os.devnull, "w")
        main(sys.argv[1:])
    except Exception:
        pass
    finally:
        sys.exit(0)
