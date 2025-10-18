import os
import requests
import numpy as np
from typing import List
from weaviate import WeaviateClient
from weaviate.connect import ConnectionParams

# Config
EMBEDDING_SERVICE_URL = os.getenv("EMBEDDING_SERVICE_URL", "http://localhost:8001/embed")

def get_client(url: str, grpc_port: int) -> WeaviateClient:
    cp = ConnectionParams.from_url(url, grpc_port=grpc_port)
    client = WeaviateClient(cp)
    client.connect()
    return client

def encode_query_remote(text: str) -> np.ndarray:
    """
    Send text to embedding service and get back a vector.
    """
    resp = requests.post(
        EMBEDDING_SERVICE_URL,
        json={"text": text},
        timeout=10
    )
    resp.raise_for_status()
    data = resp.json()
    return np.array(data["vector"], dtype=np.float32)

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
