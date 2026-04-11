import importlib.util
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_build():
    build_path = ROOT / "build_site.py"
    spec = importlib.util.spec_from_file_location("build_site", build_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.build()


def main():
    run_build()
    subprocess.run([sys.executable, str(ROOT / "serve_site.py")], check=True)


if __name__ == "__main__":
    main()
