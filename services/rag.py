from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

from flask import current_app

DIM = 1536
TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9\-\./]+", re.I)


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in TOKEN_RE.findall(text or "")]


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def hash_embed(text: str, dim: int = DIM) -> list[float]:
    vec = [0.0] * dim
    tokens = _tokenize(text)
    grams = tokens[:]
    grams += [f"{a}_{b}" for a, b in zip(tokens, tokens[1:])]
    grams += [f"{a}_{b}_{c}" for a, b, c in zip(tokens, tokens[1:], tokens[2:])]
    for tok in grams:
        digest = hashlib.md5(tok.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "little") % dim
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vec[idx] += sign
    return _l2_normalize(vec)


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))


class JsonVectorStore:
    def __init__(self, path: str):
        self.path = Path(path)
        self.items: dict[str, dict] = {}
        self.load()

    def load(self) -> None:
        if self.path.exists():
            try:
                self.items = json.loads(self.path.read_text())
            except json.JSONDecodeError:
                self.items = {}
        else:
            self.items = {}

    def persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.items))

    def upsert(self, vector_id: str, embedding: list[float], document: str, metadata: dict) -> None:
        self.items[vector_id] = {
            "embedding": embedding,
            "document": document,
            "metadata": metadata,
        }
        self.persist()

    def query(self, embedding: list[float], k: int = 5) -> list[dict]:
        scored = []
        for vid, item in self.items.items():
            score = cosine(embedding, item.get("embedding") or [])
            scored.append(
                {
                    "id": vid,
                    "score": score,
                    "document": item.get("document", ""),
                    "metadata": item.get("metadata") or {},
                }
            )
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:k]


class RAGEngine:
    def __init__(self) -> None:
        self.store: JsonVectorStore | None = None
        self.chroma = None
        self.openai_client = None

    def init_app(self, app) -> None:
        self.store = JsonVectorStore(app.config["VECTOR_STORE_PATH"])
        self._init_openai(app)
        self._init_chroma(app)

    def _init_openai(self, app) -> None:
        key = app.config.get("OPENAI_API_KEY")
        if not key:
            self.openai_client = None
            return
        try:
            from openai import OpenAI

            self.openai_client = OpenAI(api_key=key)
        except Exception:
            self.openai_client = None

    def _init_chroma(self, app) -> None:
        try:
            import chromadb

            client = chromadb.PersistentClient(path=app.config["CHROMA_PATH"])
            self.chroma = client.get_or_create_collection("forgemind_knowledge")
        except Exception:
            self.chroma = None

    def embed(self, text: str) -> list[float]:
        if self.openai_client:
            try:
                model = current_app.config.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
                resp = self.openai_client.embeddings.create(model=model, input=text)
                return _l2_normalize(list(resp.data[0].embedding))
            except Exception:
                pass
        return hash_embed(text, dim=DIM)

    def index_record(self, record) -> str:
        chunk = record.to_chunk()
        vector_id = record.id
        embedding = self.embed(chunk)
        record.embedding = embedding

        staff_str = record.staff_member if isinstance(record.staff_member, str) else getattr(record.staff_member, "name", "")
        asset_str = record.asset_code if hasattr(record, "asset_code") else (record.asset.asset_code if getattr(record, "asset", None) else "")
        desc_str = getattr(record, "asset_description", "") or (record.asset.asset_name if getattr(record, "asset", None) else "")

        metadata = {
            "code": record.code,
            "asset_code": asset_str,
            "asset_description": desc_str,
            "staff": staff_str,
            "category": getattr(record, "category", "Mechanical"),
            "record_id": record.id,
            "notes": getattr(record, "notes", "") or "",
        }
        if self.store:
            self.store.upsert(vector_id, embedding, chunk, metadata)
        if self.chroma is not None:
            try:
                self.chroma.upsert(
                    ids=[vector_id],
                    embeddings=[embedding],
                    documents=[chunk],
                    metadatas=[metadata],
                )
            except Exception:
                pass
        return vector_id

    def search(self, query: str, k: int = 5) -> list[dict]:
        embedding = self.embed(query)
        pool = max(k * 4, 12)
        results: list[dict] = []
        if self.chroma is not None:
            try:
                raw = self.chroma.query(query_embeddings=[embedding], n_results=min(pool, 20))
                ids = (raw.get("ids") or [[]])[0]
                docs = (raw.get("documents") or [[]])[0]
                metas = (raw.get("metadatas") or [[]])[0]
                dists = (raw.get("distances") or [[]])[0]
                for i, vid in enumerate(ids):
                    dist = dists[i] if i < len(dists) else 0
                    score = 1 / (1 + float(dist)) if dist is not None else 0
                    results.append(
                        {
                            "id": vid,
                            "score": score,
                            "document": docs[i] if i < len(docs) else "",
                            "metadata": metas[i] if i < len(metas) else {},
                        }
                    )
            except Exception:
                results = []
        if not results and self.store:
            results = self.store.query(embedding, k=pool)

        q = (query or "").lower()
        for item in results:
            meta = item.get("metadata") or {}
            doc = (item.get("document") or "").lower()
            bonus = 0.0
            asset = (meta.get("asset_code") or "").lower()
            code = (meta.get("code") or "").lower()
            staff = (meta.get("staff") or "").lower()

            if asset and asset in q:
                bonus += 0.50
            if code and code in q:
                bonus += 0.40
            for token in _tokenize(query):
                if len(token) > 2 and token in doc:
                    bonus += 0.05
            if staff and any(part in q for part in staff.split() if len(part) > 2):
                bonus += 0.20
            item["score"] = float(item.get("score") or 0) + bonus

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:k]

    def answer(self, query: str, k: int = 5) -> dict:
        hits = self.search(query, k=k)
        citations = []
        context_blocks = []
        for hit in hits:
            meta = hit.get("metadata") or {}
            relevance = int(max(0.0, min(1.0, float(hit.get("score") or 0))) * 100)
            doc = hit.get("document") or ""
            problem = ""
            if "Problem Description:" in doc:
                problem = doc.split("Problem Description:", 1)[-1].split("\n", 1)[0].strip()
            elif "Problem:" in doc:
                problem = doc.split("Problem:", 1)[-1].split("\n", 1)[0].strip()

            citations.append(
                {
                    "id": meta.get("record_id") or hit.get("id"),
                    "code": meta.get("code", ""),
                    "assetCode": meta.get("asset_code", ""),
                    "assetDescription": meta.get("asset_description", ""),
                    "staff": meta.get("staff", ""),
                    "summary": problem or doc[:180].strip(),
                    "notes": meta.get("notes", ""),
                    "relevance": min(relevance, 100),
                    "document": doc,
                }
            )
            context_blocks.append(hit.get("document") or "")

        context = "\n\n---\n\n".join(context_blocks) if context_blocks else "No matching plant records."
        text = self._generate(query, context, citations)
        public_citations = [{k: v for k, v in c.items() if k != "document"} for c in citations]
        return {"answer": text, "citations": public_citations, "engine": self._engine_name()}

    def _engine_name(self) -> str:
        if self.openai_client:
            return "OpenAI (gpt-4o-mini + text-embedding-3-small)"
        if current_app.config.get("GROQ_API_KEY"):
            return "Groq (llama-3.1-8b)"
        return "ForgeMind Local Semantic Engine (1536-dim)"

    def _generate(self, query: str, context: str, citations: list[dict]) -> str:
        system = (
            "You are ForgeMind AI, an industrial breakdown knowledge assistant. "
            "Always answer using the historical equipment breakdown solutions provided. "
            "Identify the exact technician name, asset codes, record code, actions performed, and technician notes. "
            "Be precise, clear, and professional."
        )
        user = f"Question: {query}\n\nHistorical Breakdown Records:\n{context}"

        if self.openai_client:
            try:
                model = current_app.config.get("OPENAI_MODEL", "gpt-4o-mini")
                resp = self.openai_client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    temperature=0.1,
                )
                return resp.choices[0].message.content.strip()
            except Exception:
                pass

        groq_key = current_app.config.get("GROQ_API_KEY")
        if groq_key:
            try:
                import requests

                resp = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                    json={
                        "model": current_app.config.get("GROQ_MODEL", "llama-3.1-8b-instant"),
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        "temperature": 0.1,
                    },
                    timeout=20,
                )
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"].strip()
            except Exception:
                pass

        return self._extractive_answer(query, citations)

    def _extractive_answer(self, query: str, citations: list[dict]) -> str:
        if not citations:
            return (
                "I could not find matching historical breakdown records for that query. "
                "You can log a new breakdown report in the Knowledge Repository to expand the vector index."
            )

        top = citations[0]
        doc = top.get("document") or ""

        fields = {}
        for line in doc.splitlines():
            if ":" in line:
                key, val = line.split(":", 1)
                fields[key.strip()] = val.strip()

        staff = top.get("staff") or fields.get("Staff Member") or "The assigned technician"
        asset_code = top.get("assetCode") or fields.get("Asset Code") or "the specified asset"
        asset_desc = top.get("assetDescription") or fields.get("Asset Description") or ""
        code = top.get("code") or fields.get("Record Code") or "Matched Record"
        work = fields.get("Work Performed", "")
        root = fields.get("Root Cause", "")
        corrective = fields.get("Corrective Action", "")
        notes = top.get("notes") or fields.get("Notes", "")
        status = fields.get("Status", "Approved")

        asset_label = f"{asset_code} ({asset_desc})" if asset_desc else asset_code

        response_lines = [
            f"**Technician:** {staff} resolved the issue on **{asset_label}** under record **[{code}]**.",
            f"\n**Corrective Action / Work Performed:**\n{work if work and work != 'None recorded' else 'Action details logged in system.'}",
        ]

        if root and root != "Not recorded":
            response_lines.append(f"\n**Root Cause:**\n{root}")

        if corrective and corrective != "Not recorded" and corrective != work:
            response_lines.append(f"\n**Preventative Action:**\n{corrective}")

        if notes and notes != "None":
            response_lines.append(f"\n**Technician Notes:**\n{notes}")

        response_lines.append(f"\n**Status:** {status}")

        if len(citations) > 1:
            response_lines.append(
                f"\n*Note: Found {len(citations)} relevant breakdown records in the knowledge base. See the citation cards below for full incident telemetry.*"
            )

        return "\n".join(response_lines)


rag_engine = RAGEngine()
