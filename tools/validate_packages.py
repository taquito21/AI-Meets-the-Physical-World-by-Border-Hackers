"""Validate every engineering package (or the ones named) and print errors/warnings.

Usage:
    backend/.venv/Scripts/python tools/validate_packages.py [package_dir ...]
Exit code 1 if any package has errors.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.packages import discover_packages, validate_package  # noqa: E402


def main(args: list[str]) -> int:
    dirs = [Path(a) for a in args] or discover_packages(ROOT / "engineering-packages")
    failed = False
    for d in dirs:
        r = validate_package(d)
        s = r.summary()["stats"]
        print(f"{'OK  ' if r.ok else 'FAIL'} {d.name}: {r.manifest.get('product_id')} rev {r.manifest.get('engineering_revision')} "
              f"- {s['components']} components, {s['geometry_nodes']} nodes, {s['requirements']} requirements")
        for e in r.errors:
            print(f"   ERROR   {e}")
        for w in r.warnings:
            print(f"   warning {w}")
        failed |= not r.ok
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
