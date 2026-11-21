"""Check the install-config commit recipe stays scoped to its own paths.

Mimics /etc: an unrelated file is already staged (as another tool might
leave it) and others are dirty; the recipe must commit only ETC_PATHS.
"""

import pathlib
import subprocess
import sys

repo = pathlib.Path(sys.argv[1])
repo.mkdir(parents=True)


def git(*args, check=True):
    return subprocess.run(["git", "-C", str(repo), *args], check=check,
                          capture_output=True, text=True)


git("init", "-q")
git("config", "user.email", "test@example.invalid")
git("config", "user.name", "test")
for rel in ["cron.d/birdsnet-dash", "letsencrypt/renewal/x.conf", "other/staged.conf"]:
    (repo / rel).parent.mkdir(parents=True, exist_ok=True)
    (repo / rel).write_text("v1\n")
git("add", "-A")
git("commit", "-q", "-m", "base")

# Our change, an unrelated dirty file, and an unrelated *staged* file.
(repo / "cron.d/birdsnet-dash").write_text("v2\n")
(repo / "letsencrypt/renewal/x.conf").write_text("v2\n")
(repo / "other/staged.conf").write_text("v2\n")
git("add", "other/staged.conf")
# New file, like a fresh nginx site on first install.
(repo / "nginx/sites-available").mkdir(parents=True)
(repo / "nginx/sites-available/birds.mithis.com.conf").write_text("new\n")

paths = ["nginx/sites-available/birds.mithis.com.conf", "cron.d/birdsnet-dash"]
git("add", "-A", "--", *paths)
if git("diff", "--cached", "--quiet", "--", *paths, check=False).returncode != 0:
    git("commit", "--no-verify", "-m", "scoped", "--", *paths)

committed = git("show", "--name-only", "--format=", "HEAD").stdout.split()
still_pending = git("status", "--short").stdout
print("committed:", committed)
print("still pending:\n" + still_pending)
ok = sorted(committed) == sorted(paths) and "other/staged.conf" in still_pending
print("PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
