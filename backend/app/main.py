"""FastAPI application entry."""
# Use the OS-native CA store on Windows so outbound HTTPS to LLM providers
# doesn't fail with [SSL: CERTIFICATE_VERIFY_FAILED]. Must run before any
# httpx/openai imports trigger their default SSL context.
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import alerts, dashboard, eval, feedback, health, intelligence, query, retrieve, upload
from app.core.config import get_settings
from app.core.logging import logger, setup_logging
from app.core.tracing import setup_tracing


def create_app() -> FastAPI:
    setup_logging()
    setup_tracing()
    settings = get_settings()

    app = FastAPI(
        title="Supply Chain Risk Intelligence Assistant",
        version="0.1.0",
        description="Multi-agent RAG for supply chain risk analysis.",
    )

    # CORS — allow localhost dev + any Render-hosted frontend
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://localhost:3000",
        ],
        allow_origin_regex=r"https://.*\.onrender\.com",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(query.router)
    app.include_router(retrieve.router)
    app.include_router(dashboard.router)
    app.include_router(intelligence.router)
    app.include_router(upload.router)
    app.include_router(alerts.router)
    app.include_router(feedback.router)
    app.include_router(eval.router)

    @app.on_event("startup")
    async def _startup() -> None:
        import asyncio
        logger.info(
            "Service starting | model={} | csv={}",
            settings.primary_llm_model,
            settings.data_csv_path,
        )
        # Run heavy init in background so uvicorn can bind the port immediately.
        asyncio.create_task(_background_init(app))

    async def _background_init(_app) -> None:
        import asyncio
        loop = asyncio.get_running_loop()

        # Pre-warm DataFrame in thread pool (CPU-bound)
        try:
            from app.services.analytics import get_df
            await loop.run_in_executor(None, get_df)
            logger.info("DataFrame pre-warmed.")
        except Exception as exc:
            logger.warning("DataFrame pre-warm failed: {}", exc)

        # Start proactive alerting scheduler
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from app.services.alerting import scan_and_alert

            scheduler = BackgroundScheduler()
            scheduler.add_job(scan_and_alert, "interval", minutes=15, id="alert_scan")
            scheduler.start()
            _app.state.scheduler = scheduler
            logger.info("APScheduler started — alert scans every 15 minutes.")
            await loop.run_in_executor(None, scan_and_alert)
            logger.info("Initial alert scan complete.")
        except ImportError:
            logger.warning("apscheduler not installed — proactive alerting disabled.")
        except Exception as exc:
            logger.warning("Alert scheduler failed to start: {}", exc)

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        scheduler = getattr(app.state, "scheduler", None)
        if scheduler:
            scheduler.shutdown(wait=False)

    return app


app = create_app()
