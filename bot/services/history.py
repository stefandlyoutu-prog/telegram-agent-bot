import aiosqlite

from bot.config import DB_PATH, MAX_HISTORY_TURNS
from bot.services.print_profile import empty_profile, profile_from_json, profile_to_json


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER PRIMARY KEY,
                model TEXT NOT NULL,
                print_profile TEXT,
                auto_proceed INTEGER,
                voice_reply INTEGER
            )
            """
        )
        for col, typedef in (
            ("print_profile", "TEXT"),
            ("auto_proceed", "INTEGER"),
            ("voice_reply", "INTEGER"),
            ("tts_voice", "TEXT"),
        ):
            try:
                await db.execute(
                    f"ALTER TABLE user_settings ADD COLUMN {col} {typedef}"
                )
            except Exception:
                pass
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS user_projects (
                user_id INTEGER PRIMARY KEY,
                project_name TEXT,
                context TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_user ON messages(user_id)"
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS pending_concepts (
                user_id INTEGER PRIMARY KEY,
                image_bytes BLOB NOT NULL,
                mime TEXT NOT NULL,
                prompt TEXT NOT NULL,
                original_text TEXT NOT NULL,
                subject TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await db.commit()


async def get_model(user_id: int, default: str) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT model FROM user_settings WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else default


async def get_print_profile(user_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT print_profile FROM user_settings WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row and row[0]:
                return profile_from_json(row[0])
    return empty_profile()


async def set_print_profile(user_id: int, profile: dict) -> None:
    model = await get_model(user_id, "gpt-5.4-mini")
    raw = profile_to_json(profile)
    auto = await get_user_pref(user_id, "auto_proceed")
    voice = await get_user_pref(user_id, "voice_reply")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO user_settings (user_id, model, print_profile, auto_proceed, voice_reply)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET print_profile = excluded.print_profile
            """,
            (user_id, model, raw, auto, voice),
        )
        await db.commit()


async def save_project_context(user_id: int, name: str, context: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO user_projects (user_id, project_name, context, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                project_name = excluded.project_name,
                context = excluded.context,
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, name[:80], context[:12000]),
        )
        await db.commit()


async def get_project_context(user_id: int) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT context FROM user_projects WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row and row[0] else ""


async def get_project_name(user_id: int) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT project_name FROM user_projects WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row and row[0] else ""


async def get_user_pref(user_id: int, key: str):
    col = key if key in ("auto_proceed", "voice_reply", "tts_voice") else None
    if not col:
        return None
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            f"SELECT {col} FROM user_settings WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return row[0]
    return None


async def set_user_pref(user_id: int, key: str, value) -> None:
    from bot.config import DEFAULT_MODEL

    col = key if key in ("auto_proceed", "voice_reply", "tts_voice") else None
    if not col:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            f"UPDATE user_settings SET {col} = ? WHERE user_id = ?",
            (value, user_id),
        )
        if cur.rowcount == 0:
            await db.execute(
                """
                INSERT INTO user_settings
                    (user_id, model, print_profile, auto_proceed, voice_reply, tts_voice)
                VALUES (?, ?, NULL, 1, 1, NULL)
                """,
                (user_id, DEFAULT_MODEL),
            )
            await db.execute(
                f"UPDATE user_settings SET {col} = ? WHERE user_id = ?",
                (value, user_id),
            )
        await db.commit()


async def ensure_user_bootstrapped(user_id: int) -> None:
    """Первый контакт: включить автопилот по умолчанию."""
    from bot.config import DEFAULT_AUTO_PROCEED
    from bot.services.print_profile import ensure_profile

    if not DEFAULT_AUTO_PROCEED:
        return
    existing = await get_user_pref(user_id, "auto_proceed")
    if existing is None:
        await set_user_pref(user_id, "auto_proceed", 1)
        prof = ensure_profile({})
        await set_print_profile(user_id, prof)


async def set_model(user_id: int, model: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO user_settings (user_id, model, print_profile) VALUES (?, ?, NULL)
            ON CONFLICT(user_id) DO UPDATE SET model = excluded.model
            """,
            (user_id, model),
        )
        await db.commit()


async def get_history(user_id: int) -> list[dict[str, str]]:
    limit = MAX_HISTORY_TURNS * 2
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT role, content FROM messages
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()
    rows.reverse()
    return [{"role": role, "content": content} for role, content in rows]


async def add_message(user_id: int, role: str, content: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO messages (user_id, role, content) VALUES (?, ?, ?)",
            (user_id, role, content),
        )
        await db.commit()
        # Обрезка старых сообщений
        await db.execute(
            """
            DELETE FROM messages
            WHERE user_id = ? AND id NOT IN (
                SELECT id FROM messages
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT ?
            )
            """,
            (user_id, user_id, MAX_HISTORY_TURNS * 2),
        )
        await db.commit()


async def clear_history(user_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM user_projects WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM pending_concepts WHERE user_id = ?", (user_id,))
        await db.commit()


async def clear_all_user_context(user_id: int, *, keep_settings: bool = True) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM user_projects WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM pending_concepts WHERE user_id = ?", (user_id,))
        if keep_settings:
            await db.execute(
                "UPDATE user_settings SET print_profile = NULL WHERE user_id = ?",
                (user_id,),
            )
        else:
            await db.execute("DELETE FROM user_settings WHERE user_id = ?", (user_id,))
        await db.commit()


async def save_pending_concept(
    user_id: int,
    *,
    image_bytes: bytes,
    mime: str,
    prompt: str,
    original_text: str,
    subject: str = "",
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO pending_concepts
                (user_id, image_bytes, mime, prompt, original_text, subject, created_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                image_bytes = excluded.image_bytes,
                mime = excluded.mime,
                prompt = excluded.prompt,
                original_text = excluded.original_text,
                subject = excluded.subject,
                created_at = CURRENT_TIMESTAMP
            """,
            (user_id, image_bytes, mime, prompt[:2000], original_text[:2000], subject[:120]),
        )
        await db.commit()


async def get_pending_concept(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT image_bytes, mime, prompt, original_text, subject
            FROM pending_concepts
            WHERE user_id = ?
            """,
            (user_id,),
        ) as cursor:
            row = await cursor.fetchone()
    if not row:
        return None
    return {
        "image_bytes": row[0],
        "mime": row[1],
        "prompt": row[2],
        "original_text": row[3],
        "subject": row[4] or "",
    }


async def clear_pending_concept(user_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM pending_concepts WHERE user_id = ?", (user_id,))
        await db.commit()
