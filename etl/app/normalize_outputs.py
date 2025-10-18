#!/usr/bin/env python3
"""
normalize_outputs.py
Copy per-base outputs under data/outputs/<base>_* into data/outputs/ root so that
the loader (--steps load) can find the expected filenames.
Usage:
  docker compose run --rm etl python etl/app/normalize_outputs.py
  BASE=mn5chunk docker compose run --rm etl python etl/app/normalize_outputs.py
"""
from pathlib import Path
import shutil, os, sys

ROOT = Path(os.getenv("PROJECT_ROOT", "/workspace")) if Path("/workspace").exists() else Path(os.getenv("PROJECT_ROOT", "."))
DATA_DIR = ROOT / "data"
OUT_DIR  = DATA_DIR / "outputs"

BASE_OVERRIDE = os.getenv("BASE")  # optional: choose specific base name

def newest_dir(pattern: str):
    cands = list(OUT_DIR.glob(pattern))
    if not cands:
        return None
    cands.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return cands[0]

def pick_base():
    if BASE_OVERRIDE:
        return BASE_OVERRIDE
    d = newest_dir("*_join_headings_by_tokens")
    if d:
        return d.name.replace("_join_headings_by_tokens","")
    d = newest_dir("*_chunk_split")
    if d:
        return d.name.replace("_chunk_split","")
    return None

def cp(src: Path, dst: Path):
    if not src.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    print(f"  - copy {src} -> {dst}")
    return True

def main():
    base = pick_base()
    if not base:
        print("❌ Could not determine base. Provide BASE=... or ensure outputs/<base>_* exists", file=sys.stderr)
        sys.exit(2)

    print(f"🔎 Normalizing for base: {base}")
    join_dir = OUT_DIR / f"{base}_join_headings_by_tokens"
    emb_dir  = OUT_DIR / f"{base}_labse_embeddings"

    # 1) CSVs
    csv_map = {
        join_dir / "windows_with_headings.csv":   OUT_DIR / "windows_with_headings.csv",
        join_dir / "sentences_with_headings.csv": OUT_DIR / "sentences_with_headings.csv",
        join_dir / "subchunks_with_headings.csv": OUT_DIR / "subchunks_with_headings.csv",
        join_dir / "chunks_with_headings.csv":    OUT_DIR / "chunks_with_headings.csv",
    }
    copied = 0
    for s, d in csv_map.items():
        if cp(s, d):
            copied += 1
    if copied == 0:
        print(f"⚠️ No *_with_headings.csv found in {join_dir}", file=sys.stderr)

    # 2) Vectors/IDs — support both flat and subfolder layouts
    for key, npy_name, ids_name in [
        ("sentences", "sentences_labse.npy", "sentences_ids.txt"),
        ("windows",   "windows_labse.npy",   "windows_ids.txt"),
        ("subchunks", "subchunks_labse.npy", "subchunks_ids.txt"),
        ("chunks",    "chunks_labse.npy",    "chunks_ids.txt"),
    ]:
        npy_src = emb_dir / npy_name
        ids_src = emb_dir / ids_name
        if not npy_src.exists() or not ids_src.exists():
            npy_src = emb_dir / key / "vectors.npy"
            ids_src = emb_dir / key / "ids.txt"
        if npy_src.exists() and ids_src.exists():
            cp(npy_src, OUT_DIR / npy_name)
            cp(ids_src, OUT_DIR / ids_name)
        else:
            print(f"⚠️ Missing vectors/ids for {key} in {emb_dir}", file=sys.stderr)

    print("✅ Normalization complete.")

if __name__ == "__main__":
    main()
