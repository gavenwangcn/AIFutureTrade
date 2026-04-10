from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class TradeMcpConfig:
    """
    Minimal config for connecting to a trade-mcp MCP server.

    This file intentionally keeps credentials OUT of source. Configure via env:
      - TRADE_MCP_URL: MCP server URL (SSE/HTTP endpoint as required by your deployment)
    """

    url: str


def load_trade_mcp_config() -> TradeMcpConfig:
    url = (os.getenv("TRADE_MCP_URL") or "").strip()
    if not url:
        raise RuntimeError(
            "Missing TRADE_MCP_URL environment variable (trade-mcp MCP server endpoint)."
        )
    return TradeMcpConfig(url=url)


class TradeMcpClient:
    """
    Thin wrapper around the Python MCP client library.

    Notes:
    - This is a template. Your environment must provide a reachable MCP endpoint.
    - We keep the implementation lightweight and import MCP modules lazily to reduce
      prompt/memory bloat when the skill is used (aligns with the skill's lazy-load guidance).
    """

    def __init__(self, cfg: TradeMcpConfig):
        self._cfg = cfg
        self._session = None

    async def __aenter__(self) -> "TradeMcpClient":
        # Lazy import to keep script startup small and skill prompt light.
        # The concrete transport class name depends on the MCP Python package version.
        from mcp import ClientSession  # type: ignore

        # Try to use an SSE-capable transport if present; fall back to a generic HTTP transport.
        transport = None
        try:
            from mcp.client.sse import SSEClientTransport  # type: ignore

            transport = SSEClientTransport(self._cfg.url)
        except Exception:
            try:
                from mcp.client.http import HttpClientTransport  # type: ignore

                transport = HttpClientTransport(self._cfg.url)
            except Exception as exc:
                raise RuntimeError(
                    "MCP transports not found. Ensure the Python 'mcp' package supports your endpoint."
                ) from exc

        self._session = ClientSession(transport)
        await self._session.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._session is not None:
            await self._session.__aexit__(exc_type, exc, tb)
            self._session = None

    async def call(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if self._session is None:
            raise RuntimeError("TradeMcpClient not started. Use 'async with TradeMcpClient(...)'.")
        # MCP tool call shape varies by library; we keep it minimal and return JSON-ish dict.
        res = await self._session.call_tool(tool_name, arguments)  # type: ignore
        # Many MCP clients return an object with `.content` or `.data`; normalize best-effort.
        if isinstance(res, dict):
            return res
        payload: Dict[str, Any] = {}
        for key in ("data", "content", "result"):
            if hasattr(res, key):
                payload[key] = getattr(res, key)
        payload.setdefault("raw", str(res))
        return payload

    async def klines_with_indicators(
        self, *, symbol: str, interval: str, limit: int = 200
    ) -> Dict[str, Any]:
        # trade-mcp tool name per skill: trade.market.klines_with_indicators
        return await self.call(
            "trade.market.klines_with_indicators",
            {"symbol": symbol, "interval": interval, "limit": limit},
        )

