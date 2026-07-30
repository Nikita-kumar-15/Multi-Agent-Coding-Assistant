# app.py
"""
FastAPI application entrypoint.
Run: uvicorn app:app --reload
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.models.database import init_db
from backend.api import process, chat, debug, sessions, artifacts

app = FastAPI(title="AI Dev Team API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()

@app.on_event("startup")
def startup_event():
    import os
    
    provider = os.getenv("LLM_PROVIDER")
    default_model = os.getenv("DEFAULT_MODEL")
    api_key = os.getenv("CEREBRAS_API_KEY")

    if not all([provider, default_model, api_key]):
        raise ValueError("Missing required environment variables for LLM configuration. Ensure LLM_PROVIDER, DEFAULT_MODEL, and CEREBRAS_API_KEY are set in the .env file.")

    print(f"[STARTUP] Provider: {provider.capitalize()}")
    print(f"[STARTUP] Default Model: {default_model}")
    print(f"[STARTUP] Base URL: https://api.cerebras.ai/v1")
    
    from backend.services.model_router import get_model
    try:
        print("[STARTUP] Pinging LLM Provider to check API Key/Billing...")
        llm = get_model("conversation")
        
        # We don't want to use the full invoke with retries here, just a direct ping.
        llm.client.invoke("ping")
        print("[STARTUP] ✅ LLM Provider is healthy and responding.")
    except Exception as e:
        print(f"\n[STARTUP WARNING] ⚠️ Failed to reach model!\nReason: {e}\nPlease verify this model name is correct for your provider and that your API key has access to it.\n")

app.include_router(process.router)
app.include_router(chat.router)
app.include_router(debug.router)
app.include_router(sessions.router)
app.include_router(artifacts.router)


@app.get("/")
def root():
    return {"message": "AI Dev Team API is running."}


@app.get("/health")
def health_check():
    return {"status": "ok"}
