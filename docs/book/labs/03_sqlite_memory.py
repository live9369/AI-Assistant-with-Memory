"""Teaching only: in-memory SQL, version history, foreign keys and rollback."""
import sqlite3


def main():
    with sqlite3.connect(":memory:") as db:
        db.execute("PRAGMA foreign_keys=ON")
        db.executescript("""
        CREATE TABLE sources(id TEXT PRIMARY KEY, content TEXT NOT NULL);
        CREATE TABLE memories(id INTEGER PRIMARY KEY, subject TEXT NOT NULL,
          revision INTEGER NOT NULL CHECK(revision>0), value TEXT NOT NULL,
          source TEXT NOT NULL REFERENCES sources(id), UNIQUE(subject,revision));
        CREATE INDEX memory_subject_revision ON memories(subject,revision);
        """)
        with db:
            db.execute("INSERT INTO sources VALUES(?,?)", ("s1", "旧报告"))
            db.execute("INSERT INTO memories(subject,revision,value,source) VALUES(?,?,?,?)", ("林舟", 1, "青禾温室", "s1"))
            db.execute("INSERT INTO sources VALUES(?,?)", ("s2", "明确更正同一对象的当前报告"))
            db.execute("INSERT INTO memories(subject,revision,value,source) VALUES(?,?,?,?)", ("林舟", 2, "白鹭温室", "s2"))
        before = db.execute("SELECT count(*) FROM sources").fetchone()[0]
        try:
            with db:
                db.execute("INSERT INTO sources VALUES(?,?)", ("uncommitted", "must roll back"))
                db.execute("INSERT INTO memories(subject,revision,value,source) VALUES(?,?,?,?)", ("林舟", 3, "错误位置", "missing"))
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("foreign key must reject missing source")
        assert db.execute("SELECT count(*) FROM sources").fetchone()[0] == before
        current = db.execute("SELECT value FROM memories WHERE subject=? ORDER BY revision DESC LIMIT 1", ("林舟",)).fetchone()[0]
        assert current == "白鹭温室"
        assert db.execute("SELECT count(*) FROM memories").fetchone()[0] == 2
        print("current:", current, "history rows: 2; failed transaction rolled back")


if __name__ == "__main__":
    main()
