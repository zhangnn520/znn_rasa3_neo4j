docker rm -f redis
docker run -p 6379:6379 --name redis -v $(pwd)/redis_docker/redis.conf:/etc/redis/redis.conf -v $(pwd)/redis_docker/data:/data -d redis redis-server /etc/redis/redis.conf
