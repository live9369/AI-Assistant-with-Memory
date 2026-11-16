"""Teaching only: values, records, functions and explicit unknowns."""
import json


def checked_confidence(value):
    if value is None:
        return {"status": "unknown", "value": None}
    if type(value) not in (int, float) or not 0 <= value <= 1:
        raise ValueError("confidence must be a finite probability")
    return {"status": "measured", "value": value}


def main():
    message = {"subject": "林舟", "reported_location": "青禾温室", "verified": False}
    assert checked_confidence(None)["value"] is None
    assert checked_confidence(0)["status"] == "measured"
    try:
        checked_confidence(1.5)
    except ValueError:
        rejected = True
    else:
        rejected = False
    assert rejected
    copy = dict(message)
    copy["reported_location"] = "白鹭温室"
    assert message["reported_location"] == "青禾温室"
    print(json.dumps({"record": message, "unknown": checked_confidence(None),
                      "zero": checked_confidence(0), "invalid_rejected": rejected}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
