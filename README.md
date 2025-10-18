Volume Reset

docker compose down
docker volume rm tipitaka-poc-starter-main-pipe_weaviate_data
docker compose up -d


weaviate တင်
./bootstrap.sh setup
./bootstrap.sh etl --steps all
./bootstrap.sh etl --steps clean,split,parse,join,embed
./bootstrap.sh etl --steps load
