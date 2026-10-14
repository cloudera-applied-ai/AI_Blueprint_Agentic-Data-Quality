#!/usr/bin/env python3
"""Install all dependencies for the Data Quality AI application.

Installs:
  - Node.js (via NodeSource or system package manager)
  - Python requirements (from app/backend/requirements.txt)
  - Node/npm dependencies (from app/frontend/package.json)
"""

import os
import shutil
import subprocess
import sys

# __file__ is unavailable when Cloudera AI runs this in a Jupyter kernel;
# fall back to cwd which CAI sets to the project root.
try:
    ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
except NameError:
    ROOT_DIR = os.getcwd()
BACKEND_DIR = os.path.join(ROOT_DIR, "app", "backend")
FRONTEND_DIR = os.path.join(ROOT_DIR, "app", "frontend")
REQUIREMENTS = os.path.join(BACKEND_DIR, "requirements.txt")


def run(cmd, cwd=None, check=True):
    """Run a command and stream output."""
    print(f"\n>> {cmd}")
    result = subprocess.run(cmd, shell=True, cwd=cwd, check=check)
    return result.returncode == 0


def check_command(name):
    """Check if a command exists on PATH."""
    return shutil.which(name) is not None


NODE_VERSION = "20.18.1"


def install_nodejs():
    """Install Node.js if not already present.

    Uses a prebuilt binary tarball installed to ~/.local so no sudo is needed
    (required for Cloudera AI / CML containers).
    """
    if check_command("node"):
        version = subprocess.check_output(["node", "--version"], text=True).strip()
        print(f"Node.js already installed: {version}")
        return

    print(f"Node.js not found. Installing v{NODE_VERSION} to ~/.local ...")

    import platform
    import tarfile
    import urllib.request

    arch = platform.machine()
    arch_map = {"x86_64": "x64", "aarch64": "arm64", "arm64": "arm64"}
    node_arch = arch_map.get(arch)
    if not node_arch:
        print(f"ERROR: Unsupported architecture: {arch}")
        sys.exit(1)

    filename = f"node-v{NODE_VERSION}-linux-{node_arch}.tar.xz"
    url = f"https://nodejs.org/dist/v{NODE_VERSION}/{filename}"
    local_dir = os.path.expanduser("~/.local")
    os.makedirs(local_dir, exist_ok=True)
    tarball = os.path.join(local_dir, filename)

    # Download
    print(f"Downloading {url} ...")
    urllib.request.urlretrieve(url, tarball)

    # Extract — strip the top-level node-vX.Y.Z-linux-ARCH/ prefix so
    # bin/, lib/, etc. land directly under ~/.local/
    print(f"Extracting to {local_dir} ...")
    with tarfile.open(tarball) as tf:
        prefix = f"node-v{NODE_VERSION}-linux-{node_arch}/"
        for member in tf.getmembers():
            if member.name.startswith(prefix):
                member.name = member.name[len(prefix):]
                if member.name:  # skip the root dir itself
                    tf.extract(member, local_dir)
    os.remove(tarball)

    # Ensure ~/.local/bin is on PATH for this process and future shells
    local_bin = os.path.join(local_dir, "bin")
    if local_bin not in os.environ.get("PATH", ""):
        os.environ["PATH"] = local_bin + os.pathsep + os.environ.get("PATH", "")
        print(f"Added {local_bin} to PATH")

    if not check_command("node"):
        print("ERROR: Node.js installation failed.")
        sys.exit(1)

    version = subprocess.check_output(["node", "--version"], text=True).strip()
    print(f"Node.js installed successfully: {version}")


def install_python_deps():
    """Install Python requirements."""
    if not os.path.isfile(REQUIREMENTS):
        print(f"ERROR: {REQUIREMENTS} not found.")
        sys.exit(1)

    print("Installing Python dependencies...")
    run(f"{sys.executable} -m pip install -r {REQUIREMENTS}")


def install_node_deps():
    """Install npm dependencies for the frontend."""
    package_json = os.path.join(FRONTEND_DIR, "package.json")
    if not os.path.isfile(package_json):
        print(f"ERROR: {package_json} not found.")
        sys.exit(1)

    print("Installing frontend npm dependencies...")
    run("npm install", cwd=FRONTEND_DIR)


def main():
    print("=" * 60)
    print("  Data Quality AI - Dependency Installer")
    print("=" * 60)

    print("\n[1/3] Installing Node.js...")
    install_nodejs()

    print("\n[2/3] Installing Python dependencies...")
    install_python_deps()

    print("\n[3/3] Installing frontend dependencies...")
    install_node_deps()

    print("\n" + "=" * 60)
    print("  Installation complete!")
    print("  Run 'python launch.py' from the project root to start.")
    print("=" * 60)


if __name__ == "__main__":
    main()
