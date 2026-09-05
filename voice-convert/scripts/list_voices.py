#!/usr/bin/env python3
"""Tim giong nu tieng Viet trong Voice Library va ghi voice_id vao config.json.

    python3 scripts/list_voices.py            # xem danh sach
    python3 scripts/list_voices.py --add      # chon 1 giong, them vao tai khoan + ghi config
    python3 scripts/list_voices.py --add --pick 2
"""
import os
import sys
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import el_api

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "config.json")

# Tu khoa goi y giong mien Nam trong ten/mo ta cua voice
SOUTH_HINTS = ("south", "mien nam", "miền nam", "saigon", "sài gòn", "sai gon",
               "hcm", "ho chi minh", "nam bo", "nam bộ")


def score(v):
    """Uu tien giong nu + co dau hieu mien Nam."""
    blob = " ".join(str(v.get(k, "")) for k in
                    ("name", "description", "accent", "descriptive", "use_case")).lower()
    s = 0
    if (v.get("gender") or "").lower() == "female":
        s += 10
    if any(h in blob for h in SOUTH_HINTS):
        s += 8
    if (v.get("language") or "").lower() in ("vi", "vie", "vietnamese"):
        s += 3
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--add", action="store_true", help="them giong da chon vao tai khoan + ghi config")
    ap.add_argument("--pick", type=int, default=None, help="chon truc tiep so thu tu")
    ap.add_argument("--gender", default="female")
    args = ap.parse_args()

    print("Giong da co trong tai khoan:")
    try:
        mine = el_api.list_my_voices()
        for v in mine:
            print(f"  - {v.get('name'):30s} {v.get('voice_id')}  ({v.get('category', '')})")
        if not mine:
            print("  (trong)")
    except el_api.ElevenLabsError as e:
        print(f"  ! {e}")

    print("\nTim trong Voice Library (tieng Viet):")
    shared = el_api.search_shared_voices(language="vi", gender=args.gender)
    if not shared:
        print("  Khong thay giong Viet nao voi filter nay. Thu bo --gender, hoac dung Instant")
        print("  Voice Cloning: bo 1 file mau giong nu mien Nam 30s-2p vao voice_samples/.")
        return 1

    ranked = sorted(shared, key=score, reverse=True)
    for i, v in enumerate(ranked[:25], 1):
        tag = " <-- co dau hieu mien Nam" if any(
            h in " ".join(str(v.get(k, "")) for k in ("name", "description", "accent")).lower()
            for h in SOUTH_HINTS) else ""
        print(f"  {i:2d}. {v.get('name'):28s} gender={v.get('gender','?'):8s} "
              f"accent={str(v.get('accent','?')):12s} id={v.get('voice_id')}{tag}")
        if v.get("description"):
            print(f"      {str(v['description'])[:110]}")

    if not args.add:
        print("\nChay lai voi --add (--pick N) de chon.")
        return 0

    idx = args.pick
    if idx is None:
        try:
            idx = int(input("\nChon so thu tu: ").strip())
        except (ValueError, EOFError):
            print("Khong doc duoc lua chon. Dung --pick N.")
            return 1
    if not 1 <= idx <= len(ranked[:25]):
        print("So thu tu khong hop le.")
        return 1

    v = ranked[idx - 1]
    print(f"\nDang them '{v.get('name')}' vao tai khoan...")
    new_id = el_api.add_shared_voice(
        v.get("public_owner_id"), v.get("voice_id"), v.get("name") or "giong-nam"
    ) or v.get("voice_id")

    with open(CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg["voice_id"] = new_id
    cfg["voice_name"] = v.get("name") or ""
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    print(f"Da ghi voice_id={new_id} ({v.get('name')}) vao config.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
