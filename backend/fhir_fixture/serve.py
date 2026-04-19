"""
Launch script for the FHIR fixture server.

    FHIR_BACKEND=fixture python -m backend.fhir_fixture.serve
    # or
    FHIR_BACKEND=fixture uvicorn backend.fhir_fixture.main:app --port 8080

The fixture server listens on port 8080 (same port as HAPI) so the FHIR
client can point at ``http://localhost:8080/fhir`` unchanged.
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "backend.fhir_fixture.main:app",
        host="127.0.0.1",
        port=8080,
        reload=False,
        log_level="info",
    )
