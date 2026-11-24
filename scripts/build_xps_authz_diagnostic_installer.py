#!/usr/bin/env python3
"""Build a deterministic installer from a reviewed four-file SHA-256 manifest."""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import stat

RUNTIME_DIR = "/usr/local/libexec/xps-authz-diagnostic"
UNIT_DIR = "/etc/systemd/system"
SOURCES = {
    "scripts/xps_authz_ipc.py": RUNTIME_DIR + "/xps_authz_ipc.py",
    "scripts/xps_authz_diagnostic.py": RUNTIME_DIR + "/xps_authz_diagnostic.py",
    "deploy/xps-authz-diagnostic/xps-authz-diagnostic@.service":
        UNIT_DIR + "/xps-authz-diagnostic@.service",
    "deploy/xps-authz-diagnostic/xps-authz-diagnostic.socket":
        UNIT_DIR + "/xps-authz-diagnostic.socket",
}

INSTALLER = r'''
import os

if __name__ == "__main__":
    os.environ.clear()

import base64
from contextlib import contextmanager, ExitStack
import grp
import hashlib
import pwd
import stat
import subprocess
import sys

ACCOUNT = "xps-agent"
OWNER_ID = 1000
ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"}
USERADD = (
    "/usr/sbin/useradd", "--system", "--user-group", "--no-create-home",
    "--home-dir", "/var/lib/xps-agent", "--shell", "/usr/sbin/nologin", ACCOUNT,
)
MODEL = b"Dell XPS 13 9345"
KERNEL = "7.3.0-11-generic"
DIRECTORY = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


def require(condition, message):
    if not condition:
        raise ValueError(message)


def protected(fd):
    info = os.fstat(fd)
    require(info.st_uid == info.st_gid == 0 and not info.st_mode & 0o022,
            "ancestor or host file must be root:root and protected from writes")


@contextmanager
def directory(path):
    with ExitStack() as stack:
        fd = os.open("/", DIRECTORY)
        stack.callback(os.close, fd)
        protected(fd)
        for part in path.split("/")[1:]:
            fd = os.open(part, DIRECTORY, dir_fd=fd)
            stack.callback(os.close, fd)
            protected(fd)
        yield fd


def host_model():
    with directory("/sys/firmware/devicetree/base") as parent:
        fd = os.open("model", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=parent)
        with os.fdopen(fd, "rb") as model:
            protected(model.fileno())
            require(stat.S_ISREG(os.fstat(model.fileno()).st_mode),
                    "host model is not a regular file")
            return model.read(256).rstrip(b"\0")


def check_host():
    host = os.uname()
    require((host.sysname, host.machine, host.release) == ("Linux", "aarch64", KERNEL),
            "host OS, architecture or kernel mismatch")
    require(host_model() == MODEL, "host model mismatch")


def absent(fd, name):
    try:
        os.stat(name, dir_fd=fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    raise ValueError("destination already exists: " + name)


def lookup(get):
    try:
        return get(ACCOUNT)
    except KeyError:
        return None


def verify_account(owner):
    user = pwd.getpwnam(ACCOUNT)
    group = grp.getgrnam(ACCOUNT)
    require(user.pw_uid not in (0, owner.pw_uid)
            and group.gr_gid not in (0, OWNER_ID, owner.pw_gid)
            and user.pw_gid == group.gr_gid and user.pw_dir == "/var/lib/xps-agent"
            and user.pw_shell == "/usr/sbin/nologin"
            and set(os.getgrouplist(ACCOUNT, user.pw_gid)) == {group.gr_gid},
            "created account did not pass identity checks")


def check_useradd():
    for hooks in ("useradd-pre.d", "useradd-post.d"):
        try:
            with directory("/etc/shadow-maint/" + hooks) as fd:
                require(not os.listdir(fd), "useradd hooks are present: " + hooks)
        except FileNotFoundError:
            continue


def write_exclusive(parent, name, path, data, effects):
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 0o644, dir_fd=parent)
    effects.append("created " + path + " (write pending)")
    with os.fdopen(fd, "wb") as stream:
        os.fchown(stream.fileno(), 0, 0)
        os.fchmod(stream.fileno(), 0o644)
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    effects[-1] = "wrote " + path


def install(effects):
    check_host()
    decoded = []
    for path, digest, encoded in PAYLOAD:
        data = base64.b64decode(encoded, validate=True)
        require(hashlib.sha256(data).hexdigest() == digest,
                "embedded SHA-256 mismatch: " + path)
        decoded.append((path, data))

    require(lookup(pwd.getpwnam) is None and lookup(grp.getgrnam) is None,
            "xps-agent user or group already exists")
    owner = pwd.getpwuid(OWNER_ID)
    require(owner.pw_uid == OWNER_ID and owner.pw_gid != 0
            and pwd.getpwnam(owner.pw_name) == owner,
            "owner identity does not reconcile through NSS")
    check_useradd()
    with directory("/run") as run:
        absent(run, "xps-authz-diagnostic.sock")
    runtime_parent, runtime_leaf = RUNTIME_DIR.rsplit("/", 1)
    with directory(runtime_parent) as lib, directory(UNIT_DIR) as units:
        absent(lib, runtime_leaf)
        for path, _ in decoded:
            parent, name = path.rsplit("/", 1)
            if parent == UNIT_DIR:
                absent(units, name)

        effects.append("invoked useradd (account databases may have changed)")
        try:
            result = subprocess.run(USERADD, env=ENV, cwd="/", stdin=subprocess.DEVNULL,
                                    timeout=30, check=False)
            outcome = f"exit={result.returncode}"
        except subprocess.TimeoutExpired:
            result = None
            outcome = "timed out after 30 seconds"
        user_exists = lookup(pwd.getpwnam) is not None
        group_exists = lookup(grp.getgrnam) is not None
        effects[-1] = (f"useradd {outcome}, "
                       f"xps-agent user present={user_exists}, group present={group_exists}")
        require(result is not None and result.returncode == 0, "useradd failed")
        verify_account(owner)

        os.mkdir(runtime_leaf, 0o755, dir_fd=lib)
        effects.append("created " + RUNTIME_DIR)
        runtime = os.open(runtime_leaf, DIRECTORY, dir_fd=lib)
        try:
            os.fchown(runtime, 0, 0)
            protected(runtime)
            os.fsync(lib)
            for path, data in decoded:
                parent, name = path.rsplit("/", 1)
                write_exclusive(units if parent == UNIT_DIR else runtime,
                                name, path, data, effects)
                os.fsync(units if parent == UNIT_DIR else runtime)
        finally:
            os.close(runtime)


def main():
    effects = []
    try:
        require(sys.argv[1:] == ["--install-diagnostic-only"],
                "expected exactly --install-diagnostic-only")
        require(sys.flags.isolated and sys.flags.no_site,
                "invoke /usr/bin/python3 -I -S")
        require(os.getresuid() == (0, 0, 0) and os.getresgid() == (0, 0, 0),
                "a locally authenticated root session is required")
        os.umask(0o022)
        install(effects)
    except (OSError, ValueError, KeyError, KeyboardInterrupt) as error:
        print(f"Diagnostic installation stopped: {error}", file=sys.stderr)
        return 1
    finally:
        for effect in effects:
            print(effect, file=sys.stderr)
    print("Diagnostic files staged. Service activation was not requested.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate manifest key: {key}")
        result[key] = value
    return result


def read_source(root, relative):
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY
    fd = os.open(root, flags)
    try:
        *parents, name = relative.split("/")
        for part in parents:
            child = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        source = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        with os.fdopen(source, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError(f"source is not a regular file: {relative}")
            return stream.read()
    finally:
        os.close(fd)


def render(root, manifest_text):
    manifest = json.loads(manifest_text, object_pairs_hook=unique_object)
    if not isinstance(manifest, dict) or manifest.keys() != SOURCES.keys():
        raise ValueError("manifest must name exactly the four approved sources")
    for source, digest in manifest.items():
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError(f"invalid SHA-256 for {source}")

    payload = []
    for source, destination in SOURCES.items():
        data = read_source(root, source)
        digest = hashlib.sha256(data).hexdigest()
        if digest != manifest[source]:
            raise ValueError(f"SHA-256 mismatch: {source}")
        payload.append((destination, digest, base64.b64encode(data).decode("ascii")))

    config = f"RUNTIME_DIR = {RUNTIME_DIR!r}\nUNIT_DIR = {UNIT_DIR!r}\nPAYLOAD = (\n"
    config += "".join(f"    {item!r},\n" for item in payload) + ")\n"
    return ("# XPS M3 diagnostic-only installer\n" + config + INSTALLER).encode("ascii")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        artifact = render(Path(__file__).resolve().parent.parent,
                          args.manifest.read_text(encoding="utf-8"))
        with args.output.open("xb") as output:
            output.write(artifact)
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")
    print(hashlib.sha256(artifact).hexdigest(), args.output)


if __name__ == "__main__":
    main()
