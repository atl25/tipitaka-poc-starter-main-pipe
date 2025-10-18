from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
from utils import get_client, encode_query_remote, pick_return_props

# ------------------------------------------------------
# Config (use env vars for flexibility in production)
# ------------------------------------------------------

WEAVIATE_URL = os.getenv("WEAVIATE_URL", "http://weaviate:8080")
WEAVIATE_GRPC_PORT = int(os.getenv("WEAVIATE_GRPC_PORT", 50051))
COLLECTION = os.getenv("WEAVIATE_COLLECTION", "Chunk")

# ------------------------------------------------------
# FastAPI app
# ------------------------------------------------------

app = FastAPI()

# Pydantic request schema
class SearchRequest(BaseModel):
    query: str
    mode: str = "bm25"   # "bm25", "vector", or "hybrid"
    k: int = 5
    alpha: float = 0.5   # only for hybrid

@app.get("/health")
async def health():
    """
    Health check endpoint.
    Useful for bootstrap.sh readiness checks.
    """
    try:
        client = get_client(WEAVIATE_URL, WEAVIATE_GRPC_PORT)
        # simple ping (doesn't throw if available)
        client.close()
        return {"status": "ok", "service": "search"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Service unhealthy: {e}")


@app.post("/search")
async def search(req: SearchRequest):
    try:
        client = get_client(WEAVIATE_URL, WEAVIATE_GRPC_PORT)
        coll = client.collections.get(COLLECTION)
        props = pick_return_props(COLLECTION)

        if req.mode == "vector":
            qvec = encode_query_remote(req.query)
            res = coll.query.near_vector(near_vector=qvec, limit=req.k, return_properties=props)
        elif req.mode == "hybrid":
            qvec = encode_query_remote(req.query)
            res = coll.query.hybrid(query=req.query, vector=qvec, alpha=req.alpha, limit=req.k, return_properties=props)
        else:
            res = coll.query.bm25(query=req.query, limit=req.k, return_properties=props)

        return res.dict()  # JSON response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        client.close()

# ✅ Dev mode: can run directly
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
