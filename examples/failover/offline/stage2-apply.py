"""Stage 2, part 2 for the offline BIG-IP pair: apply the Declarative Onboarding and Cloud Failover declarations that stage 1 skipped.

Run it AFTER stage2-license.py has licensed BOTH units (an unlicensed unit rejects the declaration). It needs to reach both management
addresses over SSH (port 22) and nothing else: no internet. Requests are made by SSH-ing to each unit and calling its REST API on localhost.

It reads the two runtime-init YAML files from this repository (instance 01 and instance 02), removes the `License` class (the units are already
licensed), fills in the {{{PLACEHOLDERS}}} from the arguments below, and posts the declarations in order:
  unit 01: DO declaration (network, routes, hostname, admin password), then the CFE declaration
  unit 02: DO declaration (network, routes, hostname, admin password, config sync, failover, device group, trust to unit 01), then the CFE declaration
It waits for each DO task to finish and prints the result.

Usage:
  stage2-apply.py --yaml-dir examples/failover/bigip-configurations --password-file pw.txt \
     --mgmt1 10.0.0.11 --mgmt2 10.0.0.12 --self1 10.0.1.11 --self2 10.0.1.12 \
     --mgmt-gw 10.0.0.1 --internal-gw 10.0.1.1 [--host1 failover01.local --host2 failover02.local --tag bigip_high_availability_solution]
Needs: python3 and PyYAML (pip install pyyaml) on the machine that runs it.
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import time

import yaml

NL = chr(10)
KEYFILE = None
PASSWORD = ""


def call(host, auth, path, body=None, method=None, timeout=120):
    """Send one REST request to the unit by SSH-ing in and running curl against localhost (no remote REST login needed).
    `auth` is unused here and kept so callers do not change."""
    verb = method or ("POST" if body is not None else "GET")
    script = ""
    if body is not None:
        script += "cat > /tmp/stage2-body.json <<'STAGE2EOF'" + NL + json.dumps(body) + NL + "STAGE2EOF" + NL
    q = chr(39)
    pwq = q + PASSWORD.replace(q, q + chr(92) + q + q) + q
    script += "curl -sk -u admin:%s -X %s -H 'Content-Type: application/json' %s -w '%s%%{http_code}' https://localhost%s" % (
        pwq, verb, "-d @/tmp/stage2-body.json" if body is not None else "", NL + "HTTP:", path) + NL
    script += "rm -f /tmp/stage2-body.json" + NL
    r = subprocess.run(["ssh", "-i", KEYFILE, "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null", "-o", "LogLevel=ERROR",
                        "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", "admin@" + host, "bash", "-s"], capture_output=True, text=True, timeout=timeout, input=script)
    out = r.stdout or ""
    code = 0
    if "HTTP:" in out:
        out, _, c = out.rpartition("HTTP:")
        code = int(c.strip() or 0)
    try:
        return code, json.loads(out) if out.strip() else {}
    except Exception:
        return code, {"raw": (out or r.stderr)[:300]}


def fill(node, values):
    """Replace {{{NAME}}} placeholders in every string of a nested structure."""
    if isinstance(node, dict):
        return {k: fill(v, values) for k, v in node.items()}
    if isinstance(node, list):
        return [fill(v, values) for v in node]
    if isinstance(node, str):
        for k, v in values.items():
            node = node.replace("{{{%s}}}" % k, v)
        return node
    return node


def declarations(path):
    doc = yaml.safe_load(open(path, encoding="utf-8"))
    out = []
    for op in doc["extension_services"]["service_operations"]:
        val = op["value"]
        if op["extensionType"] == "do":
            val = json.loads(json.dumps(val))
            val["Common"].pop("My_License", None)   # units were licensed by stage2-license.py
        out.append((op["extensionType"], val))
    return out


def wait_do(host, auth, task_id, label):
    for _ in range(90):
        code, body = call(host, auth, "/mgmt/shared/declarative-onboarding/task/%s" % task_id)
        res = body.get("result", {})
        status = res.get("status")
        if status in ("OK", "ERROR", "ROLLBACK") or body.get("status") in ("OK", "ERROR"):
            return res.get("status") or body.get("status"), res.get("message") or body.get("message"), body
        time.sleep(10)
    return "TIMEOUT", "no final status after 15 minutes", {}


def apply_unit(host, auth, decls, label):
    for kind, val in decls:
        if kind == "do":
            code, body = call(host, auth, "/mgmt/shared/declarative-onboarding", val)
            if code not in (200, 202):
                print("[%s] DO post failed: HTTP %s %s" % (label, code, json.dumps(body)[:300]))
                return False
            task = body.get("id")
            status, msg, full = wait_do(host, auth, task, label)
            print("[%s] DO task %s: %s %s" % (label, (task or "")[:8], status, msg or ""))
            if status != "OK":
                print("[%s] errors: %s" % (label, json.dumps(full.get("result", {}).get("errors", full.get("errors")))[:400]))
                return False
        else:
            # CFE retries its Azure calls before it answers; with no path to Azure that takes minutes, so do not wait for the reply: send it, then read the declaration back.
            try:
                code, body = call(host, auth, "/mgmt/shared/cloud-failover/declare", val, timeout=40)
                print("[%s] CFE declare: HTTP %s %s" % (label, code, (body.get("message") or body.get("status") or "")))
            except subprocess.TimeoutExpired:
                print("[%s] CFE declare: no reply within 40 s (expected when the unit cannot reach Azure); reading it back" % label)
                time.sleep(5)
            code, body = call(host, auth, "/mgmt/shared/cloud-failover/declare", timeout=60)
            ok = code == 200 and body.get("message") == "success"
            print("[%s] CFE declaration stored: %s" % (label, "yes" if ok else "NO (HTTP %s)" % code))
            if not ok:
                return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--yaml-dir", required=True)
    ap.add_argument("--password-file", required=True)
    ap.add_argument("--ssh-key", required=True, help="private key for the deployment sshKey; requests are sent over SSH to localhost on each unit")
    for n in ("mgmt1", "mgmt2", "self1", "self2", "mgmt-gw", "internal-gw"):
        ap.add_argument("--" + n, required=True)
    ap.add_argument("--host1", default="failover01.local")
    ap.add_argument("--host2", default="failover02.local")
    ap.add_argument("--tag", default="bigip_high_availability_solution")
    ap.add_argument("--prefix-len", default="24", help="prefix length of the internal subnet, added to the self IPs (DO needs address/length)")
    ap.add_argument("--user", default="admin")
    a = ap.parse_args()
    global KEYFILE, PASSWORD
    pw = open(a.password_file).read().strip()
    KEYFILE, PASSWORD = a.ssh_key, pw
    auth = "Basic " + base64.b64encode(("%s:%s" % (a.user, pw)).encode()).decode()

    common = {"MGMT_GW": a.mgmt_gw, "DEFAULT_GW": a.internal_gw, "BIGIP_PASSWORD": pw, "FAILOVER_TAG": a.tag}
    cidr = lambda ip: ip if "/" in ip else "%s/%s" % (ip, a.prefix_len)   # the metadata service gives address/length; plain addresses get the prefix added
    v1 = dict(common, HOST_NAME=a.host1, SELF_IP_INTERNAL=cidr(a.self1), REMOTE_HOST_NAME=a.host2, REMOTE_HOST="")
    v2 = dict(common, HOST_NAME=a.host2, SELF_IP_INTERNAL=cidr(a.self2), REMOTE_HOST_NAME=a.host1, REMOTE_HOST=a.self1)
    d1 = [(k, fill(v, v1)) for k, v in declarations(os.path.join(a.yaml_dir, "runtime-init-conf-2nic-byol-instance01.yaml"))]
    d2 = [(k, fill(v, v2)) for k, v in declarations(os.path.join(a.yaml_dir, "runtime-init-conf-2nic-byol-instance02.yaml"))]

    for host, label in ((a.mgmt1, "unit 01"), (a.mgmt2, "unit 02")):
        code, body = call(host, auth, "/mgmt/tm/sys/license")
        if code != 200:
            print("[%s] cannot read the licence (HTTP %s): is the admin password set and the unit reachable? Run stage2-license.py first." % (label, code))
            return 1

    if not apply_unit(a.mgmt1, auth, d1, "unit 01"):
        return 2
    if not apply_unit(a.mgmt2, auth, d2, "unit 02"):
        return 3
    print("both units configured; check the pair with: GET /mgmt/tm/cm/sync-status and /mgmt/tm/cm/failover-status on either unit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
