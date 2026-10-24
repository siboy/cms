import subprocess
fmt = "%h | %ad | %an | %s"
subprocess.run(["git", "--no-pager", "log", "-6", "--pretty=format:" + fmt, "--date=format:%Y-%m-%d %H:%M"])
print()
