import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


def is_postgres_session(db: AsyncSession) -> bool:
    """Return True when the active AsyncSession is backed by PostgreSQL."""
    bind = db.get_bind()
    return bind is not None and bind.dialect.name == "postgresql"


def format_pgvector_literal(vec: list[float]) -> str:
    """Format a float embedding into a pgvector literal string '[v1,v2,...]'."""
    return "[" + ",".join(f"{float(v):.6f}" for v in vec) + "]"


async def sync_clause_pgvector(
    db: AsyncSession,
    *,
    clause_id: str,
    embedding: list[float],
) -> None:
    """Persist native pgvector column when running on PostgreSQL with pgvector enabled."""
    if not embedding or not is_postgres_session(db):
        return
    literal = format_pgvector_literal(embedding)
    try:
        async with db.begin_nested():
            await db.execute(
                text(
                    "UPDATE policy_clauses SET embedding_vec = CAST(:vec AS vector) "
                    "WHERE id = :cid"
                ),
                {"vec": literal, "cid": clause_id},
            )
    except Exception as exc:
        logger.warning("pgvector_sync_skipped", clause_id=clause_id, error=str(exc))


async def query_clauses_pgvector(
    db: AsyncSession,
    *,
    query_vec: list[float],
    policy_id: str | None,
    clause_type: str | None,
    limit: int,
) -> list[tuple[str, float]] | None:
    """Run native cosine-distance search via pgvector HNSW when on PostgreSQL."""
    if not query_vec or not is_postgres_session(db):
        return None

    filters = ["embedding_vec IS NOT NULL"]
    params: dict[str, object] = {
        "qvec": format_pgvector_literal(query_vec),
        "lim": max(limit * 3, 25),
    }
    if policy_id:
        filters.append("policy_id = :pid")
        params["pid"] = policy_id
    if clause_type:
        filters.append("clause_type = :ctype")
        params["ctype"] = clause_type.strip().lower()

    where_sql = " AND ".join(filters)
    sql = text(
        f"SELECT id, 1.0 - (embedding_vec <=> CAST(:qvec AS vector)) AS cosine_sim "
        f"FROM policy_clauses WHERE {where_sql} "
        f"ORDER BY embedding_vec <=> CAST(:qvec AS vector) ASC LIMIT :lim"
    )
    try:
        rows = (await db.execute(sql, params)).all()
        return [(str(row[0]), float(row[1])) for row in rows]
    except Exception as exc:
        logger.warning("pgvector_query_fallback_to_python", error=str(exc))
        return None
