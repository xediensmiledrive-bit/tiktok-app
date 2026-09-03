"""Doi tu vung Bac -> Nam tren van ban da boc tu clip.

Nguyen tac:
  - Khop theo bien tu, cum dai uu tien truoc cum ngan ("bo me" truoc "bo").
  - Giu nguyen kieu hoa/thuong cua tu goc.
  - Tu nam trong danh sach canh bao thi KHONG tu doi, chi ghi log de nguoi duyet.
"""
import os
import re
import json

DICT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "bac_nam.json")


def load_rules(dict_path=DICT_PATH):
    """Gop moi nhom trong file json thanh 1 bang tra, tach rieng danh sach canh bao."""
    with open(dict_path, encoding="utf-8") as f:
        raw = json.load(f)

    warn = set(raw.get("_rui_ro_can_review", {}).get("canh_bao", []))
    rules = {}
    for group, body in raw.items():
        if group == "_rui_ro_can_review" or not isinstance(body, dict):
            continue
        for src, dst in body.items():
            if src.startswith("_"):
                continue
            rules[src.lower()] = dst
    return rules, warn


def _match_case(src, dst):
    """Ap kieu hoa cua tu goc len tu thay the."""
    if not dst:
        return dst
    if src.isupper() and len(src) > 1:
        return dst.upper()
    if src[0].isupper():
        return dst[0].upper() + dst[1:]
    return dst


def convert(text, rules=None, warn=None):
    """Tra ve (text_da_doi, danh_sach_thay_doi, danh_sach_canh_bao)."""
    if rules is None:
        rules, warn = load_rules()
    warn = warn or set()

    # Cum dai truoc -> tranh "bo" an mat "bo me"
    keys = sorted((k for k in rules if k not in warn), key=len, reverse=True)
    changes = []

    if keys:
        pattern = re.compile(
            r"(?<!\w)(" + "|".join(re.escape(k) for k in keys) + r")(?!\w)",
            re.IGNORECASE,
        )

        def _sub(m):
            found = m.group(1)
            dst = rules[found.lower()]
            changes.append((found, dst))
            return _match_case(found, dst)

        text = pattern.sub(_sub, text)

    # Tu rui ro: chi bao, khong doi
    warnings = []
    for w in warn:
        if w in rules and re.search(rf"(?<!\w){re.escape(w)}(?!\w)", text, re.IGNORECASE):
            warnings.append((w, rules[w]))

    # Don khoang trang doi ra tu cac rule map sang chuoi rong
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\s+([,.!?;:])", r"\1", text).strip()
    return text, changes, warnings


if __name__ == "__main__":
    import sys
    src = sys.argv[1] if len(sys.argv) > 1 else (
        "Bố mẹ tớ bảo thế nào cũng được, đắt lắm đấy nhé. "
        "Ông ấy mua hai quả dứa với một bát ngô, vâng đúng thế."
    )
    out, ch, wn = convert(src)
    print("GOC :", src)
    print("NAM :", out)
    print("\nDa doi:", ", ".join(f"{a}->{b}" for a, b in ch) or "(khong)")
    print("Canh bao (khong tu doi):", ", ".join(f"{a}?->{b}" for a, b in wn) or "(khong)")
