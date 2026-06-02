#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

IMAGE_REPOSITORY="${IMAGE_REPOSITORY:-yangxinyi-bigdata/miloco-backend}"
IMAGE_TAG="${IMAGE_TAG:-local}"
BACKEND_IMAGE="${IMAGE_REPOSITORY}:${IMAGE_TAG}"
OUTPUT_DIR="${1:-$PROJECT_ROOT/dist/docker}"
PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.org/simple}"

TAR_FILE="$OUTPUT_DIR/miloco-backend-${IMAGE_TAG}.tar"

mkdir -p "$OUTPUT_DIR"

echo "Building Docker image: $BACKEND_IMAGE"
docker build \
  --build-arg "PIP_INDEX_URL=$PIP_INDEX_URL" \
  -t "$BACKEND_IMAGE" \
  --target backend \
  -f "$PROJECT_ROOT/docker/backend.Dockerfile" \
  "$PROJECT_ROOT"

echo "Saving Docker image: $TAR_FILE"
docker save -o "$TAR_FILE" "$BACKEND_IMAGE"

cp "$PROJECT_ROOT/docker/docker-compose-local.yaml" "$OUTPUT_DIR/docker-compose.yaml"
cp "$PROJECT_ROOT/docker/.env.example" "$OUTPUT_DIR/.env.example"
cp "$PROJECT_ROOT/docker/.env.example" "$OUTPUT_DIR/.env"

cat > "$OUTPUT_DIR/install.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
cd "\$SCRIPT_DIR"

docker load -i "miloco-backend-${IMAGE_TAG}.tar"
BACKEND_IMAGE="${BACKEND_IMAGE}" docker compose -f docker-compose.yaml up -d

echo "Miloco backend is starting on https://127.0.0.1:\${BACKEND_PORT:-8000}"
echo "Use: docker logs -f miloco-backend"
EOF
chmod +x "$OUTPUT_DIR/install.sh"

cat > "$OUTPUT_DIR/README.md" <<EOF
# Miloco Docker Package

This package was built from the current source tree.

Configuration defaults are in \`.env\`.

## Install

\`\`\`bash
./install.sh
\`\`\`

## Manual install

\`\`\`bash
docker load -i miloco-backend-${IMAGE_TAG}.tar
BACKEND_IMAGE=${BACKEND_IMAGE} docker compose -f docker-compose.yaml up -d
docker logs -f miloco-backend
\`\`\`

## Stop

\`\`\`bash
docker compose -f docker-compose.yaml down
\`\`\`
EOF

echo "Docker package created at: $OUTPUT_DIR"
echo "Install with: $OUTPUT_DIR/install.sh"
