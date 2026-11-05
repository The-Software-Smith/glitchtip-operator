#!/usr/bin/env bash
# End-to-end check against a real GlitchTip in Docker and a minikube cluster.
set -euo pipefail

cd "$(dirname "$0")"
root=$(git rev-parse --show-toplevel)
context=${KUBE_CONTEXT:-minikube}
tag=e2e-$(date +%s)
kc() { kubectl --context "$context" "$@"; }

docker compose up -d --wait
until curl -sf -o /dev/null http://localhost:8000/api/0/; do sleep 2; done
token=$(docker compose exec -T web ./manage.py shell < seed.py | sed -n 's/^TOKEN=//p')

docker build -t "glitchtip-operator:$tag" "$root"
minikube image load "glitchtip-operator:$tag"

helm --kube-context "$context" upgrade --install gto "$root/charts/glitchtip-operator" \
  -n glitchtip-operator --create-namespace \
  --set image.repository=glitchtip-operator --set image.tag="$tag" --set image.pullPolicy=Never \
  --set glitchtip.url=http://host.minikube.internal:8000 --set glitchtip.token="$token" \
  --set resyncIntervalSeconds=30 --wait

kc create namespace e2e-apps --dry-run=client -o yaml | kc apply -f -
kc -n e2e-apps apply -f "$root/examples/"
kc -n e2e-apps wait projectalert --all --for=jsonpath='{.status.conditions[0].status}'=True --timeout=120s
kc -n e2e-apps get projectalerts -o wide

curl -sf -H "Authorization: Bearer $token" http://localhost:8000/api/0/projects/e2e/api/alerts/ \
  | grep -q '"New issues to Slack"'
echo "e2e: ok"
