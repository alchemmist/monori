#!/usr/bin/env bash
# Build once; publish-image jobs must consume these exact OCI archives.
set -euo pipefail
out=${1:?output directory}
mkdir -p "$out"
for component in front back sync; do
  docker buildx build --platform linux/amd64 --file "deploy/Dockerfile.$component" \
    --output "type=oci,dest=$out/$component.tar" .
done
(cd "$out" && sha256sum front.tar back.tar sync.tar >SHA256SUMS)
