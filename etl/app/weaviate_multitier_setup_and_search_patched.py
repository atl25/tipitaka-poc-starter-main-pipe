# weaviate_multitier_setup_and_search_patched.py
import argparse
import csv
import os
from typing import List

import weaviate
from weaviate import WeaviateClient
from weaviate.connect import ConnectionParams
from weaviate.classes.config import Property, DataType, Configure

# --------------------
# Helpers
# --------------------
def connect(url: str, grpc_port: int) -> WeaviateClient:
    cp = ConnectionParams.from_url(url, grpc_port=grpc_port)
    client = WeaviateClient(cp)
    client.connect()
    return client

def create_collections(client: WeaviateClient, use_vectorizer: bool = False):
    """
    Create 4 collections. Default: BM25-only (no vectorizer).
    Set use_vectorizer=True if your Weaviate has a text2vec module enabled.
    """
    vectorizer = Configure.Vectorizer.text2vec_transformers() if use_vectorizer else Configure.Vectorizer.none()

    existing = set(client.collections.list_all())

    if "Window" not in existing:
        client.collections.create(
            name="Window",
            description="2/3-sentence windows with optional heading context",
            vectorizer_config=vectorizer,  # note: DeprecationWarning is OK; keeps backwards-compat
            properties=[
                Property(name="window_id", data_type=DataType.TEXT),
                Property(name="chunk_id", data_type=DataType.TEXT),
                Property(name="size", data_type=DataType.INT),
                Property(name="left_sentence_id", data_type=DataType.TEXT),
                Property(name="right_sentence_id", data_type=DataType.TEXT),
                Property(name="order_idx", data_type=DataType.INT),
                Property(name="text", data_type=DataType.TEXT),
                Property(name="token_start", data_type=DataType.INT),
                Property(name="token_end", data_type=DataType.INT),
                Property(name="heading_id", data_type=DataType.TEXT),
                Property(name="level", data_type=DataType.INT),
                Property(name="path", data_type=DataType.TEXT),
                Property(name="h1", data_type=DataType.TEXT),
                Property(name="h2", data_type=DataType.TEXT),
                Property(name="h3", data_type=DataType.TEXT),
                Property(name="h4", data_type=DataType.TEXT),
                Property(name="h5", data_type=DataType.TEXT),
                Property(name="h6", data_type=DataType.TEXT),
            ],
        )

    if "Sentence" not in existing:
        client.collections.create(
            name="Sentence",
            description="Sentence-level units with optional heading context",
            vectorizer_config=vectorizer,
            properties=[
                Property(name="sentence_id", data_type=DataType.TEXT),
                Property(name="chunk_id", data_type=DataType.TEXT),
                Property(name="subchunk_id", data_type=DataType.TEXT),
                Property(name="order_idx", data_type=DataType.INT),
                Property(name="token_start", data_type=DataType.INT),
                Property(name="token_end", data_type=DataType.INT),
                Property(name="sentence_text", data_type=DataType.TEXT),
                Property(name="heading_id", data_type=DataType.TEXT),
                Property(name="level", data_type=DataType.INT),
                Property(name="path", data_type=DataType.TEXT),
                Property(name="h1", data_type=DataType.TEXT),
                Property(name="h2", data_type=DataType.TEXT),
                Property(name="h3", data_type=DataType.TEXT),
                Property(name="h4", data_type=DataType.TEXT),
                Property(name="h5", data_type=DataType.TEXT),
                Property(name="h6", data_type=DataType.TEXT),
            ],
        )

    if "Subchunk" not in existing:
        client.collections.create(
            name="Subchunk",
            description="~200-token subchunks",
            vectorizer_config=vectorizer,
            properties=[
                Property(name="subchunk_id", data_type=DataType.TEXT),
                Property(name="chunk_id", data_type=DataType.TEXT),
                Property(name="order_idx", data_type=DataType.INT),
                Property(name="token_start", data_type=DataType.INT),
                Property(name="token_end", data_type=DataType.INT),
                Property(name="subchunk_text", data_type=DataType.TEXT),
            ],
        )

    if "Chunk" not in existing:
        client.collections.create(
            name="Chunk",
            description="~8000-token chunks",
            vectorizer_config=vectorizer,
            properties=[
                Property(name="chunk_id", data_type=DataType.TEXT),
                Property(name="token_start", data_type=DataType.INT),
                Property(name="token_end", data_type=DataType.INT),
                Property(name="chunk_text", data_type=DataType.TEXT),
            ],
        )

def _safe_int(x):
    if x is None:
        return None
    x = str(x).strip()
    if x == "" or x.lower() == "nan":
        return None
    try:
        return int(x)
    except Exception:
        return None

def insert_csv(client: WeaviateClient, collection: str, csv_path: str):
    """
    Insert a single CSV file into the given collection.
    No recursion. No outdir usage here.
    """
    coll = client.collections.get(collection)
    total = 0

    # INT fields per collection
    int_fields_map = {
        "Window":   ["size", "order_idx", "token_start", "token_end", "level"],
        "Sentence": ["order_idx", "token_start", "token_end", "level"],
        "Subchunk": ["order_idx", "token_start", "token_end"],
        "Chunk":    ["token_start", "token_end"],
    }
    int_fields = set(int_fields_map.get(collection, []))

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        with coll.batch.dynamic() as batch:
            for row in reader:
                props = {}
                for k, v in row.items():
                    if k in int_fields:
                        props[k] = _safe_int(v)
                    else:
                        props[k] = v if v is not None else ""
                batch.add_object(properties=props)
                total += 1
                if total % 1000 == 0:
                    print(f"[i] {collection}: {total} inserted...")
    print(f"[✓] {collection}: {total} inserted from {csv_path}")

def ingest_all(client, outdir):
    """
    Choose best-available CSV per class and insert once each.
    Priority:
      Window   → windows_with_headings.csv  else windows_2_3.csv
      Sentence → sentences_with_headings.csv else sentences_from_200.csv
      Subchunk → subchunks_200.csv
      Chunk    → chunks.csv
    """
    outdir = os.path.abspath(outdir)
    def pick(*candidates):
        for p in candidates:
            if p and os.path.exists(p):
                return p
        return None

    win_csv = pick(
        os.path.join(outdir, "windows_with_headings.csv"),
        os.path.join(outdir, "windows_2_3.csv"),
    )
    sen_csv = pick(
        os.path.join(outdir, "sentences_with_headings.csv"),
        os.path.join(outdir, "sentences_from_200.csv"),
    )
    sub_csv = pick(os.path.join(outdir, "subchunks_200.csv"))
    chk_csv = pick(os.path.join(outdir, "chunks.csv"))

    plan = [
        ("Window",   win_csv),
        ("Sentence", sen_csv),
        ("Subchunk", sub_csv),
        ("Chunk",    chk_csv),
    ]

    for cname, path in plan:
        if path:
            insert_csv(client, cname, path)
        else:
            print(f"[skip] {cname}: required CSV not found in {outdir}")

# --------------------
# Search (cascade)
# --------------------
def bm25(coll, query: str, limit: int, return_props: List[str]):
    return coll.query.bm25(query=query, limit=limit, return_properties=return_props)

def hybrid(coll, query: str, alpha: float, limit: int, return_props: List[str]):
    # only works if vectorizer enabled; otherwise BM25 is used
    try:
        return coll.query.hybrid(query=query, alpha=alpha, limit=limit, return_properties=return_props)
    except Exception:
        return bm25(coll, query, limit, return_props)

def cascade_search(client: WeaviateClient, query: str, limit: int = 10, use_hybrid: bool = False, alpha: float = 0.5):
    results = []

    def add_results(objs, kind: str, text_field: str, id_field: str):
        for o in objs.objects:
            p = o.properties
            results.append({
                "kind": kind,
                "id": p.get(id_field, ""),
                "text": p.get(text_field, ""),
                "path": p.get("path", ""),
                "chunk_id": p.get("chunk_id", ""),
                "h1": p.get("h1", ""),
                "h2": p.get("h2", ""),
                "h3": p.get("h3", ""),
                "h4": p.get("h4", ""),
                "h5": p.get("h5", ""),
                "h6": p.get("h6", ""),
            })

    # Window
    coll = client.collections.get("Window")
    props = ["window_id","text","path","chunk_id","h1","h2","h3","h4","h5","h6"]
    res = hybrid(coll, query, alpha, limit, props) if use_hybrid else bm25(coll, query, limit, props)
    add_results(res, "window", "text", "window_id")
    if len(results) >= limit:
        return results[:limit]

    # Sentence
    coll = client.collections.get("Sentence")
    props = ["sentence_id","sentence_text","path","chunk_id","h1","h2","h3","h4","h5","h6"]
    res = hybrid(coll, query, alpha, limit, props) if use_hybrid else bm25(coll, query, limit, props)
    add_results(res, "sentence", "sentence_text", "sentence_id")
    if len(results) >= limit:
        return results[:limit]

    # Subchunk
    coll = client.collections.get("Subchunk")
    props = ["subchunk_id","subchunk_text","chunk_id"]
    res = hybrid(coll, query, alpha, limit, props) if use_hybrid else bm25(coll, query, limit, props)
    for o in res.objects:
        p = o.properties
        results.append({
            "kind": "subchunk",
            "id": p.get("subchunk_id",""),
            "text": p.get("subchunk_text",""),
            "path": "",
            "chunk_id": p.get("chunk_id",""),
            "h1":"", "h2":"", "h3":"", "h4":"", "h5":"", "h6":"",
        })
    if len(results) >= limit:
        return results[:limit]

    # Chunk
    coll = client.collections.get("Chunk")
    props = ["chunk_id","chunk_text"]
    res = hybrid(coll, query, alpha, limit, props) if use_hybrid else bm25(coll, query, limit, props)
    for o in res.objects:
        p = o.properties
        results.append({
            "kind": "chunk",
            "id": p.get("chunk_id",""),
            "text": p.get("chunk_text",""),
            "path": "",
            "chunk_id": p.get("chunk_id",""),
            "h1":"", "h2":"", "h3":"", "h4":"", "h5":"", "h6":"",
        })

    return results[:limit]

# --------------------
# CLI
# --------------------
def main():
    ap = argparse.ArgumentParser(description="Weaviate multi-tier setup + ingestion + cascade search (Window→Sentence→Subchunk→Chunk).")
    ap.add_argument("--url", default="http://localhost:8080", help="Weaviate HTTP URL")
    ap.add_argument("--grpc-port", type=int, default=50051, help="Weaviate gRPC port")
    ap.add_argument("--outdir", default="outputs", help="Directory containing CSVs")
    ap.add_argument("--setup", action="store_true", help="Create collections")
    ap.add_argument("--insert", action="store_true", help="Insert all CSVs")
    ap.add_argument("--search", default="", help="Run a cascade search for this query")
    ap.add_argument("--limit", type=int, default=10, help="Number of results to return")
    ap.add_argument("--hybrid", action="store_true", help="Use hybrid search if vectorizer is enabled")
    args = ap.parse_args()

    client = connect(args.url, args.grpc_port)
    try:
        if args.setup:
            create_collections(client, use_vectorizer=False)

        if args.insert:
            ingest_all(client, args.outdir)

        if args.search:
            hits = cascade_search(client, args.search, limit=args.limit, use_hybrid=args.hybrid)
            print(f"\n[Results] {len(hits)} objects")
            for i, h in enumerate(hits, start=1):
                path = f" | Path: {h['path']}" if h.get("path") else ""
                trail = " > ".join(x for x in [h.get("h1"),h.get("h2"),h.get("h3"),h.get("h4"),h.get("h5"),h.get("h6")] if x)
                if trail:
                    path = f" | Headings: {trail}"
                print(f"{i:>2}. [{h['kind']}] {h['id']} | {h['chunk_id']}{path}")
                print(f"    {h['text'][:180]}{'...' if len(h['text'])>180 else ''}")
    finally:
        client.close()

if __name__ == "__main__":
    main()
