"""Async HTTP forwarder — proxies requests to upstream APIs."""

import httpx


async def forward_request(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    headers: dict,
    body: bytes,
    stream: bool = False,
) -> tuple[httpx.Response, bytes]:
    """Forward request to upstream and return (response, full_body)."""

    # Strip hop-by-hop headers
    skip = {"host", "content-length", "transfer-encoding", "connection"}
    clean_headers = {k: v for k, v in headers.items() if k.lower() not in skip}

    response = await client.request(
        method=method,
        url=url,
        headers=clean_headers,
        content=body,
    )

    full_body = response.content
    return response, full_body
