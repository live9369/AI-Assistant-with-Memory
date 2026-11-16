"""Teaching only: DAG dependencies, revocation and no duplicate evidence."""


def usable(key, objects, reader, active=None):
    active = set() if active is None else set(active)
    if key in active:
        raise ValueError("dependency cycle; refuse rather than certify")
    active.add(key)
    node = objects[key]
    if not node["active"] or reader not in node["readers"] or "life" not in node["readers"]:
        return False
    return all(usable(parent, objects, reader, active) for parent in node["parents"])


def original_sources(key, objects):
    node = objects[key]
    if not node["parents"]:
        return {key}
    result = set()
    for parent in node["parents"]:
        result.update(original_sources(parent, objects))
    return result


def main():
    node = lambda parents: {"parents": parents, "active": True, "readers": {"root", "life"}}
    objects = {"source": node([]), "belief": node(["source"]),
               "summary_a": node(["belief"]), "summary_b": node(["belief"])}
    assert usable("summary_a", objects, "root")
    independent = original_sources("summary_a", objects) | original_sources("summary_b", objects)
    assert independent == {"source"}
    objects["source"]["readers"].remove("life")
    assert not usable("summary_a", objects, "root")
    assert not usable("summary_b", objects, "root")
    print("Two summaries have one original source. Withdrawal blocks both, even for root's model input.")


if __name__ == "__main__":
    main()
