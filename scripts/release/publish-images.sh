#!/usr/bin/env bash
# Registry authentication is supplied by the publishing job, not by the build.
set -euo pipefail
out=${1:?OCI archive directory}
[[ ${GITHUB_SHA:?source SHA} =~ ^[a-f0-9]{40}$ ]]
(cd "$out" && sha256sum --check SHA256SUMS)
repos=(ghcr.io/alchemmist/monori harbor.socrat.alchemmist.xyz/homelab/monori)
dest_flags=()
src_flags=()
if [[ ${2:-} == --rehearse-local ]]; then
  dest_flags=(--dest-tls-verify=false)
  src_flags=(--src-tls-verify=false)
  repos=(localhost:58129/mirror/monori localhost:58129/harbor/monori)
fi
manifest='{}'
for component in front back sync; do
  digest=''
  for repo in "${repos[@]}"; do
    skopeo copy "${dest_flags[@]}" --all --preserve-digests --digestfile "$out/$component.digest" \
      "oci-archive:$out/$component.tar" "docker://$repo:$component-$GITHUB_SHA"
    published=$(cat "$out/$component.digest")
    [[ $published =~ ^sha256:[0-9a-f]{64}$ ]]
    if [[ -n $digest && $digest != "$published" ]]; then
      echo "Registry digest mismatch for $component" >&2
      exit 1
    fi
    digest=$published
  done
  manifest=$(jq -c --arg key "$component" --arg value "$digest" '. + {($key): $value}' <<<"$manifest")
done
printf '%s\n' "$manifest" >"$out/images.json"
# Legacy compose consumers still follow the rolling component tags. Create
# these from immutable registry references, after all immutable pushes pass.
for component in front back sync; do
  for repo in "${repos[@]}"; do
    digest=$(jq -er --arg key "$component" '.[$key]' "$out/images.json")
    skopeo copy "${src_flags[@]}" "${dest_flags[@]}" --all --preserve-digests "docker://$repo@$digest" "docker://$repo:$component"
  done
done
