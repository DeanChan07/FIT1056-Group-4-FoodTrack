"""Rehearse restoration on a private copy of a supplied test database.

Run from FoodTracker: python docs/evidence/recovery/rehearse_recovery.py --source PATH
The source is opened read-only and is never changed. No server is started.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from time import perf_counter

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from foodshare.storage import SqliteStore
from foodshare import services as s
from seed import DEMO_PASSWORD
import manage


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    args = parser.parse_args()
    source = Path(args.source).resolve()
    SqliteStore.validate_backup(str(source))
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix='foodshare-recovery-') as temp:
        live = Path(temp) / 'working.sqlite3'
        with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as src, sqlite3.connect(live) as dst:
            src.backup(dst)
        os.environ['FOODSHARE_DB'] = str(live)
        store = SqliteStore(str(live))
        baseline = store.dump()
        copy = Path(temp) / 'baseline.sqlite3'
        manage.backup(str(copy))
        with store.transaction() as tx:
            batch = next(b for b in tx.all('batches') if b['name'] == 'Halal chicken')
            before_quantity = batch['quantity']
            batch['quantity'] += 3
            profile = next(p for p in tx.all('profiles') if p['urgency'] == 'Standard')
            before_urgency = profile['urgency']
            profile['urgency'] = 'Soon'
        changed = store.dump()
        assert changed != baseline
        started = datetime.now(timezone.utc).isoformat()
        timer = perf_counter()
        manage.restore(str(copy))
        restored = SqliteStore(str(live)).dump()
        seconds = perf_counter() - timer
        assert restored == baseline, 'Full table/settings comparison failed'
        # Confirm the known synthetic Staff account still authenticates after restore.
        staff = s.login(SqliteStore(str(live)), 'staff', DEMO_PASSWORD)
        assert staff['role'] == 'staff'
        assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
        evidence = {
            'executed_at_utc': started, 'source_database_sha256': source_hash,
            'source_mutated': False, 'result': 'Pass',
            'comparison': 'All application tables and settings exactly equal baseline before post-restore login',
            'row_counts': {k: len(v) for k, v in baseline.items() if k != 'settings'},
            'changed_fields': {'Halal chicken quantity': [before_quantity, before_quantity + 3, before_quantity],
                               'selected profile urgency': [before_urgency, 'Soon', before_urgency]},
            'restore_and_comparison_seconds': round(seconds, 6),
            'staff_authentication_after_restore': 'Pass',
            'scope': 'Offline restoration and Python-service login on a temporary copy of the complete uploaded Demo dataset; not browser service-resumption timing or a v1 upgrade',
            'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        }
        target = Path(__file__).with_name('recovery-result.json')
        target.write_text(json.dumps(evidence, indent=2) + '\n')
        print(json.dumps(evidence, indent=2))


if __name__ == '__main__':
    main()
