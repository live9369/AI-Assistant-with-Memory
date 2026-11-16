"""Teaching only: code fallback preserves current ledger, no OS process snapshot."""


def main():
    state = {"identity": "teaching-instance", "code": "v1", "ledger": ["before upgrade"],
             "unknown_actions": ["write-result-not-yet-confirmed"], "user_stopped": False}
    known_good = state["code"]
    state["code"] = "v2"
    state["ledger"].append("a genuine message received while v2 was running")
    candidate_passed = False
    if not candidate_passed:
        state["code"] = known_good
        state["unknown_action_policy"] = "paused; reconcile, never auto-replay"
    assert state["code"] == "v1"
    assert len(state["ledger"]) == 2
    assert state["identity"] == "teaching-instance"
    assert state["unknown_actions"]
    expected_control_revision = 0
    current_control_revision = 1  # a newer user stop arrives
    state["user_stopped"] = True
    resumed = not state["user_stopped"] and current_control_revision == expected_control_revision
    assert not resumed
    print("Code fell back to v1; new history retained; unknown actions paused; newer stop respected.")


if __name__ == "__main__":
    main()
