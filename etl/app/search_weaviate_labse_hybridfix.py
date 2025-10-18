import argparse
import os
from typing import List
import numpy as np
import requests

from weaviate import WeaviateClient
from weaviate.connect import ConnectionParams

# Config
EMBEDDING_URL = os.getenv("EMBEDDING_SERVICE_URL", "http://localhost:8000/embed-many")


def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--url",
        default=os.getenv("WEAVIATE_URL", "http://localhost:8090"),
        help="Weaviate REST URL (default: from WEAVIATE_URL env or localhost:8090)"
    )
    parser.add_argument(
        "--grpc-port",
        type=int,
        default=int(os.getenv("WEAVIATE_GRPC_PORT", 50051)),
        help="Weaviate gRPC port (default: from WEAVIATE_GRPC_PORT env or 50051)"
    )
    parser.add_argument(
        "--collection",
        required=True,
        help="Name of the collection / class"
    )
    parser.add_argument(
        "--mode",
        choices=["bm25", "hybrid", "vector"],
        default="bm25",
        help="Search mode (default: bm25)"
    )
    parser.add_argument(
        "--query",
        required=True,
        help="Search query text"
    )
    parser.add_argument(
        "--k",
        type=int,
        default=5,
        help="Number of results to return (default: 5)"
    )
    parser.add_argument(
        "--alpha", 
        type=float, 
        default=0.5, 
        help="hybrid alpha (0..1) higher favors vector"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="sentence-transformers/LaBSE",
        help="Embedding model to use for vector search (kept for compatibility)"
    )

    return parser.parse_args()


def get_client(url: str, grpc_port: int) -> WeaviateClient:
    cp = ConnectionParams.from_url(url, grpc_port=grpc_port)
    client = WeaviateClient(cp)
    client.connect()
    return client


def encode_query_remote(text: str) -> np.ndarray:
    """
    Send query to embedding service (/embed-many with a single text).
    """
    try:
        resp = requests.post(
            EMBEDDING_URL,
            json={"texts": [text]},
            timeout=15
        )
        resp.raise_for_status()
        vecs = np.array(resp.json()["vectors"], dtype=np.float32)
        return vecs[0]  # single vector
    except Exception as e:
        raise SystemExit(f"❌ Embedding service failed: {e}")


def pick_return_props(coll_name: str) -> List[str]:
    if coll_name == "Window":
        return ["window_id", "text", "chunk_id", "path", "h1", "h2", "h3", "h4", "h5", "h6"]
    if coll_name == "Sentence":
        return ["sentence_id", "sentence_text", "chunk_id", "path", "h1", "h2", "h3", "h4", "h5", "h6"]
    if coll_name == "Subchunk":
        return ["subchunk_id", "subchunk_text", "chunk_id"]
    if coll_name == "Chunk":
        return ["chunk_id", "chunk_text"]
    return []


def short_text(s: str, n: int = 180) -> str:
    s = s or ""
    s = " ".join(s.split())
    return s[:n] + ("..." if len(s) > n else "")


def main():
    args = parse_args()
    print(f"🔗 Connecting to Weaviate at {args.url} (gRPC {args.grpc_port})")
    
    client = get_client(args.url, args.grpc_port)
    try:
        coll = client.collections.get(args.collection)
        props = pick_return_props(args.collection)

        if args.mode == "vector":
            qvec = encode_query_remote(args.query)
            res = coll.query.near_vector(
                near_vector=qvec,
                limit=args.k,
                return_properties=props,
            )
        elif args.mode == "hybrid":
            qvec = encode_query_remote(args.query)
            res = coll.query.hybrid(
                query=args.query,
                vector=qvec,
                alpha=args.alpha,
                limit=args.k,
                return_properties=props,
            )
        else:  # bm25
            res = coll.query.bm25(
                query=args.query,
                limit=args.k,
                return_properties=props,
            )

        print(f"[results] {len(res.objects)} objects")
        for i, o in enumerate(res.objects or [], start=1):
            p = o.properties or {}
            kind = args.collection.lower()
            if args.collection == "Window":
                idx = f"[{kind}] {p.get('window_id','')} | chunk={p.get('chunk_id','')}"
                text = p.get("text", "")
                trail = " > ".join(x for x in [p.get("h1"), p.get("h2"), p.get("h3"), p.get("h4"), p.get("h5"), p.get("h6")] if x)
                suffix = f" | Headings: {trail}" if trail else ""
            elif args.collection == "Sentence":
                idx = f"[{kind}] {p.get('sentence_id','')} | chunk={p.get('chunk_id','')}"
                text = p.get("sentence_text", "")
                suffix = ""
            elif args.collection == "Subchunk":
                idx = f"[{kind}] {p.get('subchunk_id','')} | chunk={p.get('chunk_id','')}"
                text = p.get("subchunk_text", "")
                suffix = ""
            else:
                idx = f"[{kind}] {p.get('chunk_id','')}"
                text = p.get("chunk_text", "")
                suffix = ""

            print(f"{i:>2}. {idx}{suffix}")
            print(f"    {short_text(text)}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
