"""
WebSocket routes — Phase 3 + 4
Streams live market ticks and strategy status updates to the frontend.

Channels:
  /api/ws/feed?token=...         → user's tick feed (all subscribed instruments)
  /api/ws/strategy/{map_id}?token=... → live status for one strategy
"""
import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException

from app.core.security import decode_token
from app.core.redis_client import get_redis, user_tick_channel

logger = logging.getLogger(__name__)
router = APIRouter()


def _auth_ws(token: str) -> str:
    """Validate JWT and return user_id, or raise."""
    try:
        payload = decode_token(token)
        user_id = payload.get("sub")
        if not user_id:
            raise ValueError("No sub in token")
        return user_id
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")


@router.websocket("/feed")
async def market_feed(ws: WebSocket, token: str = Query(...)):
    """
    Stream all market ticks for the authenticated user.
    The frontend subscribes here to drive live price displays.
    """
    try:
        user_id = _auth_ws(token)
    except HTTPException:
        await ws.close(code=4001)
        return

    await ws.accept()
    redis = get_redis()
    pubsub = redis.pubsub()
    channel = user_tick_channel(user_id)
    await pubsub.subscribe(channel)

    logger.info(f"WS market feed connected: user={user_id}")

    async def _pump():
        async for message in pubsub.listen():
            if message["type"] == "message":
                await ws.send_text(message["data"])

    pump_task = asyncio.create_task(_pump())

    try:
        while True:
            # Keep-alive: receive ping from client
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        pump_task.cancel()
        await pubsub.unsubscribe(channel)
        logger.info(f"WS market feed disconnected: user={user_id}")


@router.websocket("/market")
async def market_live(ws: WebSocket, token: str = Query(...),
                      symbols: str = Query("NIFTY50,BANKNIFTY,RELIANCE")):
    """
    Stream Dhan market data to browser via WebSocket.
    Uses a single shared poller — all connected clients share one Dhan API call.
    """
    try:
        user_id = _auth_ws(token)
    except HTTPException:
        await ws.close(code=4001)
        return

    await ws.accept()

    # Register this client with the shared poller
    from app.market.market_poller import get_poller
    poller = get_poller()
    queue  = await poller.subscribe(symbols)
    logger.info(f"WS market connected: user={user_id} clients={poller.client_count}")

    try:
        while True:
            try:
                # Wait for next tick from shared poller (timeout 30s for keepalive)
                ticks = await asyncio.wait_for(queue.get(), timeout=30)
                await ws.send_text(json.dumps({"type": "ticks", "data": ticks}))
            except asyncio.TimeoutError:
                # Send keepalive ping
                await ws.send_text(json.dumps({"type": "ping"}))
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug(f"WS market client error: {e}")
    finally:
        await poller.unsubscribe(queue)
        logger.info(f"WS market disconnected: user={user_id} clients={poller.client_count}")
async def strategy_status(ws: WebSocket, map_id: str, token: str = Query(...)):
    """
    Stream live status updates for a single running strategy.
    Pushes: { status, daily_pnl, consecutive_losses, killed }
    """
    try:
        user_id = _auth_ws(token)
    except HTTPException:
        await ws.close(code=4001)
        return

    await ws.accept()
    redis = get_redis()
    pubsub = redis.pubsub()
    channel = f"strategy_status:{map_id}"
    await pubsub.subscribe(channel)

    # Send current state immediately on connect
    from app.core.redis_client import strategy_state_key
    raw = await redis.get(strategy_state_key(map_id))
    if raw:
        await ws.send_text(raw)

    logger.info(f"WS strategy status connected: map={map_id} user={user_id}")

    async def _pump():
        async for message in pubsub.listen():
            if message["type"] == "message":
                await ws.send_text(message["data"])

    pump_task = asyncio.create_task(_pump())

    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        pump_task.cancel()
        await pubsub.unsubscribe(channel)
        logger.info(f"WS strategy status disconnected: map={map_id}")
