import argparse
import csv
import os
import re
from typing import List, Tuple

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
    return [re.sub(r'\s+', ' ', s).strip() for s in out if s.strip()]

def whitespace_tokens(text: str) -> List[str]:
    return [t for t in re.split(r'\s+', text.strip()) if t != '']

def join_tokens(tokens: List[str]) -> str:
    return ' '.join(tokens).strip()

def ensure_dir(p: str):
    os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)

def make_chunk_id(prefix: str, idx: int, width: int) -> str:
    return f"{prefix}{idx:0{width}d}"

def run_pipeline(input_txt: str,
                 out_chunks: str,
                 out_subchunks: str,
                 out_sentences: str,
                 out_windows: str,
                 prefix: str = "MAIN",
                 id_width: int = 3,
                 chunk_size: int = 8000,
                 sub_size: int = 200,
                 tokenizer: str = "whitespace"):

    with open(input_txt, 'r', encoding='utf-8-sig') as f:
        raw = f.read()
    all_sents = split_into_sentences(raw)

    # Tokenizer
    tokenize = whitespace_tokens if tokenizer == "whitespace" else lambda s: s.split()

    # === Chunking ===
    chunks = []
    current_chunk = []
    current_tokens = 0
    for s in all_sents:
        toks = tokenize(s)
        if current_tokens + len(toks) > chunk_size and current_chunk:
            chunks.append(current_chunk)
            current_chunk = []
            current_tokens = 0
        current_chunk.append((s, toks))
        current_tokens += len(toks)
    if current_chunk:
        chunks.append(current_chunk)

    # === Output CSVs ===
    chunk_rows = []
    subchunk_rows = []
    sentence_rows = []
    window_rows = []
    token_ptr = 1

    for i, chunk in enumerate(chunks, start=1):
        chunk_id = make_chunk_id(prefix, i, id_width)
        t_start = token_ptr
        chunk_text = ' '.join([s for s, _ in chunk])
        chunk_tokens = sum(len(toks) for _, toks in chunk)
        t_end = t_start + chunk_tokens - 1
        token_ptr = t_end + 1

        chunk_rows.append({
            "chunk_id": chunk_id,
            "token_start": t_start,
            "token_end": t_end,
            "chunk_text": chunk_text
        })

        # === Subchunks ===
        subchunk = []
        sub_tok_count = 0
        sub_idx = 1
        for s, toks in chunk:
            if sub_tok_count + len(toks) > sub_size and subchunk:
                sub_id = f"{chunk_id}-SUB{sub_idx:03d}"
                sub_text = ' '.join([s for s, _ in subchunk])
                sub_t_start = t_start + sum(len(t) for _, t in chunk[:chunk.index(subchunk[0])])
                sub_t_end = sub_t_start + sum(len(t) for _, t in subchunk) - 1
                subchunk_rows.append({
                    "subchunk_id": sub_id,
                    "parent_chunk": chunk_id,
                    "token_start": sub_t_start,
                    "token_end": sub_t_end,
                    "subchunk_text": sub_text
                })
                sub_idx += 1
                subchunk = []
                sub_tok_count = 0
            subchunk.append((s, toks))
            sub_tok_count += len(toks)
        if subchunk:
            sub_id = f"{chunk_id}-SUB{sub_idx:03d}"
            sub_text = ' '.join([s for s, _ in subchunk])
            sub_t_start = t_start + sum(len(t) for _, t in chunk[:chunk.index(subchunk[0])])
            sub_t_end = sub_t_start + sum(len(t) for _, t in subchunk) - 1
            subchunk_rows.append({
                "subchunk_id": sub_id,
                "parent_chunk": chunk_id,
                "token_start": sub_t_start,
                "token_end": sub_t_end,
                "subchunk_text": sub_text
            })

        # === Sentences ===
        sent_token_ptr = t_start
        for j, (s, toks) in enumerate(chunk, start=1):
            sid = f"{chunk_id}-S{j:03d}"
            sentence_rows.append({
                "sentence_id": sid,
                "parent_chunk": chunk_id,
                "token_start": sent_token_ptr,
                "token_end": sent_token_ptr + len(toks) - 1,
                "sentence_text": s
            })
            sent_token_ptr += len(toks)

        # === Windows === (2–3 sentence windows)
        for j in range(len(chunk)):
            for span in [2, 3]:
                if j + span <= len(chunk):
                    s_group = chunk[j:j+span]
                    window_text = ' '.join([s for s, _ in s_group])
                    w_start = sum(len(t) for _, t in chunk[:j]) + t_start
                    w_end = w_start + sum(len(t) for _, t in s_group) - 1
                    win_id = f"{chunk_id}-W{span}-{j+1:04d}"
                    window_rows.append({
                        "window_id": win_id,
                        "parent_chunk": chunk_id,
                        "token_start": w_start,
                        "token_end": w_end,
                        "window_text": window_text
                    })

    # Write CSVs
    def write_csv(path: str, fieldnames: List[str], rows: List[dict]):
        ensure_dir(path)
        with open(path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
            print(f"[✓] Saved {len(rows)} rows → {path}")

    write_csv(out_chunks, ["chunk_id", "token_start", "token_end", "chunk_text"], chunk_rows)
    write_csv(out_subchunks, ["subchunk_id", "parent_chunk", "token_start", "token_end", "subchunk_text"], subchunk_rows)
    write_csv(out_sentences, ["sentence_id", "parent_chunk", "token_start", "token_end", "sentence_text"], sentence_rows)
    write_csv(out_windows, ["window_id", "parent_chunk", "token_start", "token_end", "window_text"], window_rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', required=True)
    ap.add_argument('--outdir', required=True)
    ap.add_argument('--prefix', default='MAIN')
    ap.add_argument('--id-width', type=int, default=3)
    ap.add_argument('--chunk-size', type=int, default=8000)
    ap.add_argument('--sub-size', type=int, default=200)
    args = ap.parse_args()

    run_pipeline(
        input_txt=args.input,
        out_chunks=os.path.join(args.outdir, 'chunks.csv'),
        out_subchunks=os.path.join(args.outdir, 'subchunks_200.csv'),
        out_sentences=os.path.join(args.outdir, 'sentences_from_200.csv'),
        out_windows=os.path.join(args.outdir, 'windows_2_3.csv'),
        prefix=args.prefix,
        id_width=args.id_width,
        chunk_size=args.chunk_size,
        sub_size=args.sub_size,
        tokenizer="whitespace"
    )

if __name__ == '__main__':
    main()
