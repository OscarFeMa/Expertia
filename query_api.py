import logging
import sys
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent))
from config.log_setup import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

from database.db_manager import get_db_manager
from llm_manager import LLMRunner

app = FastAPI(title="Expertia Query API", version="0.1.0")
llm = LLMRunner()


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
    rows = db.execute_query(
        """SELECT structured_knowledge FROM knowledge_packages
           WHERE domain = ? ORDER BY id DESC LIMIT 5""",
        (domain,),
        fetch=True,
    ) or []
    contexts = []
    total = 0
    for r in rows:
        text = (r.get("structured_knowledge") or "")[:800]
        if not text:
            continue
        if total + len(text) > max_chars:
            break
        contexts.append(text)
        total += len(text)
    if not contexts:
        rows2 = db.execute_query(
            "SELECT structured_knowledge FROM knowledge_packages ORDER BY id DESC LIMIT 3",
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
    uvicorn.run(app, host="0.0.0.0", port=8011)
