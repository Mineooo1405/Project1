from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import ws_test_handlers

app = FastAPI(title="Robot Dashboard Backend")

# Thêm CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Trong môi trường production, chỉ định nguồn cụ thể
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Thêm router test WebSocket
app.include_router(ws_test_handlers.router)

# Route mặc định
@app.get("/")
async def root():
    return {"message": "Robot Dashboard API"}

# Khởi động server
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)