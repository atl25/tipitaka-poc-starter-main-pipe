# -*- coding: utf-8 -*-
import argparse
import numpy as np
import pandas as pd
from weaviate import WeaviateClient
from weaviate.connect import ConnectionParams

INT_FIELDS = {"size", "order_idx", "token_start", "token_end", "level"}

def safe_int(x):
    if x is None:
        return None
    s = str(x).strip()
    if s == "" or s.lower() == "nan":
        return None
    try:
        return int(float(s))  # handle "12.0" etc.
    except Exception:
        return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--grpc-port", type=int, default=50051)
    ap.add_argument("--win-csv", required=True, help="windows_with_headings.csv")
    ap.add_argument("--win-ids", required=True, help="windows_ids.txt")
    ap.add_argument("--win-npy", required=True, help="windows_labse.npy")
    ap.add_argument("--batch", type=int, default=256)
    ap.add_argument("--upsert_mode", choices=["insert", "replace"], default="replace")
    args = ap.parse_args()

    # Connect
    client = WeaviateClient(ConnectionParams.from_url(args.url, grpc_port=args.grpc_port))
    client.connect()

    try:
        coll = client.collections.get("Window")

        # Load
        df = pd.read_csv(args.win_csv, encoding="utf-8")
        # force strings for all columns so we control casting ourselves
        for c in df.columns:
            if c not in INT_FIELDS:
                df[c] = df[c].astype(str)

        with open(args.win_ids, "r", encoding="utf-8") as f:
            ids = [line.strip() for line in f if line.strip()]

        vecs = np.load(args.win_npy)
        if len(ids) != len(vecs):
            raise ValueError(f"IDs ({len(ids)}) and vectors ({len(vecs)}) length mismatch")

        # Reindex df by ids order; drop missing ids while keeping vectors aligned
        df = df.set_index("window_id")
        # reindex will create NaN rows for missing ids -> make a mask to keep only those present in df
        mask = [i in df.index for i in ids]
        if not any(mask):
            raise ValueError("None of the IDs from windows_ids.txt exist in the CSV (window_id column).")
        ids_kept = [i for i, keep in zip(ids, mask) if keep]
        vecs_kept = vecs[mask]
        df = df.loc[ids_kept].reset_index()

        total = len(ids_kept)
        print(f"[i] Ready to upsert {total} windows (after aligning CSV with ids).")

        # Upsert loop
        def make_props(row: pd.Series):
            props = {}
            for k, v in row.items():
                if k in INT_FIELDS:
                    props[k] = safe_int(v)
                else:
                    props[k] = None if str(v).strip().lower() in ("nan", "") else v
            return props

        # Batch insert/replace
        start = 0
        while start < total:
            end = min(start + args.batch, total)
            batch_ids = ids_kept[start:end]
            batch_vecs = vecs_kept[start:end]
            batch_rows = df.iloc[start:end]

            objects = []
            for i, (_, row) in enumerate(batch_rows.iterrows()):
                props = make_props(row)
                obj = {
                    "uuid": batch_ids[i],
                    "properties": props,
                    "vector": batch_vecs[i].astype(float).tolist(),
                }
                objects.append(obj)

            # Use the new Collections Batch API
            try:
                if args.upsert_mode == "replace":
                    # replace is idempotent; overwrites if exists, creates if not
                    coll.data.replace_many(objects)
                else:
                    coll.data.insert_many(objects)
                print(f"[✓] Window: {end} / {total}")
            except Exception as e:
                print(f"[!] Batch {start}-{end} failed: {e}")
                # Optional: fall back to per-row to surface the bad item
                for i, obj in enumerate(objects):
                    try:
                        if args.upsert_mode == "replace":
                            coll.data.replace(
                                uuid=obj["uuid"],
                                properties=obj["properties"],
                                vector=obj["vector"]
                            )
                        else:
                            coll.data.insert(
                                uuid=obj["uuid"],
                                properties=obj["properties"],
                                vector=obj["vector"]
                            )
                    except Exception as ee:
                        print(f"    [-] Failed uuid={obj['uuid']}: {ee}")
            start = end

        print("[DONE] vectors + properties upserted to 'Window'.")
    finally:
        client.close()

if __name__ == "__main__":
    main()
