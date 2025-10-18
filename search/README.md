search/
│
├── utils.py        # Shared helper functions (embedding call, weaviate query, props, etc.)
├── cli.py          # CLI tool for developers (your current script, refactored)
└── app.py          # FastAPI service (production-ready API for search)

Example command 
```bash
docker compose run --rm search python cli.py --collection Window --mode hybrid --query "mettā" --k 10
```