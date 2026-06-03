import logging
import sys
from pathlib import Path
from typing import Optional

import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent))
from config.log_setup import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

from database.db_manager import get_db_manager
from llm_manager import LLMRunner
from api_router import router as api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    global llm
    llm = LLMRunner()
    logger.info("LLMRunner initialized")
    # Reset stale ACTIVE statuses from crashed pipelines
    try:
        db = get_db_manager()
        db.execute_query("UPDATE specialist_registry SET status = 'IDLE' WHERE status = 'ACTIVE'")
        logger.info("Reset stale ACTIVE specialist statuses")
    except Exception as e:
        logger.warning(f"Failed to reset stale ACTIVE: {e}")
    yield
    if llm:
        if hasattr(llm, '_session') and llm._session:
            await llm._session.aclose()
        logger.info("LLMRunner session closed")


app = FastAPI(title="Expertia Query API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8011",
        "http://localhost:8080",
        "http://127.0.0.1:8011",
        "http://127.0.0.1:8080",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response
app.include_router(api_router)

frontend_path = Path(__file__).parent / "frontend" / "control-center"
if frontend_path.exists():
    app.mount("/admin", StaticFiles(directory=str(frontend_path), html=True), name="admin")

llm: Optional[LLMRunner] = None


class QueryRequest(BaseModel):
    question: str
    domain: Optional[str] = None
    max_context_tokens: int = 2000


class QueryResponse(BaseModel):
    answer: str
    domain: str
    model: str
    source_count: int


def _get_db():
    return get_db_manager()


def _find_best_domain(question: str) -> tuple[str, str]:
    db = _get_db()
    specialists = db.execute_query(
        "SELECT id, domain, model, root_qid FROM specialist_registry ORDER BY ema_score DESC",
        fetch=True,
    ) or []
    if not specialists:
        return "GeneralKnowledge", "qwen2.5:3b"
    domain_model = {s["domain"]: s["model"] for s in specialists}
    keyword_map = {
        "software": "SoftwareEngineering",
        "code": "SoftwareEngineering",
        "programming": "SoftwareEngineering",
        "python": "SoftwareEngineering",
        "function": "SoftwareEngineering",
        "math": "Mathematics",
        "algorithm": "Mathematics",
        "equation": "Mathematics",
        "medicine": "Medicine",
        "disease": "Medicine",
        "health": "Medicine",
        "clinical": "Medicine",
        "law": "LegalSystem",
        "legal": "LegalSystem",
        "court": "LegalSystem",
        "philosophy": "PhilosophyHistory",
        "history": "PhilosophyHistory",
        "economy": "FinanceEconomics",
        "finance": "FinanceEconomics",
        "inflation": "FinanceEconomics",
        "market": "FinanceEconomics",
        "physics": "Physics",
        "quantum": "Physics",
        "cyber": "Cybersecurity",
        "security": "Cybersecurity",
        "encryption": "Cybersecurity",
        "bio": "Bioinformatics",
        "genomics": "Bioinformatics",
        "dna": "Bioinformatics",
        "geopolitics": "Geopolitics",
        "political": "Geopolitics",
        "data": "DataScience",
        "machine learning": "DataScience",
        "neural": "DataScience",
        "chemistry": "Chemistry",
        "molecule": "Chemistry",
        "art": "ArtHistory",
        "painting": "ArtHistory",
        "electronics": "Electronics",
        "circuit": "Electronics",
        "astronomy": "Astronomy",
        "space": "Astronomy",
        "planet": "Astronomy",
    }
    q = question.lower()
    for kw, dom in keyword_map.items():
        if kw in q and dom in domain_model:
            return dom, domain_model[dom]
    fallback = specialists[0]
    return fallback["domain"], fallback["model"]


def _fetch_context(domain: str, question: str, max_chars: int = 2000) -> list[str]:
    db = _get_db()
    contexts = []

    # Try FTS5 keyword search first (table may not exist yet)
    keywords = [w for w in question.split() if len(w) > 3]
    if keywords:
        try:
            fts_query = " OR ".join(keywords[:5])
            rows = db.execute_query(
                """SELECT kp.structured_knowledge FROM knowledge_packages_fts fts
                   JOIN knowledge_packages kp ON kp.id = fts.rowid
                   JOIN specialist_registry sr ON sr.domain = kp.domain
                   WHERE knowledge_packages_fts MATCH ? AND sr.tier >= 1
                   LIMIT 5""",
                (fts_query,),
                fetch=True,
            ) or []
            for r in rows:
                text = (r.get("structured_knowledge") or "")[:800]
                if text:
                    contexts.append(text)
        except Exception:
            pass  # FTS5 table doesn't exist yet, fall through to recency

    # Fallback to recency if FTS returned nothing
    if not contexts:
        rows = db.execute_query(
            """SELECT kp.structured_knowledge FROM knowledge_packages kp
               JOIN specialist_registry sr ON sr.domain = kp.domain
               WHERE kp.domain = ? AND sr.tier >= 1
               ORDER BY kp.id DESC LIMIT 5""",
            (domain,),
            fetch=True,
        ) or []
        for r in rows:
            text = (r.get("structured_knowledge") or "")[:800]
            if text:
                contexts.append(text)

    # Final fallback: any domain, tier >= 1
    if not contexts:
        rows2 = db.execute_query(
            """SELECT kp.structured_knowledge FROM knowledge_packages kp
               JOIN specialist_registry sr ON sr.domain = kp.domain
               WHERE sr.tier >= 1
               ORDER BY kp.id DESC LIMIT 3""",
            fetch=True,
        )
        for r in rows2 or []:
            text = (r.get("structured_knowledge") or "")[:800]
            if text:
                contexts.append(text)
    return contexts


@app.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest):
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="question is required")

    domain, model = (
        (req.domain, _find_best_domain(req.question)[1])
        if req.domain
        else _find_best_domain(req.question)
    )
    logger.info(f"Query domain={domain} model={model} question={req.question[:80]}")

    contexts = _fetch_context(domain, req.question)
    ctx_block = "\n\n".join(contexts) if contexts else "No prior knowledge available."

    prompt = (
        f"You are an expert in {domain}. Answer the following question using "
        f"the provided context when relevant.\n\n"
        f"Context:\n{ctx_block}\n\n"
        f"Question: {req.question}\n\n"
        f"Answer concisely and cite sources if possible."
    )

    if llm is None:
        raise HTTPException(status_code=503, detail="LLM not initialized")
    try:
        answer = await llm.query_llm(model_name=model, prompt=prompt, max_tokens=1024)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM query failed: {e}")

    return QueryResponse(
        answer=answer or "No answer generated.",
        domain=domain,
        model=model,
        source_count=len(contexts),
    )


if __name__ == "__main__":
    import os
    if not os.getenv("EXPERTIA_API_KEY"):
        print("[WARN] No EXPERTIA_API_KEY set. Binding to 0.0.0.0 exposes the API to the network.")
        print("[WARN] Set EXPERTIA_API_KEY environment variable or bind to 127.0.0.1.")
    uvicorn.run(app, host="0.0.0.0", port=8011)
