# 重新构建
docker build --build-arg PIP_INDEX_URL=https://pypi.org/simple \
  -t ghcr.io/xiaomi/miloco-backend:latest \
  --target backend -f docker/backend.Dockerfile .

# 启动
DOCKER_REPO=ghcr.io/ docker compose -f docker/docker-compose-lite.yaml up -d

# 查看日志
docker logs -f miloco-backend

# 停止
DOCKER_REPO=ghcr.io/ docker compose -f docker/docker-compose-lite.yaml down