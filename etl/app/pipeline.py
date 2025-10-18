#!/usr/bin/env python3
"""
UNIFIED ETL + LOAD PIPELINE (idempotent)
- Clean → Split → (optional) Parse headings → Join → Embed (LaBSE)
- Normalizes outputs into OUTPUTS_DIR with filenames expected by loader
- Load: schema → CSV insert (BM25) → vector insert → sanity search

Idempotency:
- Per-step/per-file skip if required artifacts already exist
- FORCE flags to override: FORCE_ALL=1 or FORCE_CLEAN/SPLIT/PARSE/JOIN/EMBED=1
"""
import os, sys, time, json, argparse, subprocess, shutil
from pathlib import Path
import urllib.request
from typing import List

# --- Paths & Config ---------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_DIR      = Path(__file__).resolve().parent
DATA_DIR     = Path(os.getenv("DATA_DIR", str(PROJECT_ROOT / "data")))
RAW_DIR      = Path(os.getenv("RAW_DIR",  str(DATA_DIR / "raw")))
OUT_DIR      = Path(os.getenv("OUTPUTS_DIR", str(DATA_DIR / "outputs")))

WEAVIATE_URL  = os.getenv("WEAVIATE_URL", "http://weaviate:8080")
WEAVIATE_GRPC = int(os.getenv("WEAVIATE_GRPC_PORT", "50051"))
WAIT_MAX_SEC  = int(os.getenv("WAIT_MAX_SEC", "300"))

# Expected normalized filenames in OUT_DIR (for the loader)
CSV_TARGETS = {
    "Window":   ("windows_with_headings.csv",   "window_id",   "text"),
    "Sentence": ("sentences_with_headings.csv", "sentence_id", "sentence_text"),
    "Subchunk": ("subchunks_with_headings.csv",  "subchunk_id", "subchunk_text"),
    "Chunk":    ("chunks_with_headings.csv",     "chunk_id",    "chunk_text"),
}
VEC_TARGETS = {
    "Window":   ("windows_ids.txt",   "windows_labse.npy"),
    "Sentence": ("sentences_ids.txt", "sentences_labse.npy"),
    "Subchunk": ("subchunks_ids.txt", "subchunks_labse.npy"),
    "Chunk":    ("chunks_ids.txt",    "chunks_labse.npy"),
}

# --- Imports from prep utilities -------------------------------------------
sys.path.append(str(APP_DIR))
from clean_text import clean_text_all_files         # provided in repo
from chunk_split import run_pipeline                # provided in repo

# ---------------- Idempotent helpers (skip-if-done) -------------------------
def _forced(stage: str) -> bool:
    """FORCE_ALL=1 or FORCE_<STAGE>=1 to force re-run."""
    return os.getenv("FORCE_ALL","0")=="1" or os.getenv(f"FORCE_{stage.upper()}","0")=="1"

def _exists_all(paths: List[Path]) -> bool:
    return all(Path(p).exists() for p in paths)

def _clean_ready(raw_dir: Path, cleaned_dir: Path) -> bool:
    raws = [p for p in raw_dir.glob("*") if p.suffix.lower() in (".txt", ".md")]
    if not raws:
        return False
    for rp in raws:
        tgt = cleaned_dir / f"{rp.stem}_cleaned.txt"
        if not tgt.exists():
            return False
    return True

def _split_ready(base: str, out_dir: Path) -> bool:
    d = out_dir / f"{base}_chunk_split"
    need = [d/"chunks.csv", d/"subchunks_200.csv", d/"sentences_from_200.csv", d/"windows_2_3.csv"]
    return _exists_all(need)

def _parse_ready(base_md: str, out_dir: Path) -> bool:
    d = out_dir / f"{base_md}_hd_parse"
    need = [d/"headings.csv", d/"units_sentences_with_tokens.csv"]
    return _exists_all(need)

def _join_ready(base_md: str, out_dir: Path) -> bool:
    d = out_dir / f"{base_md}_join_headings_by_tokens"
    need = [d/"sentences_with_headings.csv", d/"windows_with_headings.csv",
            d/"subchunks_with_headings.csv", d/"chunks_with_headings.csv"]
    return _exists_all(need)

def _embed_ready(base: str, out_dir: Path) -> bool:
    b = base.replace("-heading","")
    d = out_dir / f"{b}_labse_embeddings"

    # flat layout (what your embed script writes today)
    flat_need = [
        d/"sentences_labse.npy", d/"sentences_ids.txt",
        d/"windows_labse.npy",   d/"windows_ids.txt",
        d/"subchunks_labse.npy", d/"subchunks_ids.txt",
        d/"chunks_labse.npy",    d/"chunks_ids.txt",
    ]
    have_flat = all(p.exists() for p in flat_need)

    # new subfolder layout (future-proof)
    new_need = [
        d/"sentences/ids.txt", d/"sentences/vectors.npy",
        d/"windows/ids.txt",   d/"windows/vectors.npy",
        d/"subchunks/ids.txt", d/"subchunks/vectors.npy",
        d/"chunks/ids.txt",    d/"chunks/vectors.npy",
    ]
    have_new = all(p.exists() for p in new_need)

    # skip if either layout exists
    return have_flat or have_new

# ----------------------------------------------------------------------------

# --- Small utilities --------------------------------------------------------
def sh(cmd, check=True, cwd=None):
    print("  $", " ".join(map(str, cmd)), flush=True)
    return subprocess.run(cmd, check=check, cwd=cwd)

def wait_ready(url: str, max_wait: int = WAIT_MAX_SEC):
    ready = url.rstrip("/") + "/v1/.well-known/ready"
    live  = url.rstrip("/") + "/v1/.well-known/live"
    start = time.time()
    print(f"⏳ Waiting for Weaviate: {ready}")
    while True:
        for probe in (ready, live):
            try:
                with urllib.request.urlopen(probe, timeout=3) as r:
                    body = (r.read().decode("utf-8", "ignore") or "").strip()
                    if r.status == 200:
                        try:
                            if json.loads(body).get("status") == "ready":
                                print(f"✅ Weaviate ready (JSON) via {probe}")
                                return
                        except Exception:
                            if not body or body.upper() == "OK" or "ready" in body.lower():
                                print(f"✅ Weaviate ready (text='{body}') via {probe}")
                                return
            except Exception:
                pass
        if time.time() - start > max_wait:
            print("❌ Timed out waiting for Weaviate.", file=sys.stderr)
            sys.exit(1)
        time.sleep(2)

def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)
    return p

# --- Steps ------------------------------------------------------------------
def step_clean():
    print("[1/9] CLEAN → raw → cleaned_text …")
    cleaned_dir = ensure_dir(OUT_DIR / "cleaned_text")
    if _clean_ready(RAW_DIR, cleaned_dir) and not _forced("clean"):
        print("↪︎ [skip] CLEAN: cleaned_text already up-to-date for all inputs")
        return cleaned_dir
    clean_text_all_files(input_folder=str(RAW_DIR), output_folder=str(cleaned_dir), suffix="_cleaned.txt")
    return cleaned_dir

def step_split(cleaned_dir: Path):
    print("[2/9] SPLIT → cleaned_text → per-file chunk_split …")
    split_dirs = []
    for fname in os.listdir(cleaned_dir):
        if not fname.endswith("_cleaned.txt"): 
            continue
        input_cleaned = cleaned_dir / fname
        base_name = fname.replace("_cleaned.txt", "")  # e.g., mn5chunk
        outdir = ensure_dir(OUT_DIR / f"{base_name}_chunk_split")
        if _split_ready(base_name, OUT_DIR) and not _forced("split"):
            print(f"↪︎ [skip] SPLIT: {base_name}_chunk_split already has 4 files")
            split_dirs.append((base_name, outdir))
            continue
        print(f"   - splitting {fname} → {outdir}")
        run_pipeline(
            input_txt=str(input_cleaned),
            out_chunks=str(outdir / 'chunks.csv'),
            out_subchunks=str(outdir / 'subchunks_200.csv'),
            out_sentences=str(outdir / 'sentences_from_200.csv'),
            out_windows=str(outdir / 'windows_2_3.csv'),
            prefix="MAIN", id_width=3, chunk_size=8000, sub_size=200, tokenizer="whitespace"
        )
        split_dirs.append((base_name, outdir))
    if not split_dirs:
        print("❌ No cleaned files found to split.", file=sys.stderr)
        sys.exit(1)
    return split_dirs

def step_parse_and_join(split_dirs):
    print("[3/9] PARSE (optional .md headings) + [4/9] JOIN …")
    md_files = list(RAW_DIR.glob("*.md"))
    joined_outputs = []

    if not md_files:
        print("   ⏭️ No .md found. Will synthesize *with_headings.csv from split CSVs.")
        for base_name, split_dir in split_dirs:
            join_dir = ensure_dir(OUT_DIR / f"{base_name}_join_headings_by_tokens")
            if _join_ready(base_name, OUT_DIR) and not _forced("join"):
                print(f"↪︎ [skip] JOIN synth: {base_name}_join_headings_by_tokens already has *_with_headings.csv")
                joined_outputs.append((base_name, join_dir))
                continue
            mapping = {
                split_dir / "windows_2_3.csv":        join_dir / "windows_with_headings.csv",
                split_dir / "sentences_from_200.csv": join_dir / "sentences_with_headings.csv",
                split_dir / "subchunks_200.csv":      join_dir / "subchunks_with_headings.csv",
                split_dir / "chunks.csv":             join_dir / "chunks_with_headings.csv",
            }
            for src, dst in mapping.items():
                if src.exists(): shutil.copyfile(src, dst)
            joined_outputs.append((base_name, join_dir))
        return joined_outputs

    # .md headings present → parse + join for each md
    for md in md_files:
        base_filename = md.stem  # e.g., MN5chunk or MN5chunk-heading
        hd_dir = ensure_dir(OUT_DIR / f"{base_filename}_hd_parse")
        if _parse_ready(base_filename, OUT_DIR) and not _forced("parse"):
            print(f"↪︎ [skip] PARSE: {base_filename}_hd_parse already ready")
        else:
            print(f"   - parsing headings: {md}")
            sh([sys.executable, str(APP_DIR / "md_headings_parse.py"), "--input", str(md), "--outdir", str(hd_dir)])

        # which split_dir to join with (strip '-heading' if present)
        chunk_split_name = base_filename.replace("-heading", "")
        split_dir = OUT_DIR / f"{chunk_split_name}_chunk_split"

        join_dir = ensure_dir(OUT_DIR / f"{base_filename}_join_headings_by_tokens")
        if _join_ready(base_filename, OUT_DIR) and not _forced("join"):
            print(f"↪︎ [skip] JOIN: {base_filename}_join_headings_by_tokens already ready")
        else:
            args = [
                sys.executable, str(APP_DIR / "join_headings_by_tokens.py"),
                "--units", str(hd_dir / "units_sentences_with_tokens.csv"),
                "--sentences", str(split_dir / "sentences_from_200.csv"),
                "--windows",   str(split_dir / "windows_2_3.csv"),
                "--subchunks", str(split_dir / "subchunks_200.csv"),
                "--chunks",    str(split_dir / "chunks.csv"),
                "--outdir",    str(join_dir),
            ]
            sh(args)
        joined_outputs.append((base_filename, join_dir))

    return joined_outputs

def step_embed(joined_outputs):
    print("[5/9] EMBED (LaBSE) …")
    artifacts = {k: {"csv": None, "ids": None, "npy": None} for k in CSV_TARGETS}

    for base_name, join_dir in joined_outputs:
        if _embed_ready(base_name, OUT_DIR) and not _forced("embed"):
            print(f"↪︎ [skip] EMBED: {base_name.replace('-heading','')}_labse_embeddings already ready")
        else:
            out_embed_dir = ensure_dir(OUT_DIR / f"{base_name.replace('-heading','')}_labse_embeddings")
            args = [
                sys.executable, str(APP_DIR / "make_labse_embeddings.py"),
                "--sentences", str(join_dir / "sentences_with_headings.csv"),
                "--windows",   str(join_dir / "windows_with_headings.csv"),
                "--subchunks", str(join_dir / "subchunks_with_headings.csv"),
                "--chunks",    str(join_dir / "chunks_with_headings.csv"),
                "--outdir",    str(out_embed_dir),
            ]
            sh(args)

        # === ADD THIS: embed လုပ်ပြီးတိုင်း (skip ဖြစ်লেও) normalize_outputs.py ကို ခေါ်ပါ ===
        env = os.environ.copy()
        env["BASE"] = base_name.replace("-heading","")
        subprocess.run(
            [sys.executable, str(APP_DIR / "normalize_outputs.py")],
            check=True,
            env=env,
        )
        # === END ADD ===

        out_embed_dir = OUT_DIR / f"{base_name.replace('-heading','')}_labse_embeddings"
        produced = {
            "Window":   (join_dir / "windows_with_headings.csv",   out_embed_dir / "windows"   / "ids.txt", out_embed_dir / "windows"   / "vectors.npy"),
            "Sentence": (join_dir / "sentences_with_headings.csv", out_embed_dir / "sentences" / "ids.txt", out_embed_dir / "sentences" / "vectors.npy"),
            "Subchunk": (join_dir / "subchunks_with_headings.csv",  out_embed_dir / "subchunks" / "ids.txt", out_embed_dir / "subchunks"  / "vectors.npy"),
            "Chunk":    (join_dir / "chunks_with_headings.csv",     out_embed_dir / "chunks"    / "ids.txt", out_embed_dir / "chunks"    / "vectors.npy"),
        }
        for key, (csv_path, ids_path, npy_path) in produced.items():
            if csv_path.exists() and ids_path.exists() and npy_path.exists():
                artifacts[key] = {"csv": csv_path, "ids": ids_path, "npy": npy_path}

    # Normalize into OUT_DIR filenames expected by loader (ရှိနေသေးတယ်—ထားခဲ့လို့ ပိုမအန္တရာယ်)
    for key in CSV_TARGETS:
        csv_name, _, _ = CSV_TARGETS[key]
        ids_name, npy_name = VEC_TARGETS[key]
        if artifacts[key]["csv"]:
            shutil.copyfile(artifacts[key]["csv"], OUT_DIR / csv_name)
        if artifacts[key]["ids"]:
            shutil.copyfile(artifacts[key]["ids"], OUT_DIR / ids_name)
        if artifacts[key]["npy"]:
            shutil.copyfile(artifacts[key]["npy"], OUT_DIR / npy_name)

    return OUT_DIR

def step_schema_insert_vectors_and_search():
    print("[6/9] WAIT for Weaviate …")
    wait_ready(WEAVIATE_URL)

    setup_script = APP_DIR / "weaviate_multitier_setup_and_search_patched.py"
    inserter     = APP_DIR / "insert_vectors_generic.py"
    searcher     = APP_DIR / "search_weaviate_labse_hybridfix.py"

    for p in (setup_script, inserter, searcher):
        if not p.exists():
            print(f"❌ Missing script: {p}", file=sys.stderr)
            sys.exit(1)

    print("[7/9] SCHEMA setup …")
    sh([sys.executable, str(setup_script), "--url", WEAVIATE_URL, "--grpc-port", str(WEAVIATE_GRPC), "--setup"])  

    print("[8/9] INSERT CSV (BM25) …")
    sh([sys.executable, str(setup_script), "--url", WEAVIATE_URL, "--grpc-port", str(WEAVIATE_GRPC), "--outdir", str(OUT_DIR), "--insert"])  

    print("[9/9] INSERT VECTORS + sanity search …")
    for coll, (csv_name, id_col, text_col) in CSV_TARGETS.items():
        ids_name, npy_name = VEC_TARGETS[coll]
        csvp, idsp, npyp = OUT_DIR/csv_name, OUT_DIR/ids_name, OUT_DIR/npy_name
        if csvp.exists() and idsp.exists() and npyp.exists():
            print(f"   - {coll}: inserting vectors")
            sh([sys.executable, str(inserter),
                "--url", WEAVIATE_URL, "--grpc-port", str(WEAVIATE_GRPC),
                "--collection", coll,
                "--csv", str(csvp),
                "--id-col", id_col, "--text-col", text_col,
                "--ids", str(idsp), "--npy", str(npyp)])
        else:
            print(f"   - {coll}: skip (missing one of {csv_name}/{ids_name}/{npy_name})")

    sh([sys.executable, str(searcher), "--url", WEAVIATE_URL, "--grpc-port", str(WEAVIATE_GRPC),
        "--collection","Window","--mode","hybrid","--query","mettā","--k","5","--alpha","0.5"], check=False)

# --- CLI --------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Unified ETL + Load pipeline (idempotent)")
    ap.add_argument("--skip-clean", action="store_true")
    ap.add_argument("--skip-split", action="store_true")
    ap.add_argument("--skip-join",  action="store_true")
    ap.add_argument("--skip-embed", action="store_true")
    ap.add_argument("--skip-load",  action="store_true", help="skip weaviate schema/insert/vector")
    args = ap.parse_args()

    print("=== Unified ETL + LOAD Pipeline (idempotent) ===")
    print(f"RAW_DIR={RAW_DIR}\nOUT_DIR={OUT_DIR}\nWEAVIATE_URL={WEAVIATE_URL} gRPC={WEAVIATE_GRPC}\n")

    ensure_dir(OUT_DIR)

    cleaned_dir = None
    split_dirs  = None
    joined_out  = None

    if not args.skip_clean:
        cleaned_dir = step_clean()
    if not args.skip_split:
        if cleaned_dir is None:
            cleaned_dir = OUT_DIR / "cleaned_text"
        split_dirs = step_split(cleaned_dir)
    if not args.skip_join:
        if split_dirs is None:
            candidates = [p for p in OUT_DIR.glob("*_chunk_split") if p.is_dir()]
            split_dirs = [(p.name.replace("_chunk_split",""), p) for p in candidates]
        joined_out = step_parse_and_join(split_dirs)
    if not args.skip_embed:
        if joined_out is None:
            candidates = [p for p in OUT_DIR.glob("*_join_headings_by_tokens") if p.is_dir()]
            if not candidates:
                print("❌ No joined outputs to embed.", file=sys.stderr)
                sys.exit(1)
            joined_out = [(p.name.replace("_join_headings_by_tokens",""), p) for p in candidates]
        step_embed(joined_out)

    if not args.skip_load:
        step_schema_insert_vectors_and_search()

    print("✅ All done.")

if __name__ == "__main__":
    main()
