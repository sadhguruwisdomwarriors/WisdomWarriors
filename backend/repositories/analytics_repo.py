from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.post_snapshot import PostSnapshot
from backend.models.scrape_profile import ScrapeProfile
from backend.services.embedding.client import embed_texts


WISDOM_WARRIOR_ALLOWED_MENTIONS = [
    "ishafoundation",
    "adiyogi.official",
    "sadhguru",
    "sadhgurutamil",
    "sadhgurutelugu",
    "sadhguru.hindiofficial",
    "sadhguru.malayalam",
    "sadhguru_marathi_official",
    "sadhgurubangla",
    "sadhguru_kannada_official",
]

WISDOM_WARRIOR_ALLOWED_TAGGED_USERS = [
    "ishafoundation",
    "adiyogi.official",
    "sadhguru",
    "sadhgurutamil",
    "sadhgurutelugu",
    "sadhguru.hindiofficial",
    "sadhguru.malayalam",
    "sadhguru_marathi_official",
    "sadhgurubangla",
    "sadhguru_kannada_official",
]

WISDOM_WARRIOR_ALLOWED_HASHTAGS = [
    # Core & Foundation
    "Sadhguru",
    "Sadhgurujaggivasudev",
    "Jaggi",
    "Isha",
    "Ishafoundation",
    "Ishayoga",
    "Ishayogacenter",
    "Soundsofisha",
    "Ishalife",
    "Ishaashram",
    "Ishaevents",
    "Ishavolunteers",
    # Programs & Initiatives
    "Innerengineering",
    "Innerengineeringonline",
    "Iecompletion",
    "Bhavaspandana",
    "Shoonyameditation",
    "Shoonya",
    "Samyama",
    "Sadhanapada",
    "Cauverycalling",
    "Savesoil",
    "Consciousplanet",
    "Consciousliving",
    "Consciousness",
    "Conscious",
    "Miracleofmind",
    # Consecrated & Deities
    "Adiyogi",
    "Adiyogishiva",
    "Dhyanalinga",
    "Lingabhairavi",
    "Bhairavi",
    "Devi",
    "Shiva",
    "Mahadev",
    "Sacredspaces",
    # Practices & Wisdom
    "Yoga",
    "Hathayoga",
    "Kriyayoga",
    "Pranayama",
    "Meditation",
    "Meditationpractice",
    "Guidedmeditation",
    "Yogapractice",
    "Spiritualpractice",
    "Dailysadhana",
    "Sadhana",
    "Energybody",
    "Spirituality",
    "Sadhguruquotes",
    "Sadhguruwisdom",
    "Sanatandharma",
    # States of Being & Qualities
    "Innerpeace",
    "Bliss",
    "Joyfulliving",
    "Mindfulness",
    "Selfawareness",
    "Awakening",
    "Enlightenment",
    "Transformation",
    "Stillness",
    "Silence",
    "Devotion",
    "Gratitude",
    "Divineenergy",
    "Presence",
    "Awareness",
    "Culture",
    "Feminine",
    # Multilingual
    "ஈஷா",
]

WISDOM_WARRIOR_ALLOWED_CAPTION_KEYWORDS = [
    # Foundation & Core
    "Isha",
    "Ishafoundation",
    "Isha Foundation",
    "Ishayoga",
    "Isha Yoga",
    "Ishayogacenter",
    "Isha Yoga Center",
    "Sounds of Isha",
    "Soundsofisha",
    "Isha Volunteers",
    "Isha Life",
    "Isha Ashram",
    "Isha Events",
    "Sacred Spaces",
    # Sadhguru & Quotes
    "Sadhguru",
    "Sadhgurujaggivasudev",
    "Sadhguru Jaggi Vasudev",
    "Jaggi",
    "Sadhguru Quotes",
    "Sadhguruquotes",
    "Sadhguru Wisdom",
    "Sadhguruwisdom",
    # Programs & Modules
    "Inner Engineering",
    "Innerengineering",
    "Inner Engineering Online",
    "IE Completion",
    "Bhava Spandana",
    "Bhavaspandana",
    "Shoonya Meditation",
    "Shoonyameditation",
    "Shoonya",
    "Samyama",
    "Sadhanapada",
    # Movements & Environment
    "Cauvery Calling",
    "Cauverycalling",
    "Save Soil",
    "Savesoil",
    "Conscious Planet",
    "Consciousplanet",
    "Conscious Living",
    "Consciousliving",
    "Consciousness",
    "Conscious",
    "Miracle of Mind",
    "Miracleofmind",
    # Consecrated & Deities
    "Adiyogi",
    "Adiyogi Shiva",
    "Adiyogishiva",
    "Dhyanalinga",
    "Linga Bhairavi",
    "Lingabhairavi",
    "Bhairavi",
    "Devi",
    "Shiva",
    "Mahadev",
    "Divine Energy",
    "Sanatan Dharma",
    # Practices & Yoga
    "Yoga",
    "Hatha Yoga",
    "Hathayoga",
    "Kriya Yoga",
    "Kriyayoga",
    "Pranayama",
    "Meditation",
    "Meditation Practice",
    "Guided Meditation",
    "Yoga Practice",
    "Spiritual Practice",
    "Daily Sadhana",
    "Sadhana",
    "Energy Body",
    "Spirituality",
    # States of Being & Mind
    "Inner Peace",
    "Bliss",
    "Joyful Living",
    "Mindfulness",
    "Self Awareness",
    "Awakening",
    "Enlightenment",
    "Transformation",
    "Stillness",
    "Silence",
    "Devotion",
    "Gratitude",
    "Presence",
    "Awareness",
    "Culture",
    "Feminine",
    # Regional Languages
    "ஈஷா",
    "ईशा",
    "ఇషా",
    "ഇഷ",
    "ಇಶಾ",
    "சத்குரு",
    "సద్గురు",
    "ಸದ್ಗುರು",
    "സദ്‍ഗുരു",
    "सद्गुरु",
]


def _normalize_hashtag(value: str) -> str:
    return "".join((value or "").strip().lstrip("#").casefold().split())


def _normalize_mention(value: str) -> str:
    return (value or "").strip().lstrip("@").casefold()


def _extract_coauthor_usernames(values: list[object] | None) -> list[str]:
    usernames: list[str] = []
    for value in values or []:
        candidate: str | None = None
        if isinstance(value, str):
            candidate = value
        elif isinstance(value, dict):
            for key in ("username", "userName", "ownerUsername", "handle"):
                raw_value = value.get(key)
                if isinstance(raw_value, str) and raw_value.strip():
                    candidate = raw_value
                    break
        if candidate:
            normalized = _normalize_mention(candidate)
            if normalized and normalized not in usernames:
                usernames.append(normalized)
    return usernames


ALLOWED_HASHTAG_MAP = {
    _normalize_hashtag(value): value for value in WISDOM_WARRIOR_ALLOWED_HASHTAGS
}
ALLOWED_MENTION_MAP = {
    _normalize_mention(value): value for value in WISDOM_WARRIOR_ALLOWED_MENTIONS
}
ALLOWED_CAPTION_KEYWORDS = [value.casefold() for value in WISDOM_WARRIOR_ALLOWED_CAPTION_KEYWORDS]


def _vector_literal(values: list[float]) -> str:
    return f"[{','.join(str(value) for value in values)}]"


async def get_overview(db: AsyncSession, period_label: str | None = None) -> dict:
    period_expr = ":period_label" if period_label else "(SELECT MAX(period_label) FROM account_monthly_summary)"
    hashtag_period_expr = ":period_label" if period_label else "(SELECT MAX(period_label) FROM hashtag_performance)"
    latest_period_expr = ":period_label" if period_label else "(SELECT MAX(period_label) FROM account_monthly_summary)"
    result = await db.execute(text("""
        SELECT
            (SELECT COUNT(*) FROM profiles) AS total_profiles,
            (
                SELECT COUNT(*)
                FROM (
                    SELECT DISTINCT ON (url) id
                    FROM post_snapshots
                    ORDER BY url, scraped_at DESC NULLS LAST, id DESC
                ) latest_posts
            ) AS total_posts,
            (SELECT COALESCE(AVG(followers_count), 0) FROM profiles) AS avg_followers,
            (SELECT username FROM profiles ORDER BY followers_count DESC LIMIT 1) AS top_profile,
            {latest_period_expr} AS latest_period,
            (
                SELECT COUNT(*)
                FROM account_monthly_summary
                WHERE period_label = {period_expr}
            ) AS active_accounts,
            (
                SELECT COALESCE(ROUND(AVG(avg_engagement_rate), 2), 0)
                FROM account_monthly_summary
                WHERE period_label = {period_expr}
            ) AS avg_engagement_rate,
            (
                SELECT tag
                FROM hashtag_performance
                WHERE period_label = {hashtag_period_expr}
                ORDER BY avg_engagement_rate DESC NULLS LAST, post_count DESC, total_likes DESC
                LIMIT 1
            ) AS top_hashtag
    """.format(period_expr=period_expr, hashtag_period_expr=hashtag_period_expr, latest_period_expr=latest_period_expr)), ({"period_label": period_label} if period_label else {}))
    row = result.mappings().first()
    return dict(row) if row else {}


async def get_follower_growth(
    db: AsyncSession,
    username: str | None = None,
    up_to_period_label: str | None = None,
) -> list[dict]:
    params: dict[str, str] = {}
    period_clause = ""
    if up_to_period_label:
        period_clause = " AND period_label <= :up_to_period_label"
        params["up_to_period_label"] = up_to_period_label

    if username:
        params["username"] = username
        result = await db.execute(text("""
            SELECT period_label, followers_count, username, follower_delta, follower_delta_pct, scraped_at
            FROM profile_follower_growth
            WHERE username = :username {period_clause}
            ORDER BY scraped_at
        """.format(period_clause=period_clause)), params)
    else:
        result = await db.execute(text("""
            SELECT
                period_label,
                SUM(followers_count) AS followers_count,
                'all' AS username,
                SUM(COALESCE(follower_delta, 0)) AS follower_delta,
                NULL::numeric AS follower_delta_pct,
                MAX(scraped_at) AS scraped_at
            FROM profile_follower_growth
            WHERE 1 = 1 {period_clause}
            GROUP BY period_label
            ORDER BY MAX(scraped_at)
        """.format(period_clause=period_clause)), params)
    return [dict(r) for r in result.mappings().all()]


async def get_top_profiles(db: AsyncSession, metric: str = "followers_count", limit: int = 10) -> list[dict]:
    allowed = {"followers_count", "follows_count", "posts_count"}
    col = metric if metric in allowed else "followers_count"
    result = await db.execute(
        text(f"SELECT username, {col} AS value FROM profiles ORDER BY {col} DESC LIMIT :limit"),
        {"limit": limit},
    )
    return [dict(r) for r in result.mappings().all()]


async def get_hashtag_frequency(db: AsyncSession, limit: int = 20) -> list[dict]:
    result = await db.execute(text("""
        SELECT tag, SUM(post_count) AS count
        FROM hashtag_performance
        GROUP BY tag
        ORDER BY count DESC, tag ASC
        LIMIT :limit
    """), {"limit": limit})
    return [dict(r) for r in result.mappings().all()]


async def get_engagement_by_profile(db: AsyncSession) -> list[dict]:
    result = await db.execute(text("""
     SELECT owner_username,
         ROUND(AVG(avg_likes), 0)::int AS avg_likes,
         ROUND(AVG(avg_video_views), 0)::int AS avg_plays,
         SUM(posts_count)::int AS post_count
     FROM account_monthly_summary
     GROUP BY owner_username
     ORDER BY avg_likes DESC NULLS LAST
        LIMIT 20
    """))
    return [dict(r) for r in result.mappings().all()]


async def get_post_volume(db: AsyncSession, up_to_period_label: str | None = None) -> list[dict]:
    params: dict[str, str] = {}
    period_clause = ""
    if up_to_period_label:
        period_clause = " WHERE period_label <= :up_to_period_label"
        params["up_to_period_label"] = up_to_period_label

    result = await db.execute(text("""
        SELECT period_label, SUM(posts_count) AS post_count
        FROM account_monthly_summary
        {period_clause}
        GROUP BY period_label
        ORDER BY period_label
    """.format(period_clause=period_clause)), params)
    return [dict(r) for r in result.mappings().all()]


async def get_account_monthly_summary(
    db: AsyncSession,
    period_label: str | None = None,
    limit: int = 12,
) -> list[dict]:
    query = """
        SELECT
            owner_username,
            period_label,
            grade,
            category,
            posts_count,
            avg_likes,
            avg_comments,
            avg_video_views,
            total_likes,
            total_comments,
            peak_likes,
            peak_comments,
            avg_engagement_rate,
            peak_engagement_rate,
            image_count,
            video_count,
            carousel_count,
            trim(most_active_day) AS most_active_day
        FROM account_monthly_summary
    """
    params: dict[str, str | int] = {"limit": limit}
    if period_label:
        query += " WHERE period_label = :period_label"
        params["period_label"] = period_label
    else:
        query += " WHERE period_label = (SELECT MAX(period_label) FROM account_monthly_summary)"
    query += " ORDER BY avg_engagement_rate DESC NULLS LAST, total_likes DESC, owner_username ASC LIMIT :limit"
    result = await db.execute(text(query), params)
    return [dict(r) for r in result.mappings().all()]


async def get_grade_benchmarks(db: AsyncSession, period_label: str | None = None) -> list[dict]:
    query = """
        SELECT
            grade,
            category,
            account_count,
            avg_engagement_rate,
            avg_likes,
            avg_comments,
            avg_followers,
            period_label
        FROM grade_benchmarks
    """
    params: dict[str, str] = {}
    if period_label:
        query += " WHERE period_label = :period_label"
        params["period_label"] = period_label
    else:
        query += " WHERE period_label = (SELECT MAX(period_label) FROM grade_benchmarks)"
    query += " ORDER BY avg_engagement_rate DESC NULLS LAST, avg_followers DESC NULLS LAST, grade ASC"
    result = await db.execute(text(query), params)
    return [dict(r) for r in result.mappings().all()]


async def get_hashtag_performance(
    db: AsyncSession,
    period_label: str | None = None,
    username: str | None = None,
    limit: int = 15,
) -> list[dict]:
    query = """
        SELECT
            tag,
            owner_username,
            period_label,
            grade,
            category,
            post_count,
            avg_likes,
            avg_comments,
            avg_engagement_rate,
            total_likes,
            peak_engagement_rate
        FROM hashtag_performance
        WHERE 1 = 1
    """
    params: dict[str, str | int] = {"limit": limit}
    if period_label:
        query += " AND period_label = :period_label"
        params["period_label"] = period_label
    else:
        query += " AND period_label = (SELECT MAX(period_label) FROM hashtag_performance)"
    if username:
        query += " AND owner_username = :username"
        params["username"] = username
    query += " ORDER BY avg_engagement_rate DESC NULLS LAST, post_count DESC, total_likes DESC, tag ASC LIMIT :limit"
    result = await db.execute(text(query), params)
    return [dict(r) for r in result.mappings().all()]


async def get_posting_time_heatmap(
    db: AsyncSession,
    username: str | None = None,
    period_label: str | None = None,
) -> list[dict]:
    query = """
        SELECT
            MIN(to_char(pe.timestamp, 'Dy')) AS day_name,
            extract(dow from pe.timestamp)::int AS day_of_week,
            extract(hour from pe.timestamp)::int AS hour_of_day,
            COUNT(*)::int AS post_count,
            ROUND(AVG(pe.likes_count), 0)::int AS avg_likes,
            ROUND(AVG(pe.comments_count), 0)::int AS avg_comments,
            ROUND(AVG(pe.engagement_rate), 2) AS avg_engagement_rate
        FROM post_engagement pe
        WHERE pe.timestamp IS NOT NULL
    """
    params: dict[str, str] = {}
    if username:
        query += " AND pe.owner_username = :username"
        params["username"] = username
    if period_label:
        query += " AND pe.period_label = :period_label"
        params["period_label"] = period_label
    query += " GROUP BY day_of_week, hour_of_day ORDER BY day_of_week, hour_of_day"
    result = await db.execute(text(query), params)
    return [dict(r) for r in result.mappings().all()]


async def get_scrape_run_summary(db: AsyncSession, limit: int = 10, max_run_id: int | None = None) -> list[dict]:
    query = """
        SELECT
            id,
            scraper_type,
            trigger,
            started_at,
            finished_at,
            status,
            embedding_status,
            items_fetched,
            profiles_requested,
            error_message,
            embedding_error_message,
            schedule_name,
            schedule_frequency,
            duration_seconds,
            apify_posts_run_id,
            apify_posts_dataset_id,
            apify_posts_status,
            apify_profiles_run_id,
            apify_profiles_dataset_id,
            apify_profiles_status
        FROM scrape_run_summary
    """
    params: dict[str, int] = {"limit": limit}
    if max_run_id is not None:
        query += " WHERE id <= :max_run_id"
        params["max_run_id"] = max_run_id
    query += " ORDER BY id DESC LIMIT :limit"
    result = await db.execute(text(query), params)
    return [dict(r) for r in result.mappings().all()]


async def get_post_engagement_history(db: AsyncSession, short_code: str) -> list[dict]:
    result = await db.execute(text("""
        SELECT
            post_id,
            short_code,
            owner_username,
            period_label,
            scraped_at,
            likes_count,
            type,
            display_storage_url,
            caption,
            hashtags,
            run_id,
            followers_count,
            likes_rate
        FROM post_engagement_history
        WHERE short_code = :short_code
        ORDER BY scraped_at
    """), {"short_code": short_code})
    return [dict(r) for r in result.mappings().all()]


async def search_similar_posts(
    db: AsyncSession,
    query: str,
    username: str | None = None,
    limit: int = 10,
) -> list[dict]:
    query_embedding = (await embed_texts([query]))[0]
    vector_text = _vector_literal(query_embedding)
    result = await db.execute(text("""
        SELECT *
        FROM search_similar_posts(
            CAST(:query_embedding AS vector(1536)),
            :filter_username,
            :result_limit
        )
    """), {
        "query_embedding": vector_text,
        "filter_username": username,
        "result_limit": limit,
    })
    return [dict(r) for r in result.mappings().all()]


async def get_wisdom_warriors_monthly_views(db: AsyncSession, month: str) -> list[dict]:
    return await get_wisdom_warriors_monthly_views_filtered(
        db=db,
        month=month,
        apply_filters=True,
        hashtags=WISDOM_WARRIOR_ALLOWED_HASHTAGS,
        mentions=WISDOM_WARRIOR_ALLOWED_MENTIONS,
        tagged_users=WISDOM_WARRIOR_ALLOWED_TAGGED_USERS,
        caption_keywords=WISDOM_WARRIOR_ALLOWED_CAPTION_KEYWORDS,
        category=None,
    )


async def list_wisdom_warriors_snapshot_runs(db: AsyncSession, limit: int = 100) -> list[dict]:
    result = await db.execute(
        text(
            """
            SELECT
                ps.run_id,
                MAX(ps.scraped_at) AS scraped_at
            FROM post_snapshots ps
            WHERE ps.run_id IS NOT NULL
            GROUP BY ps.run_id
            ORDER BY MAX(ps.scraped_at) DESC
            LIMIT :limit
            """
        ),
        {"limit": limit},
    )
    return [dict(r) for r in result.mappings().all()]


async def get_wisdom_warriors_monthly_views_filtered(
    db: AsyncSession,
    month: str,
    apply_filters: bool,
    hashtags: list[str] | None,
    mentions: list[str] | None,
    tagged_users: list[str] | None,
    caption_keywords: list[str] | None,
    category: str | None,
    snapshot_run_id: int | None = None,
) -> list[dict]:
    all_profiles_result = await db.execute(
        select(ScrapeProfile.username).where(ScrapeProfile.username.is_not(None))
    )
    tracked_usernames = {
        _normalize_mention(username)
        for username in all_profiles_result.scalars().all()
        if isinstance(username, str) and username.strip()
    }

    profile_query = select(ScrapeProfile)
    if category:
        profile_query = profile_query.where(ScrapeProfile.category == category)
    profile_query = profile_query.order_by(ScrapeProfile.position, ScrapeProfile.id)

    profile_result = await db.execute(profile_query)
    profiles = profile_result.scalars().all()
    if not profiles:
        return []

    usernames = {
        _normalize_mention(profile.username)
        for profile in profiles
        if profile.username and profile.username.strip()
    }

    resolved_snapshot_run_id = snapshot_run_id
    if resolved_snapshot_run_id is None:
        latest_snapshot_run = await db.execute(
            select(PostSnapshot.run_id)
            .where(PostSnapshot.run_id.is_not(None))
            .order_by(PostSnapshot.scraped_at.desc().nullslast(), PostSnapshot.run_id.desc())
            .limit(1)
        )
        resolved_snapshot_run_id = latest_snapshot_run.scalar_one_or_none()

    if resolved_snapshot_run_id is None:
        return [
            {
                "username": profile.username,
                "month": month,
                "total_views": 0.0,
                "matched_hashtags": [],
                "matched_mentions": [],
                "matched_tagged_users": [],
            }
            for profile in profiles
        ]

    post_query = (
        select(PostSnapshot)
        .where(PostSnapshot.timestamp.is_not(None))
        .where(func.to_char(PostSnapshot.timestamp, "YYYY-MM") == month)
        .where(PostSnapshot.run_id == resolved_snapshot_run_id)
    )
    post_result = await db.execute(post_query)
    posts = post_result.scalars().all()

    active_hashtags = hashtags if hashtags else WISDOM_WARRIOR_ALLOWED_HASHTAGS
    active_mentions = mentions if mentions else WISDOM_WARRIOR_ALLOWED_MENTIONS
    active_tagged_users = tagged_users if tagged_users else WISDOM_WARRIOR_ALLOWED_TAGGED_USERS
    active_caption_keywords = caption_keywords if caption_keywords else WISDOM_WARRIOR_ALLOWED_CAPTION_KEYWORDS
    hashtag_map = {_normalize_hashtag(value): value for value in active_hashtags}
    mention_map = {_normalize_mention(value): value for value in active_mentions}
    tagged_user_map = {_normalize_mention(value): value for value in active_tagged_users}
    keyword_matches = [value.casefold() for value in active_caption_keywords]

    summary_by_username: dict[str, dict] = {
        _normalize_mention(profile.username): {
            "username": profile.username,
            "month": month,
            "total_views": 0.0,
            "matched_hashtags": [],
            "matched_mentions": [],
            "matched_tagged_users": [],
        }
        for profile in profiles
    }

    for post in posts:
        if not post.timestamp or post.timestamp.strftime("%Y-%m") != month:
            continue

        owner_username = _normalize_mention(post.owner_username or "")
        collaborator_usernames = _extract_coauthor_usernames(post.coauthor_producers)
        participant_usernames = []
        for participant in [owner_username, *collaborator_usernames]:
            if participant and participant not in participant_usernames:
                participant_usernames.append(participant)

        if not participant_usernames:
            continue

        tracked_participants = [participant for participant in participant_usernames if participant in tracked_usernames]
        credited_usernames = [participant for participant in tracked_participants if participant in usernames]
        if not credited_usernames:
            continue

        post_hashtags = post.hashtags or []
        post_mentions = post.mentions or []
        post_tagged_users = _extract_coauthor_usernames(post.tagged_users)
        caption_text = (post.caption or "").casefold()

        matched_hashtags = []
        matched_mentions = []
        matched_tagged_users = []
        caption_match = False

        if apply_filters:
            matched_hashtags = sorted(
                {
                    hashtag_map[normalized]
                    for normalized in (_normalize_hashtag(value) for value in post_hashtags)
                    if normalized in hashtag_map
                }
            )
            matched_mentions = sorted(
                {
                    mention_map[normalized]
                    for normalized in (_normalize_mention(value) for value in post_mentions)
                    if normalized in mention_map
                }
            )
            matched_tagged_users = sorted(
                {
                    tagged_user_map[normalized]
                    for normalized in post_tagged_users
                    if normalized in tagged_user_map
                }
            )
            caption_match = any(keyword in caption_text for keyword in keyword_matches)

            if not matched_hashtags and not matched_mentions and not matched_tagged_users and not caption_match:
                continue

        shared_views = float(post.video_play_count or 0) / max(1, len(participant_usernames))
        for username_key in credited_usernames:
            summary = summary_by_username.get(username_key)
            if summary is None:
                continue
            summary["total_views"] += shared_views
            if apply_filters:
                summary["matched_hashtags"] = sorted(set(summary["matched_hashtags"]) | set(matched_hashtags))
                summary["matched_mentions"] = sorted(set(summary["matched_mentions"]) | set(matched_mentions))
                summary["matched_tagged_users"] = sorted(
                    set(summary["matched_tagged_users"]) | set(matched_tagged_users)
                )

    return [summary_by_username[_normalize_mention(profile.username)] for profile in profiles]
