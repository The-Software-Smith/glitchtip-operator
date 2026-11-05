# glitchtip-operator

A Kubernetes operator that manages [GlitchTip](https://glitchtip.com) project alerts as
`ProjectAlert` resources, so alert rules and their Slack, Teams, Discord and other
destinations live in Git instead of the GlitchTip UI.

```yaml
apiVersion: glitchtip.softwaresmith.io/v1alpha1
kind: ProjectAlert
metadata:
  name: api-new-issues
  namespace: my-app
spec:
  organization: acme
  project: api
  errors:
    quantity: 1
    timespanMinutes: 1
  recipients:
    - type: webhook
      urlFrom:
        secretKeyRef:
          name: slack-webhook
          key: url
      tagsToAdd: [service, environment]
```

## Install

```sh
helm install glitchtip-operator oci://ghcr.io/the-software-smith/charts/glitchtip-operator \
  -n glitchtip-operator --create-namespace \
  --set glitchtip.url=https://glitchtip.example.com \
  --set glitchtip.existingSecret=glitchtip-api-token
```

The API token belongs to a GlitchTip user who must be an admin of each organization the
operator manages. Give it the `project:write` scope to create and update alerts, and
`project:admin` to delete them.

| Value | Default | |
|---|---|---|
| `glitchtip.url` | — | GlitchTip base URL (required) |
| `glitchtip.token` / `glitchtip.existingSecret` | — | API token, inline or from a Secret (`existingSecretKey`, default `token`) |
| `watchNamespaces` | `[]` | Namespaces to watch; empty means all, using a ClusterRole |
| `resyncIntervalSeconds` | `300` | How often every alert is compared with GlitchTip and drift is reverted |
| `retryDelaySeconds` | `60` | Retry delay after a temporary failure |
| `crds.install` / `crds.keep` | `true` / `true` | Install the CRD and keep it on uninstall |

## Spec

| Field | |
|---|---|
| `organization`, `project` | GlitchTip slugs (required) |
| `name` | Alert name in GlitchTip; defaults to `metadata.name` |
| `errors.quantity`, `errors.timespanMinutes` | Notify when an issue gets `quantity` events in `timespanMinutes`. Each issue notifies once per alert, so `1`/`1` means "every new issue" |
| `uptime` | Also notify on uptime monitor failures |
| `deletionPolicy` | `Delete` (default) removes the GlitchTip alert with the resource; `Orphan` leaves it |
| `recipients[].type` | `webhook` (Slack-compatible), `email`, `discord`, `googlechat`, `teams`, `ntfy`, `feishu`, `zulip` |
| `recipients[].url` / `urlFrom.secretKeyRef` | Destination URL, inline or from a Secret in the same namespace |
| `recipients[].tagsToAdd` | Event tags to include in the notification |
| `recipients[].zulip` | `botEmail`, `channel`, `topic`, `apiKeyFrom.secretKeyRef` |

At least one of `errors` and `uptime` is required. An `email` recipient mails the
project's team members.

## Behaviour

- **Ownership.** The GlitchTip alert id is recorded in `status.alertId`. On first sync, an
  existing alert with the same name is adopted rather than duplicated. If several alerts
  share the name, the resource reports `Conflict` and nothing is changed.
- **Drift.** Every `resyncIntervalSeconds`, the operator compares each alert with its spec
  and overwrites any edits made in the UI. The same resync also picks up rotated Secret
  values.
- **Moving.** Changing `organization` or `project` deletes the old alert (unless
  `deletionPolicy: Orphan`) and creates one in the new project.
- **Status.** `kubectl get projectalerts` shows a `Ready` condition with reason `Synced`,
  `InvalidSpec`, `Conflict`, `SecretNotFound` or `GlitchTipError`. Events are posted when
  an alert is created or updated, and when the failure reason changes.

## Development

```sh
pip install -e '.[dev]'
pytest
ruff check . && ruff format --check .
```

`hack/e2e/run.sh` starts GlitchTip in Docker Compose, then builds the image, installs the
chart into minikube and applies `examples/`.

Run the operator locally against your current kube context:

```sh
GLITCHTIP_URL=http://localhost:8000 GLITCHTIP_TOKEN=... \
  kopf run --standalone -m glitchtip_operator.handlers --all-namespaces
```

Tested against GlitchTip 6.2.

## License

Apache-2.0
