"""Capture REAL AI assessments for a package's prepared demo photos, for offline replay in demo mode.

Each entry in <package>/demo-evidence/demo-evidence.json is sent to the configured AI provider with exactly the
same context a live inspection would use. The validated result is stored under "precomputed_assessment" with the
model, latency and capture time (or "precomputed_assessment_<lang>" with --lang, e.g. Spanish replies for --lang es). The app always labels replayed results "DEMO RESULT · precomputed".
Nothing is written for an entry whose call fails, so no result is ever invented.

Usage:
    backend/.venv/Scripts/python tools/precompute_demo_assessments.py engineering-packages/electrical-panel-icp-001 [--force] [--lang es]
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app import ai  # noqa: E402
from app.packages import validate_package  # noqa: E402


def main(pkg_dir: str, force: bool, lang: str = "en") -> int:
    key = "precomputed_assessment" if lang == "en" else f"precomputed_assessment_{lang}"
    pkg = Path(pkg_dir)
    report = validate_package(pkg)
    if not report.ok:
        print("package invalid:", report.errors)
        return 1
    provider = ai.get_provider()
    ok, why = provider.available()
    if not ok:
        print("AI provider unavailable:", why)
        return 1
    path = pkg / "demo-evidence" / "demo-evidence.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    comps = {c["component_id"]: c for c in report.components}
    reqs = {r["requirement_id"]: r for r in report.procedure["requirements"]}
    failures = 0
    for entry in doc["items"]:
        if entry.get(key) and not force:
            print(f"skip {entry['id']} (already captured)")
            continue
        req = reqs[entry["requirement_id"]]
        jpeg, img = ai.normalize_image((pkg / "demo-evidence" / entry["file"]).read_bytes())
        ctx = ai.build_context(manifest=report.manifest, procedure=report.procedure, component=comps[req["component_id"]],
                               requirement=req, serial_number=f"{report.manifest['product_id']}-DEMO",
                               worker_note=f"DEMO PHOTO: {entry.get('caption')}", image_checks=ai.image_checks(img),
                               language=lang)
        outcome = provider.assess(jpeg, ctx)
        if outcome.status != "completed":
            print(f"FAIL {entry['id']}: {outcome.status} {outcome.error}")
            failures += 1
            continue
        entry[key] = {
            "provider": outcome.provider, "model": outcome.model, "latency_ms": outcome.latency_ms,
            "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "result": outcome.result,
        }
        print(f"ok   {entry['id']}: {outcome.result['recommended_action']} ({outcome.latency_ms} ms)")
        path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 1 if failures else 0


if __name__ == "__main__":
    lang = sys.argv[sys.argv.index("--lang") + 1] if "--lang" in sys.argv else "en"
    args = [a for a in sys.argv[1:] if not a.startswith("--") and a != lang]
    if len(args) != 1:
        sys.exit(__doc__)
    sys.exit(main(args[0], "--force" in sys.argv, lang))
