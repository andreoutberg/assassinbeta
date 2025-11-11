"""WebSocket endpoint for real-time dashboard updates."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Set, Dict, List, Optional
import asyncio
import logging
import json
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)

router = APIRouter()

# Store active WebSocket connections
active_connections: Set[WebSocket] = set()


class ConnectionManager:
    """Manages WebSocket connections and broadcasts."""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.heartbeat_tasks: Dict[WebSocket, asyncio.Task] = {}
        self.subscriptions: Dict[WebSocket, Dict[str, List[str]]] = {}
        self.pending_acks: Dict[str, Dict] = {}  # message_id -> {websocket, message, timestamp}

    async def connect(self, websocket: WebSocket):
        """Accept and store a new WebSocket connection."""
        await websocket.accept()
        self.active_connections.add(websocket)
        self.subscriptions[websocket] = {"symbols": [], "phases": []}

        # Start heartbeat task for this connection
        heartbeat_task = asyncio.create_task(self._heartbeat_loop(websocket))
        self.heartbeat_tasks[websocket] = heartbeat_task

        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection."""
        self.active_connections.discard(websocket)

        # Cancel heartbeat task
        if websocket in self.heartbeat_tasks:
            self.heartbeat_tasks[websocket].cancel()
            del self.heartbeat_tasks[websocket]

        # Clean up subscriptions
        if websocket in self.subscriptions:
            del self.subscriptions[websocket]

        # Clean up pending acknowledgments
        self._clean_pending_acks_for_websocket(websocket)

        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")

    async def _heartbeat_loop(self, websocket: WebSocket):
        """Send periodic heartbeat pings every 30 seconds."""
        try:
            while websocket in self.active_connections:
                await asyncio.sleep(30)
                try:
                    await websocket.send_json({"type": "heartbeat", "data": {"timestamp": datetime.utcnow().isoformat()}})
                    logger.debug(f"Heartbeat sent to websocket")
                except Exception as e:
                    logger.error(f"Failed to send heartbeat: {e}")
                    self.disconnect(websocket)
                    break
        except asyncio.CancelledError:
            logger.debug("Heartbeat task cancelled")

    def _clean_pending_acks_for_websocket(self, websocket: WebSocket):
        """Remove all pending acknowledgments for a specific websocket."""
        to_remove = [msg_id for msg_id, data in self.pending_acks.items() if data["websocket"] == websocket]
        for msg_id in to_remove:
            del self.pending_acks[msg_id]

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """Send a message to a specific WebSocket connection."""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Error sending personal message: {e}")

    def subscribe(self, websocket: WebSocket, channel_type: str, channel_value: str):
        """Subscribe a websocket to a specific channel (symbol or phase)."""
        if websocket not in self.subscriptions:
            self.subscriptions[websocket] = {"symbols": [], "phases": []}

        if channel_type == "symbol" and channel_value not in self.subscriptions[websocket]["symbols"]:
            self.subscriptions[websocket]["symbols"].append(channel_value)
            logger.info(f"WebSocket subscribed to symbol: {channel_value}")
        elif channel_type == "phase" and channel_value not in self.subscriptions[websocket]["phases"]:
            self.subscriptions[websocket]["phases"].append(channel_value)
            logger.info(f"WebSocket subscribed to phase: {channel_value}")

    def unsubscribe(self, websocket: WebSocket, channel_type: str, channel_value: str):
        """Unsubscribe a websocket from a specific channel."""
        if websocket not in self.subscriptions:
            return

        if channel_type == "symbol" and channel_value in self.subscriptions[websocket]["symbols"]:
            self.subscriptions[websocket]["symbols"].remove(channel_value)
            logger.info(f"WebSocket unsubscribed from symbol: {channel_value}")
        elif channel_type == "phase" and channel_value in self.subscriptions[websocket]["phases"]:
            self.subscriptions[websocket]["phases"].remove(channel_value)
            logger.info(f"WebSocket unsubscribed from phase: {channel_value}")

    def _should_send_to_client(self, websocket: WebSocket, message: dict) -> bool:
        """Check if a message should be sent to a specific client based on subscriptions."""
        if websocket not in self.subscriptions:
            return True  # Send to all if no subscriptions

        subs = self.subscriptions[websocket]

        # If client has no subscriptions, send everything
        if not subs["symbols"] and not subs["phases"]:
            return True

        # Check symbol subscription
        message_symbol = message.get("data", {}).get("symbol")
        if subs["symbols"] and message_symbol:
            if message_symbol not in subs["symbols"]:
                return False

        # Check phase subscription
        message_phase = message.get("data", {}).get("phase")
        if subs["phases"] and message_phase:
            if message_phase not in subs["phases"]:
                return False

        return True

    async def broadcast(self, message: dict, require_ack: bool = False):
        """Broadcast a message to all connected WebSocket clients with optional acknowledgment."""
        # Generate message ID if acknowledgment is required
        message_id = str(uuid.uuid4()) if require_ack else None
        if message_id:
            message["message_id"] = message_id
            message["require_ack"] = True

        # Use asyncio.gather for parallel sending (non-blocking)
        send_tasks = []
        for connection in list(self.active_connections):
            # Check if message should be sent to this client based on subscriptions
            if not self._should_send_to_client(connection, message):
                continue

            send_tasks.append(self._send_with_retry(connection, message, message_id))

        # Send to all clients in parallel
        if send_tasks:
            await asyncio.gather(*send_tasks, return_exceptions=True)

    async def _send_with_retry(self, websocket: WebSocket, message: dict, message_id: Optional[str] = None):
        """Send message to a single client with retry logic."""
        try:
            await websocket.send_json(message)

            # Track for acknowledgment if required
            if message_id:
                self.pending_acks[message_id] = {
                    "websocket": websocket,
                    "message": message,
                    "timestamp": datetime.utcnow(),
                    "retries": 0
                }

                # Schedule acknowledgment check (5 seconds timeout)
                asyncio.create_task(self._check_acknowledgment(message_id))

        except WebSocketDisconnect:
            self.disconnect(websocket)
        except Exception as e:
            logger.error(f"Error broadcasting to connection: {e}")
            self.disconnect(websocket)

    async def _check_acknowledgment(self, message_id: str):
        """Check if a message was acknowledged, resend if not."""
        await asyncio.sleep(5)  # Wait 5 seconds for acknowledgment

        if message_id not in self.pending_acks:
            return  # Already acknowledged

        ack_data = self.pending_acks[message_id]
        websocket = ack_data["websocket"]
        message = ack_data["message"]
        retries = ack_data["retries"]

        # Max 3 retries
        if retries >= 3:
            logger.warning(f"Message {message_id} not acknowledged after 3 retries, giving up")
            del self.pending_acks[message_id]
            return

        # Resend message
        logger.info(f"Resending message {message_id} (retry {retries + 1}/3)")
        ack_data["retries"] += 1

        try:
            await websocket.send_json(message)
            # Schedule another check
            asyncio.create_task(self._check_acknowledgment(message_id))
        except Exception as e:
            logger.error(f"Failed to resend message {message_id}: {e}")
            del self.pending_acks[message_id]
            self.disconnect(websocket)

    def acknowledge_message(self, message_id: str):
        """Mark a message as acknowledged."""
        if message_id in self.pending_acks:
            logger.debug(f"Message {message_id} acknowledged")
            del self.pending_acks[message_id]


manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time updates.

    Clients will receive messages in the format:
    {
        "type": "signal" | "strategy" | "optimization" | "alert" | "stats",
        "data": {...}
    }
    """
    await manager.connect(websocket)

    try:
        # Send initial connection success message
        await manager.send_personal_message(
            {
                "type": "connection",
                "data": {"status": "connected", "message": "WebSocket connection established"}
            },
            websocket
        )

        # Keep connection alive and listen for messages
        while True:
            try:
                # Wait for any message from client (can be used for heartbeat/ping)
                data = await websocket.receive_text()

                # Handle ping/pong for connection keep-alive
                if data == "ping":
                    await manager.send_personal_message(
                        {"type": "pong", "data": {}},
                        websocket
                    )
                else:
                    # Parse message
                    try:
                        message = json.loads(data)
                        msg_type = message.get("type")

                        # Handle subscribe message
                        if msg_type == "subscribe":
                            channel_type = message.get("channel_type")  # "symbol" or "phase"
                            channel_value = message.get("channel_value")  # e.g., "BTCUSDT" or "phase_1"

                            if channel_type and channel_value:
                                manager.subscribe(websocket, channel_type, channel_value)
                                await manager.send_personal_message(
                                    {
                                        "type": "subscribed",
                                        "data": {"channel_type": channel_type, "channel_value": channel_value}
                                    },
                                    websocket
                                )

                        # Handle unsubscribe message
                        elif msg_type == "unsubscribe":
                            channel_type = message.get("channel_type")
                            channel_value = message.get("channel_value")

                            if channel_type and channel_value:
                                manager.unsubscribe(websocket, channel_type, channel_value)
                                await manager.send_personal_message(
                                    {
                                        "type": "unsubscribed",
                                        "data": {"channel_type": channel_type, "channel_value": channel_value}
                                    },
                                    websocket
                                )

                        # Handle acknowledgment message
                        elif msg_type == "ack":
                            message_id = message.get("message_id")
                            if message_id:
                                manager.acknowledge_message(message_id)

                        # Handle heartbeat response from client
                        elif msg_type == "pong":
                            logger.debug("Received pong from client")

                        else:
                            logger.debug(f"Received WebSocket message: {message}")

                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON received: {data}")

            except WebSocketDisconnect:
                logger.info("Client disconnected normally")
                break
            except Exception as e:
                logger.error(f"Error in WebSocket loop: {e}")
                break

    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        manager.disconnect(websocket)


async def broadcast_signal_update(signal_data: dict):
    """Broadcast a signal update to all connected clients."""
    await manager.broadcast({
        "type": "signal",
        "data": signal_data
    })


async def broadcast_strategy_update(strategy_data: dict):
    """Broadcast a strategy update to all connected clients."""
    await manager.broadcast({
        "type": "strategy",
        "data": strategy_data
    })


async def broadcast_optimization_update(optimization_data: dict):
    """Broadcast an optimization update to all connected clients."""
    await manager.broadcast({
        "type": "optimization",
        "data": optimization_data
    })


async def broadcast_alert(alert_data: dict):
    """Broadcast an alert to all connected clients."""
    await manager.broadcast({
        "type": "alert",
        "data": alert_data
    })


async def broadcast_stats_update(stats_data: dict):
    """Broadcast stats update to all connected clients."""
    await manager.broadcast({
        "type": "stats",
        "data": stats_data
    })
