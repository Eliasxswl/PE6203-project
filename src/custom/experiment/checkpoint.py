"""Small durable transactions behind the single experiment writer."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3


NAME = '.checkpoint.sqlite3'


@contextmanager
def connection(path, readonly=False):
    path = Path(path)
    db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=5) if readonly else sqlite3.connect(path, timeout=5)
    try:
        if not readonly:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('PRAGMA synchronous=FULL')
        yield db
    finally:
        db.close()


def replay(path, sequence):
    """Read a consistent committed prefix; never alter a checkpoint during inspection."""
    if not Path(path).exists():
        return []
    with connection(path, readonly=True) as db:
        db.execute('BEGIN')
        if db.execute('PRAGMA user_version').fetchone()[0] == 0:
            return []  # A first transaction may have died before publishing its schema.
        rows = db.execute('SELECT sequence, payload FROM events WHERE sequence > ? ORDER BY sequence', (sequence,)).fetchall()
        latest = db.execute('SELECT sequence FROM progress WHERE singleton=1').fetchone()[0]
    expected = sequence
    for number, _ in rows:
        expected += 1
        if number != expected:
            raise ValueError('Experiment checkpoint has a missing event')
    if latest > expected:
        raise ValueError('Experiment checkpoint is newer than its recoverable events')
    return [(number, json.loads(payload)) for number, payload in rows]


def append(path, sequence, frame):
    """Commit and fsync before returning the worker acknowledgement."""
    payload = json.dumps(frame, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    with connection(path) as db:
        with db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('CREATE TABLE IF NOT EXISTS progress (singleton INTEGER PRIMARY KEY CHECK(singleton=1), sequence INTEGER NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS events (sequence INTEGER PRIMARY KEY, payload TEXT NOT NULL)')
            db.execute('PRAGMA user_version=1')
            db.execute('INSERT OR IGNORE INTO progress VALUES (1, ?)', (sequence,))
            latest = db.execute('SELECT sequence FROM progress WHERE singleton=1').fetchone()[0]
            if latest > sequence:
                raise ValueError('Another writer advanced this experiment checkpoint')
            number = sequence + 1
            db.execute('INSERT INTO events VALUES (?, ?)', (number, payload))
            db.execute('UPDATE progress SET sequence=? WHERE singleton=1', (number,))
    return number


def prune(path, sequence):
    """The atomic JSON snapshot already contains this prefix; pruning is crash-safe."""
    if not Path(path).exists():
        return
    with connection(path) as db:
        with db:
            db.execute('DELETE FROM events WHERE sequence <= ?', (sequence,))
