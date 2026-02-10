from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.api.chat_routes import router as chat_router

app = FastAPI(title="Numa 🐻")

# Static frontend
app.mount("/static", StaticFiles(directory="frontend"), name="static")


@app.get("/")
def home():
    return FileResponse("frontend/index.html")


# API routes
app.include_router(chat_router)
