"""i18n parity check for strategy.json locale files.

Compares key sets between English and Arabic strategy.json files.
Exits with code 1 if there is a mismatch, printing the missing keys.
"""

import json
import sys
from pathlib import Path

EN_PATH = Path("apps/web/messages/en/strategy.json")
AR_PATH = Path("apps/web/messages/ar/strategy.json")


def main() -> int:
    with open(EN_PATH, "r", encoding="utf-8") as f:
        en_keys = set(json.load(f).keys())

    with open(AR_PATH, "r", encoding="utf-8") as f:
        ar_keys = set(json.load(f).keys())

    missing_in_ar = en_keys - ar_keys
    missing_in_en = ar_keys - en_keys

    if missing_in_ar or missing_in_en:
        errors = []
        if missing_in_ar:
            errors.append(f"Missing in Arabic: {sorted(missing_in_ar)}")
        if missing_in_en:
            errors.append(f"Missing in English: {sorted(missing_in_en)}")
        print("\n".join(errors))
        return 1

    print("i18n parity OK: English and Arabic have exactly", len(en_keys), "keys")
    return 0


if __name__ == "__main__":
    sys.exit(main())
