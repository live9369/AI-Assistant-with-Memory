"""Teaching only. In-memory state + independent deterministic reasoner; no LLM/network."""
import copy
import json
import sqlite3


def fresh_reasoner(request):
    """Only consumes this explicit packet; never remembers a prior invocation."""
    if request["memory"] is None:
        answer = "没有本次可读的当前报告；需要补充信息。"
    else:
        item = request["memory"]
        answer = "根据本次可读报告，" + request["subject"] + "负责" + item["value"] + "；这是报告，未经外部核验。"
    return {"action": "wait", "explanation": answer}


class TeachingAssistant:
    def __init__(self):
        self.db = sqlite3.connect(":memory:")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
        CREATE TABLE reports(id INTEGER PRIMARY KEY, owner TEXT NOT NULL,
          subject TEXT NOT NULL,value TEXT NOT NULL,life_readable INTEGER NOT NULL CHECK(life_readable IN(0,1)));
        CREATE TABLE candidates(id INTEGER PRIMARY KEY,report INTEGER REFERENCES reports(id),
          status TEXT CHECK(status IN('held','accepted')) NOT NULL);
        """)
        self.current_subject = {}
        self.calls = []
        self.receipts = []

    def remember(self, owner, subject, value):
        with self.db:
            source = self.db.execute("INSERT INTO reports(owner,subject,value,life_readable) VALUES(?,?,?,1)", (owner, subject, value)).lastrowid
            self.db.execute("INSERT INTO candidates(report,status) VALUES(?,'held')", (source,))
        # Receipt is appended only after the transaction commits.
        self.receipts.append({"saved_report": source, "candidate": "held"})
        self.current_subject[owner] = subject
        return source

    def ask(self, owner, subject=None):
        subject = subject or self.current_subject.get(owner)
        row = self.db.execute("SELECT id,value,life_readable FROM reports WHERE owner=? AND subject=? ORDER BY id DESC LIMIT 1", (owner, subject)).fetchone()
        # Select the latest version first. A withdrawn current report does NOT
        # silently make an older value the current truth again.
        memory = {"source": row[0], "value": row[1]} if row and row[2] else None
        packet = {"context_mode": "fresh_request", "account": owner,
                  "subject": subject, "memory": memory, "tools": ["wait"]}
        result = fresh_reasoner(copy.deepcopy(packet))
        self.calls.append({"input": copy.deepcopy(packet), "output": copy.deepcopy(result)})
        if subject is not None:
            self.current_subject[owner] = subject
        return result["explanation"]

    def withdraw_from_life(self, source):
        with self.db:
            self.db.execute("UPDATE reports SET life_readable=0 WHERE id=?", (source,))

    def close(self):
        self.db.close()


def main():
    assistant = TeachingAssistant()
    try:
        old = assistant.remember("alice", "林舟", "青禾温室")
        first = assistant.ask("alice")
        assert "青禾温室" in first
        new = assistant.remember("alice", "林舟", "白鹭温室")
        second = assistant.ask("alice")
        assert "白鹭温室" in second and "青禾温室" not in second
        private = assistant.ask("bob", "林舟")
        assert "白鹭温室" not in private
        assistant.withdraw_from_life(new)
        withdrawn = assistant.ask("alice", "林舟")
        assert "白鹭温室" not in withdrawn and "青禾温室" not in withdrawn
        assert assistant.db.execute("SELECT count(*) FROM reports").fetchone()[0] == 2
        assert assistant.db.execute("SELECT count(*) FROM candidates WHERE status='accepted'").fetchone()[0] == 0
        assert all(call["input"]["context_mode"] == "fresh_request" for call in assistant.calls)
        assert old != new
        print(json.dumps({"first": first, "corrected": second, "other_account": private,
                          "withdrawn": withdrawn, "independent_calls": len(assistant.calls),
                          "saved_reports": len(assistant.receipts), "real_model_calls": 0}, ensure_ascii=False, indent=2))
    finally:
        assistant.close()


if __name__ == "__main__":
    main()
