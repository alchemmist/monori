#!/usr/bin/env bash
# Registry authentication is supplied by the publishing job, not by the build.
set -euo pipefail
out=${1:?OCI archive directory}
[[ ${GITHUB_SHA:?source SHA} =~ ^[a-f0-9]{40}$ ]]
(cd "$out" && sha256sum --check SHA256SUMS)
manifest='{}'
for component in front back sync; do
  for repo in ghcr.io/alchemmist/monori harbor.socrat.alchemmist.xyz/homelab/monori; do
    skopeo copy --all --preserve-digests --digestfile "$out/$component.digest" \
      "oci-archive:$out/$component.tar" "docker://$repo:$component-$GITHUB_SHA"
  done
  digest=$(cat "$out/$component.digest")
  [[ $digest =~ ^sha256:[0-9a-f]{64}$ ]]
  manifest=$(jq -c --arg key "$component" --arg value "$digest" '. + {($key): $value}' <<<"$manifest")
done
printf '%s\n' "$manifest" > "$out/images.json"
# Legacy compose consumers still follow the rolling component tags. Create
# these from immutable registry references, after all immutable pushes pass.
for component in front back sync; do
  for repo in ghcr.io/alchemmist/monori harbor.socrat.alchemmist.xyz/homelab/monori; do
    digest=$(jq -er --arg key "$component" '.[$key]' "$out/images.json")
    skopeo copy --all --preserve-digests "docker://$repo@$digest" "docker://$repo:$component"
  done
done
