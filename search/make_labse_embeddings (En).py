import argparse, os, sys, numpy as np, pandas as pd, torch
from sentence_transformers import SentenceTransformer

def embed_and_save(csv_path, id_col, text_col, out_prefix, model, batch_size=128, normalize=True):
    df = pd.read_csv(csv_path, encoding="utf-8-sig")

    # auto-detect possible id/text columns
    id_candidates = [id_col, "unit_id", "sentence_id", "chunk_id", "subchunk_id", "window_id"]
    text_candidates = [text_col, "sentence_text", "chunk_text", "subchunk_text", "window_text"]

    id_field = next((c for c in id_candidates if c in df.columns), None)
    text_field = next((c for c in text_candidates if c in df.columns), None)

    if not id_field or not text_field:
        print(f"[!] Could not find ID/text columns in {csv_path}")
        print(f"    Available columns: {list(df.columns)}")
        return

    ids = df[id_field].astype(str).tolist()
    texts = df[text_field].astype(str).tolist()
    print(f"[i] Encoding {len(ids)} rows from {csv_path} (id={id_field}, text={text_field}) ...")

    vecs = model.encode(
        texts, batch_size=batch_size, convert_to_numpy=True,
        show_progress_bar=True, normalize_embeddings=normalize
    ).astype("float32")

    os.makedirs("outputs", exist_ok=True)
    np.save(f"{out_prefix}_labse.npy", vecs)
    with open(f"{out_prefix}_ids.txt", "w", encoding="utf-8") as f:
        for s in ids:
            f.write(s + "\n")

    print(f"[✓] Saved {len(ids)} rows → {out_prefix}_labse.npy / {out_prefix}_ids.txt")

def main():
    ap = argparse.ArgumentParser(...)
    ap.add_argument("--sentences", help="CSV file for sentences_with_headings.csv")
    ap.add_argument("--windows", help="CSV file for windows_with_headings.csv")
    ap.add_argument("--subchunks", help="CSV file for subchunks_with_headings.csv")
    ap.add_argument("--chunks", help="CSV file for chunks_with_headings.csv")
    ap.add_argument("--id-col", default="unit_id", help="ID column name (default: unit_id)")
    ap.add_argument("--text-col", default="sentence_text", help="Text column name (default: sentence_text)")
    ap.add_argument("--batch-size", type=int, default=128)
    ap.add_argument("--normalize", action="store_true", help="Apply L2 normalization")
    ap.add_argument("--outdir", default="outputs", help="Folder to save embeddings")  # 👈 ဒီလို ထပ်ထည့်
    args = ap.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[i] Loading LaBSE on {device} ...")
    model = SentenceTransformer("sentence-transformers/LaBSE", device=device)

    if args.sentences:
        embed_and_save(args.sentences, args.id_col, args.text_col,
                       os.path.join(args.outdir, "sentences"), model,
                       args.batch_size, args.normalize)
    if args.windows:
        embed_and_save(args.windows, "window_id", args.text_col,
                       os.path.join(args.outdir, "windows"), model,
                       args.batch_size, args.normalize)
    if args.subchunks:
        embed_and_save(args.subchunks, "subchunk_id", args.text_col,
                       os.path.join(args.outdir, "subchunks"), model,
                       args.batch_size, args.normalize)
    if args.chunks:
        embed_and_save(args.chunks, "chunk_id", args.text_col,
                       os.path.join(args.outdir, "chunks"), model,
                       args.batch_size, args.normalize)


if __name__ == "__main__":
    main()
