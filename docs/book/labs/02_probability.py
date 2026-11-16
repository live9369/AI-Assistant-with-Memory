"""Teaching only: permission filtering before a stable softmax."""
import math


def distribution(candidates, temperature=1.0):
    if not math.isfinite(temperature) or temperature <= 0:
        raise ValueError("positive finite temperature required")
    allowed = [c for c in candidates if c["allowed"]]
    if not allowed:
        raise PermissionError("no allowed action; no sampling performed")
    scores = [c["score"] for c in allowed]
    if not all(math.isfinite(s) for s in scores):
        raise ValueError("finite scores required")
    highest = max(scores)
    weights = [math.exp((s - highest) / temperature) for s in scores]
    total = sum(weights)
    return {c["action"]: w / total for c, w in zip(allowed, weights)}


def main():
    candidates = [{"action": "answer", "score": 2, "allowed": True},
                  {"action": "clarify", "score": 1, "allowed": True},
                  {"action": "read_private_file", "score": 100, "allowed": False}]
    result = distribution(candidates)
    assert "read_private_file" not in result
    assert abs(sum(result.values()) - 1) < 1e-12
    assert abs(result["answer"] - 0.7310585786) < 1e-9
    try:
        distribution([{"action": "forbidden", "score": 1, "allowed": False}])
    except PermissionError:
        pass
    else:
        raise AssertionError("must not assign probabilities to forbidden actions")
    for temperature in (0.5, 1, 2):
        print("temperature", temperature, distribution(candidates, temperature))


if __name__ == "__main__":
    main()
