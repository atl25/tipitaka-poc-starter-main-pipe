from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer
import os
import uvicorn

# Load LaBSE once at startup
MODEL_NAME = "sentence-transformers/LaBSE"
print(f"Loading model {MODEL_NAME} ...")
model = SentenceTransformer(MODEL_NAME)
print("Model loaded ✅")

# FastAPI app
app = FastAPI()

class EmbedRequest(BaseModel):
    text: str

class EmbedManyRequest(BaseModel):
    texts: list[str]

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/embed")
async def embed(req: EmbedRequest):
    try:
        vector = model.encode(req.text, convert_to_numpy=True).tolist()
        return {"vector": vector}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
        
@app.post("/embed-many")
def embed_many(req: EmbedManyRequest):
    try:
        vecs = model.encode(
            req.texts,
            batch_size=32,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False
        ).tolist()
        return {"vectors": vecs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
