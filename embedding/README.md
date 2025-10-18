Usage

Prod (Docker, K8s, ECS, etc.) →

docker run -p 8000:8000 embedding-service


Gunicorn auto-chooses workers based on CPU.

Dev (local) →

python app.py


Runs your single-worker uvicorn (from if __name__ == "__main__")


ETL shrinks: remove torch, transformers, sentence-transformers → drops from 7.8 GB → ~500 MB.

Embedding service optimized: model loaded once, reused by ETL + Search.

Batch API: efficient for large corpus ingestion.

Maintainability: one place controls embedding logic.