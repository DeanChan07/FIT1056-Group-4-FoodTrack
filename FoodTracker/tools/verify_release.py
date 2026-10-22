"""Run the submitted tests and retain reproducible evidence without touching demo data.
Run from FoodTracker: python tools/verify_release.py
"""
import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path
import sqlite3
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / 'docs' / 'evidence'


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    paths = [ROOT / name for name in ('app.py', 'run.py', 'manage.py', 'seed.py',
             'requirements.txt', 'setup.sh', 'setup.ps1', 'pytest.ini', '.streamlit/config.toml')]
    paths += list((ROOT / 'foodshare').rglob('*.py'))
    paths += list((ROOT / 'tests').rglob('*.py'))
    paths += list((ROOT / 'tools').rglob('*.py'))
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(paths)}
    build = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    started = datetime.now(timezone.utc).isoformat()
    result = subprocess.run([sys.executable, '-m', 'pytest', '-ra',
                             '--junitxml=docs/evidence/pytest-results.xml'], cwd=ROOT,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    (OUTPUT / 'pytest-output.txt').write_text(result.stdout, encoding='utf-8')
    evidence = {'started_at_utc': started, 'finished_at_utc': datetime.now(timezone.utc).isoformat(),
                'python': platform.python_version(), 'platform': platform.platform(),
                'sqlite': sqlite3.sqlite_version,
                'dependencies': {name: importlib.metadata.version(name)
                                 for name in ('streamlit', 'pytest', 'tzdata')},
                'exit_code': result.returncode, 'source_build_sha256': build,
                'source_files': hashes, 'command': 'python -m pytest -ra --junitxml=docs/evidence/pytest-results.xml'}
    xml = OUTPUT / 'pytest-results.xml'
    if xml.exists():
        suites = ET.parse(xml).getroot().findall('testsuite')
        totals = {key: sum(int(s.get(key, 0)) for s in suites)
                  for key in ('tests', 'failures', 'errors', 'skipped')}
        totals['passed'] = totals['tests'] - sum(totals[k] for k in ('failures', 'errors', 'skipped'))
        evidence['results'] = totals
        evidence['seconds'] = sum(float(s.get('time', 0)) for s in suites)
    (OUTPUT / 'validation.json').write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
    print(result.stdout)
    return result.returncode


if __name__ == '__main__':
    sys.exit(main())
