import asyncio
import websockets

clients = set()

async def handler(websocket): # Removed 'path' argument
    clients.add(websocket)
    try:
        async for message in websocket:
            print(f"Received message from client: {message}")
            for client in clients:
                # Broadcast to all connected clients
                await client.send(message)
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        clients.remove(websocket)

async def main():
    async with websockets.serve(handler, "0.0.0.0", 8768):
        print("🌐 WebSocket Server running at ws://localhost:8768")
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())