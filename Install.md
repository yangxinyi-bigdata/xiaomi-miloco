# Docker 本地打包安装

## 从当前源码构建一个本地镜像

```bash
docker build --build-arg PIP_INDEX_URL=https://pypi.org/simple \
  -t xiaomi/miloco-backend:local \
  --target backend -f docker/backend.Dockerfile .
```

构建镜像并推送
docker buildx build \
  --platform linux/amd64 \
  --build-arg PIP_INDEX_URL=https://pypi.org/simple \
  --build-arg NPM_REGISTRY=https://registry.npmmirror.com \
  --target backend \
  -f docker/backend.Dockerfile \
  -t ghcr.io/yangxinyi-bigdata/miloco-backend:0.3.4 \
  --push .

## 直接用本地镜像启动

```bash
BACKEND_IMAGE=xiaomi/miloco-backend:local \
  docker compose -f docker/docker-compose-local.yaml up -d
```

## 打包成可拷贝安装包

```bash
scripts/package_docker.sh
```

默认输出到 `dist/docker/`，里面包含：

- `miloco-backend-local.tar`
- `docker-compose.yaml`
- `.env`
- `.env.example`
- `install.sh`
- `README.md`

在目标机器上进入该目录后执行：

```bash
./install.sh
```

## 查看日志

```bash
docker logs -f miloco-backend
```

## 停止

```bash
docker compose -f docker/docker-compose-local.yaml down
```
