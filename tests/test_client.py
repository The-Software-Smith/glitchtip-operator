import httpx
import pytest
import respx

from glitchtip_operator.client import GlitchTipClient, GlitchTipError

BASE = "https://errors.example.com"
ALERTS = f"{BASE}/api/0/projects/acme/api/alerts/"


@pytest.fixture
async def client():
    c = GlitchTipClient(BASE, "secret-token")
    yield c
    await c.aclose()


@respx.mock
async def test_list_follows_cursor_pagination(client):
    respx.get(ALERTS, params={"cursor": "abc"}).respond(json=[{"id": 2}])
    first = respx.get(ALERTS).mock(
        side_effect=[
            httpx.Response(
                200,
                json=[{"id": 1}],
                headers={
                    "Link": f'<{ALERTS}>; rel="previous"; results="false"; cursor="", '
                    f'<{ALERTS}?cursor=abc>; rel="next"; results="true"; cursor="abc"'
                },
            )
        ]
    )
    assert [a["id"] for a in await client.list_alerts("acme", "api")] == [1, 2]
    assert first.calls[0].request.headers["Authorization"] == "Bearer secret-token"


@respx.mock
async def test_stops_when_next_has_no_results(client):
    respx.get(ALERTS).respond(
        json=[{"id": 1}],
        headers={"Link": f'<{ALERTS}?cursor=x>; rel="next"; results="false"; cursor="x"'},
    )
    assert len(await client.list_alerts("acme", "api")) == 1


@respx.mock
async def test_create_update_delete(client):
    respx.post(ALERTS).respond(201, json={"id": 7})
    put = respx.put(f"{ALERTS}7/").respond(json={"id": 7})
    respx.delete(f"{ALERTS}7/").respond(204)
    respx.delete(f"{ALERTS}8/").respond(404)

    assert (await client.create_alert("acme", "api", {"name": "a"}))["id"] == 7
    await client.update_alert("acme", "api", 7, {"name": "b"})
    assert put.calls[0].request.content == b'{"name":"b"}'
    assert await client.delete_alert("acme", "api", 7) is True
    assert await client.delete_alert("acme", "api", 8) is False


@respx.mock
@pytest.mark.parametrize(
    ("status", "retryable"), [(403, False), (422, False), (429, True), (502, True)]
)
async def test_errors_carry_status(client, status, retryable):
    respx.get(ALERTS).respond(status, text="nope")
    with pytest.raises(GlitchTipError) as info:
        await client.list_alerts("acme", "api")
    assert info.value.status == status
    assert info.value.retryable is retryable


@respx.mock
async def test_network_errors_are_retryable(client):
    respx.get(ALERTS).mock(side_effect=httpx.ConnectError("down"))
    with pytest.raises(GlitchTipError) as info:
        await client.list_alerts("acme", "api")
    assert info.value.retryable
