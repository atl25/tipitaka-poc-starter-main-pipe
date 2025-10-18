import argparse
import csv
import os
from typing import List, Dict, Any, Tuple

def ensure_dir(path: str):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

def read_csv(path: str) -> List[Dict[str, Any]]:
    with open(path, 'r', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))

def to_int(x, default=None):
    try:
        return int(x)
    except Exception:
        return default

def load_units(units_csv: str) -> List[Dict[str, Any]]:
    units = read_csv(units_csv)
    for u in units:
        u['token_start'] = to_int(u.get('token_start'))
        u['token_end']   = to_int(u.get('token_end'))
        u['level']       = to_int(u.get('level'))
        u['order_idx']   = to_int(u.get('order_idx'))
    units = [u for u in units if isinstance(u.get('token_start'), int) and isinstance(u.get('token_end'), int)]
    units.sort(key=lambda r: r['token_start'])
    return units

def overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> int:
    if a_start is None or a_end is None or b_start is None or b_end is None:
        return 0
    left = max(a_start, b_start)
    right = min(a_end, b_end)
    return max(0, right - left + 1)

def find_best_unit(units_sorted: List[Dict[str, Any]], start: int, end: int, cursor_hint: int) -> Tuple[Dict[str, Any], int]:
    n = len(units_sorted)
    if n == 0 or start is None or end is None:
        return None, cursor_hint
    i = cursor_hint
    if i >= n: i = n - 1
    while i > 0 and units_sorted[i]['token_start'] > start:
        i -= 1
    while i < n and units_sorted[i]['token_end'] < start:
        i += 1
    best = None
    best_ov = -1
    j = i
    while j < n and units_sorted[j]['token_start'] <= end:
        u = units_sorted[j]
        ov = overlap(start, end, u['token_start'], u['token_end'])
        if ov > best_ov:
            best = u
            best_ov = ov
        j += 1
    return best, i

def enrich_rows(rows: List[Dict[str, Any]], units_sorted: List[Dict[str, Any]], id_fieldnames: List[str]) -> List[Dict[str, Any]]:
    out = []
    cursor = 0
    for r in rows:
        start = to_int(r.get('token_start'))
        end   = to_int(r.get('token_end'))
        best, cursor = find_best_unit(units_sorted, start, end, cursor)
        enriched = dict(r)
        if best:
            enriched.update({
                'heading_id': best.get('heading_id', ''),
                'level': best.get('level', ''),
                'path': best.get('path', ''),
                'h1': best.get('h1', ''),
                'h2': best.get('h2', ''),
                'h3': best.get('h3', ''),
                'h4': best.get('h4', ''),
                'h5': best.get('h5', ''),
                'h6': best.get('h6', ''),
            })
        else:
            enriched.update({
                'heading_id': '',
                'level': '',
                'path': '',
                'h1': '',
                'h2': '',
                'h3': '',
                'h4': '',
                'h5': '',
                'h6': '',
            })
        out.append(enriched)
    return out

def write_csv(path: str, rows: List[Dict[str, Any]], field_order: List[str] = None):
    ensure_dir(path)
    if not rows:
        with open(path, 'w', encoding='utf-8', newline='') as f:
            f.write('')
        return
    keys = list(rows[0].keys())
    header = field_order if field_order else keys
    with open(path, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, '') for k in header})

def main():
    ap = argparse.ArgumentParser(description="Join pipeline outputs (sentences, windows, subchunks, chunks) with heading path by token overlap.")
    ap.add_argument('--units', required=True, help="units_sentences_with_tokens.csv from Step 2")
    ap.add_argument('--sentences', default='', help="sentences_from_200.csv")
    ap.add_argument('--windows', default='', help="windows_2_3.csv")
    ap.add_argument('--subchunks', default='', help="subchunks_200.csv")
    ap.add_argument('--chunks', default='', help="chunks.csv")
    ap.add_argument('--outdir', required=True, help="Output directory")
    args = ap.parse_args()

    units_sorted = load_units(args.units)

    if args.sentences:
        srows = read_csv(args.sentences)
        header = list(srows[0].keys()) + ['heading_id','level','path','h1','h2','h3','h4','h5','h6']
        enriched = enrich_rows(srows, units_sorted, header)
        out = os.path.join(args.outdir, 'sentences_with_headings.csv')
        write_csv(out, enriched, header)
        print(f"[✓] Wrote {out} (rows={len(enriched)})")

    if args.windows:
        wrows = read_csv(args.windows)
        has_tokens = ('token_start' in wrows[0]) and ('token_end' in wrows[0])
        header = list(wrows[0].keys()) + ['heading_id','level','path','h1','h2','h3','h4','h5','h6']
        if has_tokens:
            enriched = enrich_rows(wrows, units_sorted, header)
        else:
            enriched = [dict(r, **{'heading_id':'','level':'','path':'','h1':'','h2':'','h3':'','h4':'','h5':'','h6':''}) for r in wrows]
        out = os.path.join(args.outdir, 'windows_with_headings.csv')
        write_csv(out, enriched, header)
        print(f"[✓] Wrote {out} (rows={len(enriched)})")

    if args.subchunks:
        sc_rows = read_csv(args.subchunks)
        header = list(sc_rows[0].keys()) + ['heading_id','level','path','h1','h2','h3','h4','h5','h6']
        enriched = enrich_rows(sc_rows, units_sorted, header)
        out = os.path.join(args.outdir, 'subchunks_with_headings.csv')
        write_csv(out, enriched, header)
        print(f"[✓] Wrote {out} (rows={len(enriched)})")

    if args.chunks:
        c_rows = read_csv(args.chunks)
        header = list(c_rows[0].keys()) + ['heading_id','level','path','h1','h2','h3','h4','h5','h6']
        enriched = enrich_rows(c_rows, units_sorted, header)
        out = os.path.join(args.outdir, 'chunks_with_headings.csv')
        write_csv(out, enriched, header)
        print(f"[✓] Wrote {out} (rows={len(enriched)})")

if __name__ == '__main__':
    main()
