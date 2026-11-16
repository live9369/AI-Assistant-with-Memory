"""Run database tests and persist a machine-readable verification summary."""
import hashlib
import json
from pathlib import Path
import platform
import sqlite3
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tests'))
suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'),pattern='test_database_schema.py')
result=unittest.TextTestRunner(verbosity=2).run(suite)
stats={}
for stem in ('runtime','supervisor'):
    path=ROOT/'database'/f'{stem}.sql'
    db=sqlite3.connect(':memory:'); db.executescript(path.read_text())
    tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    stats[stem]={
        'sql_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'physical_tables_including_fts':len(tables),
        'columns_including_fts':sum(len(list(db.execute(f'PRAGMA table_info("{t}")'))) for t in tables),
        'indexes':db.execute("SELECT count(*) FROM sqlite_master WHERE type='index'").fetchone()[0],
        'triggers':db.execute("SELECT count(*) FROM sqlite_master WHERE type='trigger'").fetchone()[0],
        'integrity_check':db.execute('PRAGMA integrity_check').fetchone()[0],
        'foreign_key_check':db.execute('PRAGMA foreign_key_check').fetchall(),
    }
    db.close()
report={'scope':'SQLite storage contracts and synthetic dataflows; not life-function validation',
    'python':platform.python_version(),'sqlite':sqlite3.sqlite_version,
    'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
    'successful':result.wasSuccessful(),'schemas':stats}
(ROOT/'database'/'validation-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
sys.exit(0 if result.wasSuccessful() else 1)
