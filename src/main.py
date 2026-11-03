import json
import logging
import sys
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from api.endpoints import load_artifacts
from api.endpoints import router as api_router

logger = logging.getLogger("housing_api")
logger.setLevel(logging.INFO)
logger.addHandler(logging.StreamHandler(sys.stdout))


@asynccontextmanager
async def lifespan(app: FastAPI):
    (
        app.state.model,
        app.state.model_features,
        app.state.demographics_by_zip,
        app.state.imputer,
    ) = load_artifacts()
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_request(request: Request, call_next):
    """Log path, status, latency and zipcode (or batch size) for each request."""
    start = time.perf_counter()
    status = 500  # if the endpoint raises, the client receives a 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        if request.url.path != "/health":
            entry = {
                "path": request.url.path,
                "status": status,
                "latency_ms": round((time.perf_counter() - start) * 1000, 2),
                "zipcode": getattr(request.state, "zipcode", None),
                "rows": getattr(request.state, "rows", None),
            }
            logger.info(json.dumps(entry))


app.include_router(api_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
