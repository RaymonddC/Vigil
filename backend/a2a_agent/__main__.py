"""Allow `python -m backend.a2a_agent` to launch the A2A agent."""

from backend.a2a_agent.app import A2A_PORT, app  # noqa: F401

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.a2a_agent.app:app",
        host="0.0.0.0",
        port=A2A_PORT,
        log_level="info",
    )
