"""Stage 2 for the offline BIG-IP pair: licence one unit WITHOUT giving the BIG-IP any internet path.

Runs on any machine that can reach the unit's MANAGEMENT address over SSH (port 22) and, for --auto, can reach activate.f5.com.
A unit that has never run a Declarative Onboarding declaration has NO admin password yet (DO sets it), so this script logs in over SSH with the
deployment's SSH key (the key whose public half you gave the template as `sshKey`) and sets the admin password itself from --password-file.
  1. Reads the unit's dossier over SSH (`get_dossier -b <regkey>`).
  2. Gets the licence text from activate.f5.com: --auto posts the dossier itself; --manual prints the dossier and the URL
     and waits for you to paste the returned licence text (use this when this machine has no internet; do the web step on another machine).
  3. Installs the licence on the unit (writes /config/bigip.license, then `reloadlic`) and waits until the unit reports licensed.
Nothing here prints the admin password.

Usage:
  stage2-license.py --host 10.0.0.11 --regkey XXXXX-XXXXX-XXXXX-XXXXX-XXXXXXX --ssh-key ~/.ssh/id_rsa --password-file pw.txt [--auto | --manual]
"""
import argparse
import base64
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request

NL = chr(10)


def ssh(host, keyfile, cmd, user="admin", timeout=180):
    """Run a command on the unit through SSH. The admin login shell on BIG-IP is tmsh, so the command text is sent on stdin to `bash -s`."""
    r = subprocess.run(["ssh", "-i", keyfile, "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null", "-o", "ConnectTimeout=20",
                        "-o", "LogLevel=ERROR", "-o", "BatchMode=yes", "%s@%s" % (user, host), "bash", "-s"], capture_output=True, text=True, timeout=timeout, input=cmd + NL)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def licensed(host, keyfile):
    rc, out = ssh(host, keyfile, "tmsh show sys license 2>&1 | head -6")
    low = out.lower()   # the unit prints "Registration key" (lower-case k)
    return rc == 0 and ("registration key" in low or "licensed version" in low)


def _multipart(fields, boundary):
    crlf = chr(13) + chr(10)
    parts = []
    for name, value in fields:
        parts.append("--%s%sContent-Disposition: form-data; name=\"%s\"%s%s%s%s" % (boundary, crlf, name, crlf, crlf, value, crlf))
    parts.append("--%s%sContent-Disposition: form-data; name=\"file\"; filename=\"\"%sContent-Type: application/octet-stream%s%s%s--%s--%s" % (boundary, crlf, crlf, crlf, crlf, crlf, boundary, crlf))
    return "".join(parts).encode()


def fetch_license_online(dossier, accept_terms=False):
    """Post the dossier to activate.f5.com the way the web form does and return the licence text.
    The site may show an End User Legal Agreement before the licence. It is accepted ONLY when accept_terms is True (the --accept-terms option),
    because agreeing to F5's terms is the decision of whoever runs this, not of the script."""
    import http.cookiejar
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    ua = {"User-Agent": "Mozilla/5.0"}
    page = opener.open(urllib.request.Request("https://activate.f5.com/license/dossier.jsp", headers=ua), timeout=60).read().decode("utf-8", "replace")
    action = re.search(r'<form[^>]*name="licenseForm"[^>]*action="([^"]+)"', page).group(1)
    url = urllib.parse.urljoin("https://activate.f5.com/license/", action)
    boundary = "----stage2boundary"
    req = urllib.request.Request(url, data=_multipart((("dossier", dossier), ("ipAddress", ""), ("submit", "Next")), boundary),
                                 headers=dict(ua, **{"Content-Type": "multipart/form-data; boundary=" + boundary}))
    html = opener.open(req, timeout=90).read().decode("utf-8", "replace")
    for _ in range(3):
        m = re.search(r"<textarea[^>]*>(.*?)</textarea>", html, re.S | re.I)
        if m and "Registration Key" in m.group(1):
            return m.group(1).replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&").strip()
        form = re.search(r'<form[^>]*action="([^"]*accepteula[^"]*)"', html, re.I)
        if form and 'name="eula_agree"' in html:
            if not accept_terms:
                raise RuntimeError("activate.f5.com is asking you to agree to the F5 Platform Terms of Use. Read them at https://activate.f5.com/license/dossier.jsp and rerun with --accept-terms if you agree, or use --manual and accept in a browser.")
            eurl = urllib.parse.urljoin("https://activate.f5.com/license/", form.group(1))
            # post back every field the agreement form carries (the terms text and the dossier it echoes) plus the checkbox, as a browser does
            fields = [(n, v.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&").replace("&quot;", chr(34)))
                      for n, v in re.findall(r'<textarea[^>]*name="([^"]+)"[^>]*>(.*?)</textarea>', html, re.S | re.I)]
            fields += [("eula_agree", "on"), ("submit", "Next")]
            body = urllib.parse.urlencode(fields).encode()
            html = opener.open(urllib.request.Request(eurl, data=body, headers=dict(ua, **{"Content-Type": "application/x-www-form-urlencoded"})), timeout=90).read().decode("utf-8", "replace")
            continue
        break
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>", "", html, flags=re.S | re.I)))
    raise RuntimeError("activate.f5.com did not return licence text. Page text: " + text[:400])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", required=True)
    ap.add_argument("--regkey", required=True)
    ap.add_argument("--ssh-key", required=True, help="private key matching the public key given to the template as sshKey")
    ap.add_argument("--password-file", required=True, help="file holding the admin password to set (the same one stored in Key Vault)")
    ap.add_argument("--manual", action="store_true")
    ap.add_argument("--auto", action="store_true")
    ap.add_argument("--accept-terms", action="store_true", help="agree to the F5 Platform Terms of Use on activate.f5.com for --auto (you are accepting them, not the script)")
    a = ap.parse_args()
    pw = open(a.password_file).read().strip()

    rc, out = ssh(a.host, a.ssh_key, "echo reachable")
    if rc != 0 or "reachable" not in out:
        print("[%s] cannot log in over SSH: %s" % (a.host, out.strip()[:200]))
        return 1
    # set the admin password now: REST needs it, and DO would only set it later. It travels inside the script text over the encrypted SSH session.
    quoted = "'" + pw.replace("'", "'" + chr(92) + "''") + "'"
    rc, out = ssh(a.host, a.ssh_key, "tmsh modify auth user admin password %s && tmsh save sys config >/dev/null && echo password-set" % quoted)
    print("[%s] admin password: %s" % (a.host, "set" if "password-set" in out else "NOT SET: " + out.replace(pw, "<hidden>").strip()[:200]))

    if licensed(a.host, a.ssh_key):
        print("[%s] already licensed, nothing to do" % a.host)
        return 0
    rc, out = ssh(a.host, a.ssh_key, "get_dossier -b %s" % a.regkey)
    # get_dossier prints one long hex string with NO trailing newline, so anything else on the connection (an ssh warning) lands on the same line: take the hex run only
    m = re.search(r"[0-9a-f]{512,}", out)
    dossier = m.group(0) if m else ""
    if not dossier or len(dossier) % 512 != 0:
        dossier = ""
    if not dossier:
        print("[%s] could not read a dossier: %r" % (a.host, dossier[:80]))
        return 2
    print("[%s] dossier read (%d characters)" % (a.host, len(dossier)))

    if a.manual:
        print("")
        print("On a machine WITH internet open https://activate.f5.com/license/dossier.jsp , paste this dossier, accept the terms,")
        print("and copy the licence text it returns.")
        print("")
        print("DOSSIER:")
        print(dossier)
        print("")
        print("Paste the licence text below, then a line containing only END:")
        lines = []
        for line in sys.stdin:
            if line.strip() == "END":
                break
            lines.append(line.rstrip(NL))
        lic = NL.join(lines).strip()
    else:
        lic = fetch_license_online(dossier, accept_terms=a.accept_terms)
    if "Registration Key" not in lic:
        print("[%s] that does not look like licence text" % a.host)
        return 3

    b64 = base64.b64encode((lic + NL).encode()).decode()
    rc, out = ssh(a.host, a.ssh_key, "echo %s | base64 -d > /config/bigip.license && reloadlic && echo reloaded" % b64)
    print("[%s] licence install: %s" % (a.host, "reload requested" if "reloaded" in out else out.strip()[:200]))
    if not licensed(a.host, a.ssh_key):
        rc, out = ssh(a.host, a.ssh_key, "tmsh install sys license file /config/bigip.license && echo installed")
        print("[%s] tried tmsh install sys license: %s" % (a.host, "ok" if "installed" in out else out.strip()[:200]))
    for _ in range(30):
        if licensed(a.host, a.ssh_key):
            print("[%s] licensed" % a.host)
            return 0
        time.sleep(10)
    print("[%s] licence installed but the unit did not report licensed within 5 minutes" % a.host)
    return 4


if __name__ == "__main__":
    sys.exit(main())
