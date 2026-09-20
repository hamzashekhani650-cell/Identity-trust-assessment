
import json
import os
import hashlib
from datetime import datetime


AUDIT_LOG_PATH = "audit_log.jsonl"
CONFIG_VERSION = "v0.2.0"
THRESHOLDS = {"low": 0.952, "medium": 0.571}


def _hash_entry(entry, previous_hash):
    payload = json.dumps(entry, sort_keys=True) + "|" + previous_hash
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _last_hash(path):
    if not os.path.exists(path):
        return "GENESIS"
    with open(path, "rb") as f:
        lines = f.read().splitlines()
        if not lines:
            return "GENESIS"
        try:
            last = json.loads(lines[-1].decode("utf-8"))
            return last.get("hash", "GENESIS")
        except Exception:
            return "GENESIS"


def log_decision(record, dimensions, score, decision, log_path=None):
    path = log_path or AUDIT_LOG_PATH
    prev_hash = _last_hash(path)

    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "config_version": CONFIG_VERSION,
        "thresholds": THRESHOLDS,
        "canonical_id": record.canonical_id,
        "identifier_present": bool(record.emirates_id),
        "source_facility": record.source_facility,
        "dimensions": dimensions,
        "trust_score": score,
        "decision": decision,
    }
    entry["hash"] = _hash_entry(entry, prev_hash)

    with open(path, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def verify_chain(log_path=None):
    path = log_path or AUDIT_LOG_PATH
    if not os.path.exists(path):
        return True, "no log"
    prev = "GENESIS"
    with open(path, "rb") as f:
        for i, line in enumerate(f):
            try:
                entry = json.loads(line.decode("utf-8"))
            except Exception:
                return False, f"malformed line {i}"
            stored_hash = entry.pop("hash", None)
            computed = _hash_entry(entry, prev)
            if computed != stored_hash:
                return False, f"chain broken at line {i}"
            prev = stored_hash
    return True, "ok"
