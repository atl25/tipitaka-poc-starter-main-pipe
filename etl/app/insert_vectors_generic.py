# insert_vectors_generic.py
# Insert rows from CSV into any collection (Window/Sentence/Subchunk/Chunk) with a given vector per row.
import argparse, uuid
from typing import Dict, Any, List
import numpy as np, pandas as pd
from weaviate import WeaviateClient
from weaviate.connect import ConnectionParams

INT_FIELDS = {"size", "order_idx", "level", "token_start", "token_end"}

def connect(url: str, grpc_port: int) -> WeaviateClient:
    cp = ConnectionParams.from_url(url, grpc_port=grpc_port)
    client = WeaviateClient(cp); client.connect(); return client

def safe_cast(col: str, val: Any) -> Any:
    if pd.isna(val): return None
    if col in INT_FIELDS:
        try: return int(val)
        except: return None
    return str(val)

def load_ids(path: str) -> List[str]:
    with open(path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--grpc-port", type=int, required=True)
    ap.add_argument("--collection", required=True)   # Sentence | Subchunk | Chunk
    ap.add_argument("--csv", required=True)
    ap.add_argument("--id-col", required=True)
    ap.add_argument("--text-col", required=True)     # e.g., sentence_text / subchunk_text / chunk_text
    ap.add_argument("--ids", required=True)          # *.txt (one id per line)
    ap.add_argument("--npy", required=True)          # *.npy (vectors aligned to --ids)
    ap.add_argument("--batch-size", type=int, default=256)
    args = ap.parse_args()

    df = pd.read_csv(args.csv, encoding="utf-8-sig")
    ids = load_ids(args.ids)
    vecs = np.load(args.npy)
    if len(ids) != len(vecs):
        raise ValueError(f"ids ({len(ids)}) and vectors ({len(vecs)}) length mismatch")

    id_to_row = {str(row[args.id_col]): i for i, row in df.iterrows()}

    client = connect(args.url, args.grpc_port)
    try:
        col = client.collections.get(args.collection)
        total, start = len(ids), 0
        while start < total:
            end = min(start + args.batch_size, total)
            print(f"[i] Batch {start}-{end-1}")
            for i in range(start, end):
                the_id, vec = ids[i], vecs[i]
                if the_id not in id_to_row:
                    print(f"    [!] Skip id={the_id} (not found in CSV)"); continue
                row = df.iloc[id_to_row[the_id]]
                props: Dict[str, Any] = {c: safe_cast(c, row[c]) for c in df.columns}
                uid = uuid.uuid5(uuid.NAMESPACE_URL, f"{args.collection}:{the_id}")
                try:
                    col.data.insert(properties=props, uuid=str(uid), vector=vec.astype(np.float32))
                except Exception as e:
                    print(f"    [-] Insert failed id={the_id} uuid={uid}: {e}")
            print(f"[✓] {end} / {total} done")
            start = end
        print(f"[DONE] Inserted {total} objects into '{args.collection}'.")
        print("Tip: If you inserted the same IDs earlier without vectors, delete the collection and re-insert.")
    finally:
        client.close()

if __name__ == "__main__":
    main()
