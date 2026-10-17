"""
RAG documental: protocolos, horarios, politicas y requisitos de la IPS (data/docs/*.md).

- Fragmenta los documentos por secciones (## titulo).
- Busqueda semantica con embeddings de Gemini si existe data/generated/embeddings.json
  (generado con `python data/build_embeddings.py`) y hay API key.
- Si no, usa BM25 lexico (sin dependencias), suficiente para un corpus pequeno.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from functools import lru_cache

from app.config import DATA_DIR, DOCS_DIR, settings
from app.data_store import normalizar

EMBEDDINGS_PATH = DATA_DIR / "embeddings.json"
EMBEDDING_DIM = 768

STOPWORDS = set("""
a al algo algun alguna algunas alguno algunos ante antes como con contra cual cuales cuando de del desde donde
durante e el ella ellas ellos en entre era es esa esas ese eso esos esta estan estas este esto estos fue ha hay
la las le les lo los mas me mi mis mucho muy nada ni no nos o os otra otro para pero poco por porque que quien se
sea ser si sin sobre son su sus tambien te tiene tienen todo todos tu un una uno unos y ya debe deben puede pueden
cual cuanto cuanta necesita necesito hacer paciente pacientes usuario usuarios
""".split())


def tokenizar(texto: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", normalizar(texto)) if t not in STOPWORDS and len(t) > 1]


@lru_cache(maxsize=1)
def cargar_fragmentos() -> list[dict]:
    fragmentos = []
    for ruta in sorted(DOCS_DIR.glob("*.md")):
        texto = ruta.read_text(encoding="utf-8")
        titulo_doc = next((l[2:].strip() for l in texto.splitlines() if l.startswith("# ")), ruta.stem)
        secciones = re.split(r"\n(?=## )", texto)
        for i, sec in enumerate(secciones):
            sec = sec.strip()
            if not sec or (i == 0 and len(secciones) > 1 and len(sec.splitlines()) <= 2):
                continue
            titulo_sec = sec.splitlines()[0].lstrip("# ").strip()
            fragmentos.append({
                "id": f"{ruta.stem}#{i}",
                "documento": titulo_doc,
                "archivo": ruta.name,
                "seccion": titulo_sec,
                "texto": sec,
            })
    return fragmentos


class _BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.4, b: float = 0.75) -> None:
        self.docs, self.k1, self.b = docs, k1, b
        self.avgdl = sum(map(len, docs)) / max(1, len(docs))
        df = Counter(t for d in docs for t in set(d))
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.tf = [Counter(d) for d in docs]

    def puntajes(self, consulta: list[str]) -> list[float]:
        res = []
        for d, tf in zip(self.docs, self.tf):
            s = 0.0
            for t in consulta:
                if t in tf:
                    f = tf[t]
                    s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * len(d) / self.avgdl))
            res.append(s)
        return res


@lru_cache(maxsize=1)
def _indice_bm25() -> _BM25:
    return _BM25([tokenizar(f["documento"] + " " + f["texto"]) for f in cargar_fragmentos()])


@lru_cache(maxsize=1)
def _embeddings() -> dict[str, list[float]] | None:
    if not EMBEDDINGS_PATH.exists():
        return None
    data = json.loads(EMBEDDINGS_PATH.read_text(encoding="utf-8"))
    return data.get("vectores")


def _coseno(a: list[float], b: list[float]) -> float:
    num = sum(x * y for x, y in zip(a, b))
    den = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return num / den if den else 0.0


async def _embed_consulta(texto: str) -> list[float]:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.gemini_api_key)
    resp = await client.aio.models.embed_content(
        model=settings.embedding_model, contents=texto,
        config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY", output_dimensionality=EMBEDDING_DIM),
    )
    return list(resp.embeddings[0].values)


def buscar_lexico(pregunta: str, k: int = 4) -> list[dict]:
    frags = cargar_fragmentos()
    puntajes = _indice_bm25().puntajes(tokenizar(pregunta))
    orden = sorted(range(len(frags)), key=lambda i: puntajes[i], reverse=True)
    return [{**frags[i], "puntaje": round(puntajes[i], 3)} for i in orden[:k] if puntajes[i] > 0]


async def buscar(pregunta: str, k: int = 4) -> dict:
    """Devuelve los k fragmentos mas relevantes y el metodo usado."""
    vectores = _embeddings()
    if vectores and settings.llm_configurado:
        try:
            q = await _embed_consulta(pregunta)
            frags = cargar_fragmentos()
            puntuados = sorted(((f, _coseno(q, vectores[f["id"]])) for f in frags if f["id"] in vectores),
                               key=lambda x: x[1], reverse=True)[:k]
            return {"metodo": "semantico (embeddings Gemini)",
                    "fragmentos": [{**f, "puntaje": round(s, 3)} for f, s in puntuados]}
        except Exception as exc:  # noqa: BLE001 - si falla el embedding, caemos al lexico
            return {"metodo": f"lexico BM25 (fallback: {type(exc).__name__})", "fragmentos": buscar_lexico(pregunta, k)}
    return {"metodo": "lexico BM25", "fragmentos": buscar_lexico(pregunta, k)}
