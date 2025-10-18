
import argparse
import csv
import os
import re
from typing import List, Dict, Any, Tuple

def split_into_sentences(text: str) -> List[str]:
    text = text.replace('\n', ' ')
    sentences = []
    current = []
    paren_level = 0

    parts = re.split(r'(\.|\(|\))', text)

    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '(':
            paren_level += 1
            if current:
                current[-1] += part
            else:
                current.append(part)
        elif part == ')':
            paren_level = max(paren_level - 1, 0)
            current.append(part)
        elif part == '.' and paren_level == 0:
            current.append(part)
            sentence = ''.join(current).strip()
            if sentence:
                sentences.append(sentence)
            current = []
        else:
            current.append(part)
        i += 1

    tail = ''.join(current).strip()
    if tail:
        sentences.append(tail)

    merged = []
    for s in sentences:
        s_clean = s.strip()
        if s_clean.startswith('(') and merged:
            merged[-1] = (merged[-1].rstrip() + ' ' + s_clean).strip()
        else:
            merged.append(s_clean)
    sentences = merged

    out = []
    i = 0
    while i < len(sentences):
        s = sentences[i].strip()

        m_num_only = re.fullmatch(r'(\d+)(\.)?', s)
        if m_num_only and (i + 1) < len(sentences):
            num = m_num_only.group(1)
            sentences[i+1] = f"{num}. {sentences[i+1].lstrip()}"
            i += 1
            continue

        m_trail = re.match(r'^(.*?)(?:\s+)(\d+)\.$', s)
        if m_trail and (i + 1) < len(sentences):
            base = m_trail.group(1).strip()
            num = m_trail.group(2)
            if base:
                out.append(base)
            sentences[i+1] = f"{num}. {sentences[i+1].lstrip()}"
            i += 1
            continue

        out.append(s)
        i += 1

    out = [re.sub(r'\s+', ' ', s).strip() for s in out if s and s.strip()]
    return out

HEADING_RE = re.compile(r'^(#{1,6})\s+(.*)$')

def whitespace_tokens(text: str):
    return [t for t in re.split(r'\s+', text.strip()) if t != '']

def ensure_dir(path: str):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

def parse_markdown_with_tokens(path: str):
    with open(path, 'r', encoding='utf-8-sig') as f:
        lines = f.readlines()

    stack = []  # (level, heading_id, title)
    headings = []
    units = []

    h_run = 0
    unit_run = 0
    level_counters = {i: 0 for i in range(1, 7)}
    global_token_pos = 0
    buffer = []
    order_idx_in_heading = 0

    def current_path():
        return " > ".join(t for (_, _, t) in stack)

    def level_titles():
        return {f"h{i}": (stack[i-1][2] if i <= len(stack) else "") for i in range(1,7)}

    def flush_buffer():
        nonlocal unit_run, order_idx_in_heading, global_token_pos
        if not stack or not buffer:
            buffer.clear()
            return
        text = " ".join(x.strip() for x in buffer if x.strip()).strip()
        buffer.clear()
        if not text:
            return

        sents = split_into_sentences(text)
        for s in sents:
            s = s.strip()
            if not s:
                continue
            unit_run += 1
            order_idx_in_heading += 1
            toks = whitespace_tokens(s)
            tcount = len(toks)
            if tcount == 0:
                continue

            start = global_token_pos + 1
            end = global_token_pos + tcount
            global_token_pos = end

            titles = level_titles()
            units.append({
                "unit_id": f"U{unit_run:06d}",
                "heading_id": stack[-1][1],
                "level": stack[-1][0],
                "order_idx": order_idx_in_heading,
                "path": current_path(),
                **titles,
                "sentence_text": s,
                "token_start": start,
                "token_end": end,
            })

    for raw in lines:
        line = raw.rstrip("\n")
        m = HEADING_RE.match(line.strip())
        if m:
            flush_buffer()
            hashes, title = m.group(1), m.group(2).strip()
            level = len(hashes)

            while stack and stack[-1][0] >= level:
                stack.pop()

            level_counters[level] += 1
            h_run += 1
            order_idx_in_heading = 0
            heading_id = f"H{h_run:06d}"
            parent_id = stack[-1][1] if stack else ""
            stack.append((level, heading_id, title))

            headings.append({
                "heading_id": heading_id,
                "level": level,
                "order_idx": level_counters[level],
                "title": title,
                "path": current_path(),
                "parent_id": parent_id
            })

            global_token_pos += len(whitespace_tokens(title))
        else:
            buffer.append(line)

    flush_buffer()
    return headings, units

def write_csv(path: str, rows, fieldnames):
    ensure_dir(path)
    with open(path, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})

def main():
    ap = argparse.ArgumentParser(description="Step 2: Parse Markdown headings → headings.csv + units_sentences_with_tokens.csv")
    ap.add_argument("--input", required=True, help="Path to Markdown file with # headings")
    ap.add_argument("--outdir", required=True, help="Output directory (e.g., outputs)")
    args = ap.parse_args()

    headings, units = parse_markdown_with_tokens(args.input)

    write_csv(
        os.path.join(args.outdir, "headings.csv"),
        headings,
        ["heading_id","level","order_idx","title","path","parent_id"]
    )
    write_csv(
        os.path.join(args.outdir, "units_sentences_with_tokens.csv"),
        units,
        ["unit_id","heading_id","level","order_idx","path","h1","h2","h3","h4","h5","h6","sentence_text","token_start","token_end"]
    )

    print(f"[✓] headings: {len(headings)}  → {os.path.join(args.outdir, 'headings.csv')}")
    print(f"[✓] sentence units: {len(units)} → {os.path.join(args.outdir, 'units_sentences_with_tokens.csv')}")
    print("[i] Token alignment: heading titles were counted (but not emitted) to match plain-text pipeline token positions.")

if __name__ == "__main__":
    main()
