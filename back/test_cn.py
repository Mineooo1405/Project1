# Save as test_connection.py
import asyncio
import websockets

async def test():
    try:
        async with websockets.connect("ws://localhost:8000/ws/server") as websocket:
            print("Connected successfully!")
            await websocket.send('{"type":"ping"}')
            response = await websocket.recv()
            print(f"Received: {response}")
    except Exception as e:
        print(f"Connection failed: {e}")

asyncio.run(test())