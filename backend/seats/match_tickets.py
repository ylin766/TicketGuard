#!/usr/bin/env python3
"""
Match StubHub listings to seat-view photos and our sightline scores.

Join key = venue (from metadata) + section (per ticket).

Usage:
    python match_tickets.py LISTINGS.json PHOTOS_ROOT [SCORES_DIR] [-o matched.csv]

  PHOTOS_ROOT : folder containing one subfolder per venue, each holding
                section<NN>-<k>.jpg files  (e.g. photos_avfms/ or photos_event--key-ratemyseats/)
  SCORES_DIR  : optional, the batch output folder with <venue>_scores.csv files
                (so each listing also gets our computed seat score)

Output: a CSV with one row per ticket:
  listing_id, section, section_type, row, price, view, rating,
  match_status, photo_count, photo_paths, our_score, ring

match_status is one of:
  matched           -> exact section photo found
  matched_base      -> matched after stripping a letter suffix (236C -> 236)
  no_photo          -> physical section, but no photo file present
  category          -> FIFA Category ticket, no single section -> not matchable
  supporters        -> supporters section, no single section -> not matchable
  unmatchable       -> null / unparseable section
"""
import json, csv, re, os, glob, sys, difflib


def norm_venue(s):
    s = s.lower().replace("&", "")
    s = re.sub(r"\band\b", "", s)
    s = re.sub(r"[^a-z0-9]", "", s)
    for suf in ("stadium", "field", "place", "arena", "park"):
        if s.endswith(suf) and len(s) > len(suf) + 2:
            s = s[: -len(suf)]
    return s


def resolve_folder(venue, candidates):
    """Pick the candidate dir whose normalized name best matches the venue."""
    nv = norm_venue(venue)
    nmap = {norm_venue(c): c for c in candidates}
    if nv in nmap:
        return nmap[nv]
    hit = difflib.get_close_matches(nv, list(nmap.keys()), n=1, cutoff=0.55)
    return nmap[hit[0]] if hit else None


def classify(section, stype):
    s = str(section).strip()
    if stype == "category" or s.lower().startswith("category"):
        return "category", None, None
    if stype == "supporters" or "support" in s.lower():
        return "supporters", None, None
    if stype is None and not re.search(r"\d", s):
        return "unmatchable", None, None
    m = re.fullmatch(r"([A-Za-z]{0,3})(\d{1,4})([A-Za-z]{0,2})", s)
    if m:
        return "section", s, m.group(2)          # full id, base number
    return "unmatchable", None, None


def find_photos(folder, full, base):
    for key, tag in ((full, "matched"), (base, "matched_base")):
        if not key:
            continue
        hits = []
        for ext in ("jpg", "jpeg", "png", "webp"):
            hits += glob.glob(os.path.join(folder, f"section{key}-*.{ext}"))
            hits += glob.glob(os.path.join(folder, f"section{key}.{ext}"))
        if hits:
            return sorted(hits), tag
    return [], None


def load_scores(scores_dir, venue):
    if not scores_dir or not os.path.isdir(scores_dir):
        return {}
    files = [f for f in os.listdir(scores_dir) if f.endswith("_scores.csv")]
    f = resolve_folder(venue, [x[:-len("_scores.csv")] for x in files])
    if not f:
        return {}
    path = os.path.join(scores_dir, f + "_scores.csv")
    m = {}
    with open(path) as fh:
        for r in csv.DictReader(fh):
            m[str(r["section"]).upper()] = r
    return m


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    out = "matched.csv"
    if "-o" in sys.argv:
        out = sys.argv[sys.argv.index("-o") + 1]
    if len(args) < 2:
        print(__doc__); return
    listings, photos_root = args[0], args[1]
    scores_dir = args[2] if len(args) > 2 else None

    data = json.load(open(listings))
    venue = data["metadata"]["venue"]
    tickets = data["tickets"]

    subdirs = [d for d in os.listdir(photos_root) if os.path.isdir(os.path.join(photos_root, d))]
    vfolder = resolve_folder(venue, subdirs)
    folder = os.path.join(photos_root, vfolder) if vfolder else None
    scores = load_scores(scores_dir, venue)

    print(f"Venue: {venue}")
    print(f"  photos folder : {vfolder or 'NOT FOUND'}")
    print(f"  scores loaded : {len(scores)} sections")

    rows, summ = [], {}
    for t in tickets:
        kind, full, base = classify(t["section"], t.get("section_type"))
        photos, tag = ([], None)
        status = kind if kind != "section" else "no_photo"
        sc = {}
        if kind == "section":
            if folder:
                photos, tag = find_photos(folder, full, base)
                if tag:
                    status = tag
            sc = scores.get(str(full).upper()) or scores.get(str(base).upper()) or {}
        summ[status] = summ.get(status, 0) + 1
        rows.append({
            "listing_id": t.get("listing_id"), "section": t.get("section"),
            "section_type": t.get("section_type"), "row": t.get("row"),
            "price": t.get("price"), "view": t.get("view"),
            "rating": t.get("rating") or t.get("rating_text"),
            "match_status": status, "photo_count": len(photos),
            "photo_paths": " | ".join(os.path.relpath(p, photos_root) for p in photos),
            "our_score": sc.get("score", ""), "ring": sc.get("ring", ""),
        })

    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)

    print(f"\nWrote {out}  ({len(rows)} tickets)")
    for k in sorted(summ):
        print(f"  {k:14s}: {summ[k]}")


if __name__ == "__main__":
    main()
