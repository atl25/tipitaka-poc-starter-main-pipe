import argparse
import os
from utils import get_client, encode_query_remote, pick_return_props, short_text

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=os.getenv("WEAVIATE_URL", "http://localhost:8080")) #or use 8081 
    parser.add_argument("--grpc-port", type=int, default=int(os.getenv("WEAVIATE_GRPC_PORT", 50051))) #or use 50052
    parser.add_argument("--collection", required=True)
    parser.add_argument("--mode", choices=["bm25", "hybrid", "vector"], default="bm25")
    parser.add_argument("--query", required=True)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--alpha", type=float, default=0.5)
    return parser.parse_args()

def main():
    args = parse_args()
    print(f"🔗 Connecting to Weaviate at {args.url} (gRPC {args.grpc_port})")
    client = get_client(args.url, args.grpc_port)

    try:
        coll = client.collections.get(args.collection)
        props = pick_return_props(args.collection)

        if args.mode == "vector":
            qvec = encode_query_remote(args.query)
            res = coll.query.near_vector(near_vector=qvec, limit=args.k, return_properties=props)
        elif args.mode == "hybrid":
            qvec = encode_query_remote(args.query)
            res = coll.query.hybrid(query=args.query, vector=qvec, alpha=args.alpha, limit=args.k, return_properties=props)
        else:  # bm25
            res = coll.query.bm25(query=args.query, limit=args.k, return_properties=props)

        print(f"[results] {len(res.objects)} objects")
        for i, o in enumerate(res.objects or [], start=1):
            p = o.properties or {}
            kind = args.collection.lower()
            score = getattr(o.metadata, "score", None)
            score_str = f"{score:.4f}" if score is not None else "N/A"

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

            print(f"{i:>2}. {idx}{suffix} (score: {score_str})")
            print(f"    {short_text(text)}")

    finally:
        client.close()

if __name__ == "__main__":
    main()
