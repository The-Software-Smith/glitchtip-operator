from __future__ import annotations

import asyncio
import base64

from kubernetes import client as k8s
from kubernetes import config as k8s_config
from kubernetes.client.rest import ApiException


class SecretNotFound(Exception):
    pass


class SecretReader:
    def __init__(self) -> None:
        try:
            k8s_config.load_incluster_config()
        except k8s_config.ConfigException:
            k8s_config.load_kube_config()
        self._api = k8s.CoreV1Api()

    async def __call__(self, namespace: str, name: str, key: str) -> str:
        try:
            secret = await asyncio.to_thread(self._api.read_namespaced_secret, name, namespace)
        except ApiException as exc:
            if exc.status == 404:
                raise SecretNotFound(f"secret {namespace}/{name} not found") from exc
            raise
        value = (secret.data or {}).get(key)
        if value is None:
            raise SecretNotFound(f"secret {namespace}/{name} has no key {key!r}")
        return base64.b64decode(value).decode()
