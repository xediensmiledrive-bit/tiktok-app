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


def load_rules(dict_path=DICT_PATH, muc_do="nhe"):
    """Gop cac nhom trong file json thanh 1 bang tra.

    muc_do="nhe" (mac dinh): chi doi tu vung an toan trong moi ngu canh.
    muc_do="dam": bat them nhom _dam_them (tui, ne, hong, khoai...) cho chat Nam
                  ro hon. Hop van noi chuyen / quang cao, khong hop van trang trong.

    Nhom _rui_ro_can_review khong bao gio duoc ap dung o bat ky muc do nao.
    """
    if muc_do not in ("nhe", "dam"):
        raise ValueError(f"muc_do phai la 'nhe' hoac 'dam', nhan duoc {muc_do!r}")

    with open(dict_path, encoding="utf-8") as f:
        raw = json.load(f)

    warn = set(raw.get("_rui_ro_can_review", {}).get("canh_bao", []))
    protect = list(raw.get("_cum_bao_ve", {}).get("cum", []))
    rules = {}
    for group, body in raw.items():
        if group in ("_rui_ro_can_review", "_cum_bao_ve") or not isinstance(body, dict):
            continue
        if group == "_dam_them" and muc_do != "dam":
            continue
        for src, dst in body.items():
            if src.startswith("_"):
                continue
            rules[src.lower()] = dst
    return rules, warn, protect


def _match_case(src, dst):
    """Ap kieu hoa cua tu goc len tu thay the."""
    if not dst:
        return dst
    if src.isupper() and len(src) > 1:
        return dst.upper()
    if src[0].isupper():
        return dst[0].upper() + dst[1:]
    return dst


def _mask(text, phrases):
    """Che cac cum co dinh de luat doi tu vung khong dong vao.

    Can thiet vi tu don le co the nam trong mot cum mang nghia khac han:
    "khong" -> "hong" la dung khi phu dinh, nhung pha nat "khong day", "khong khi".
    """
    slots = {}
    for i, ph in enumerate(sorted(phrases, key=len, reverse=True)):
        pat = re.compile(rf"(?<!\w){re.escape(ph)}(?!\w)", re.IGNORECASE)

        def _sub(m, i=i):
            key = f"\x00{i}_{len(slots)}\x00"
            slots[key] = m.group(0)
            return key

        text = pat.sub(_sub, text)
    return text, slots


def _unmask(text, slots):
    for key, val in slots.items():
        text = text.replace(key, val)
    return text


def convert(text, rules=None, warn=None, muc_do="nhe", protect=None):
    """Tra ve (text_da_doi, danh_sach_thay_doi, danh_sach_canh_bao)."""
    if rules is None:
        rules, warn, protect = load_rules(muc_do=muc_do)
    warn = warn or set()
    text, slots = _mask(text, protect or [])

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
    text = _unmask(text, slots)
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\s+([,.!?;:])", r"\1", text).strip()
    return text, changes, warnings


if __name__ == "__main__":
    import sys
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    muc_do = "dam" if "--dam" in sys.argv else "nhe"
    src = args[0] if args else (
        "Bố mẹ tớ bảo thế nào cũng được, đắt lắm đấy nhé. "
        "Ông ấy mua hai quả dứa với một bát ngô, vâng đúng thế."
    )
    out, ch, wn = convert(src, muc_do=muc_do)
    print(f"GOC ({muc_do}):", src)
    print("NAM :", out)
    print("\nDa doi:", ", ".join(f"{a}->{b}" for a, b in ch) or "(khong)")
    print("Canh bao (khong tu doi):", ", ".join(f"{a}?->{b}" for a, b in wn) or "(khong)")
