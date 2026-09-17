from datetime import date
from typing import Optional, Sequence
from sqlalchemy import Date, Text, and_, cast, delete, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models.post_snapshot import PostSnapshot
from backend.models.post_snapshot_hashtag import PostSnapshotHashtag
from backend.models.post_snapshot_mention import PostSnapshotMention
from backend.models.post_snapshot_tagged_user import PostSnapshotTaggedUser


TAGGED_GROUP_TERMS = {
    "isha": [
        "ishafoundation",
        "savesoil",
        "sadhguru",
        "soilhealth",
        "climateaction",
        "sustainability",
        "sadhgurumargam",
        "mysticsmusings",
        "dhyanalinga",
        "devi",
        "lingabhairavi",
        "bhairavi",
        "adhiyogi",
        "adiyogishiva",
        "ishayoga",
        "ishayogacenter",
        "soundsofisha",
        "innerengineering",
        "sadhanapada",
        "bhavaspandana",
        "shoonyameditation",
        "samyama",
        "cauverycalling",
        "consciousplanet",
        "consciousliving",
        "miracleofmind",
        "hathayoga",
        "kriyayoga",
        "pranayama",
        "sadhguruquotes",
        "sadhguruwisdom",
        "sanatandharma",
        "mahadev",
    ]
}


async def get_post_by_id(db: AsyncSession, post_id: str) -> Optional[dict]:
    result = await db.execute(
        select(PostSnapshot)
        .where(PostSnapshot.post_id == post_id)
        .order_by(PostSnapshot.scraped_at.desc(), PostSnapshot.id.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None
    return _snapshot_to_post_read(row)


async def get_snapshots_by_url(db: AsyncSession, post_url: str) -> Sequence[PostSnapshot]:
    result = await db.execute(
        select(PostSnapshot)
        .where(PostSnapshot.url == post_url)
        .order_by(PostSnapshot.scraped_at)
    )
    return result.scalars().all()


async def insert_snapshot(db: AsyncSession, data: dict) -> PostSnapshot:
    snap = PostSnapshot(**data)
    db.add(snap)
    await db.flush()
    return snap


def _normalize_hashtag(value: str) -> str:
    return value.strip().lstrip("#").casefold()


def _normalize_username(value: str) -> str:
    return value.strip().lstrip("@").casefold()


def _extract_username(value: object) -> str | None:
    if isinstance(value, str):
        candidate = value
    elif isinstance(value, dict):
        candidate = None
        for key in ("username", "userName", "ownerUsername", "handle"):
            raw_value = value.get(key)
            if isinstance(raw_value, str) and raw_value.strip():
                candidate = raw_value
                break
    else:
        candidate = None

    if not candidate:
        return None
    normalized = _normalize_username(candidate)
    return normalized or None


def _snapshot_to_post_read(row: PostSnapshot) -> dict:
    return {
        "id": row.post_id,
        "source_post_id": None,
        "short_code": None,
        "owner_username": row.owner_username,
        "owner_full_name": None,
        "owner_id": None,
        "owner_profile_pic_url": None,
        "location_name": None,
        "location_id": None,
        "url": row.url,
        "timestamp": row.timestamp,
        "likes_count": row.likes_count or 0,
        "video_play_count": row.video_play_count or 0,
        "video_view_count": 0,
        "type": row.type,
        "video_url": row.video_url,
        "audio_url": None,
        "video_duration": None,
        "display_url": row.display_url,
        "display_storage_path": row.display_storage_path,
        "display_storage_url": row.display_storage_url,
        "dimensions_height": None,
        "dimensions_width": None,
        "is_comments_disabled": False,
        "alt": None,
        "caption": row.caption,
        "product_type": row.product_type,
        "input_url": row.input_url,
        "comments_count": 0,
        "first_comment": None,
        "latest_comments": [],
        "images": [],
        "child_posts": [],
        "music_info": {},
        "hashtags": row.hashtags or [],
        "mentions": row.mentions or [],
        "tagged_users": row.tagged_users or [],
        "coauthor_producers": row.coauthor_producers or [],
        "is_pinned": False,
        "profile_id": None,
        "scraped_at": row.scraped_at,
        "period_label": row.period_label,
        "run_id": row.run_id,
        "embedding": None,
    }


async def replace_snapshot_hashtags(
    db: AsyncSession,
    *,
    snapshot_id: int,
    post_id: str,
    run_id: int | None,
    period_label: str,
    owner_username: str | None,
    hashtags: Sequence[str] | None,
) -> None:
    await db.execute(
        delete(PostSnapshotHashtag).where(PostSnapshotHashtag.snapshot_id == snapshot_id)
    )

    if not hashtags:
        return

    seen: set[str] = set()
    rows: list[PostSnapshotHashtag] = []
    for value in hashtags:
        if not isinstance(value, str):
            continue
        raw = value.strip()
        if not raw:
            continue
        norm = _normalize_hashtag(raw)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        rows.append(
            PostSnapshotHashtag(
                snapshot_id=snapshot_id,
                post_id=post_id,
                run_id=run_id,
                period_label=period_label,
                owner_username=owner_username,
                hashtag_raw=raw,
                hashtag_norm=norm,
            )
        )

    if rows:
        db.add_all(rows)


async def replace_snapshot_mentions(
    db: AsyncSession,
    *,
    snapshot_id: int,
    post_id: str,
    run_id: int | None,
    period_label: str,
    owner_username: str | None,
    mentions: Sequence[str] | None,
) -> None:
    await db.execute(
        delete(PostSnapshotMention).where(PostSnapshotMention.snapshot_id == snapshot_id)
    )

    if not mentions:
        return

    seen: set[str] = set()
    rows: list[PostSnapshotMention] = []
    for value in mentions:
        if not isinstance(value, str):
            continue
        raw = value.strip()
        if not raw:
            continue
        norm = _normalize_username(raw)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        rows.append(
            PostSnapshotMention(
                snapshot_id=snapshot_id,
                post_id=post_id,
                run_id=run_id,
                period_label=period_label,
                owner_username=owner_username,
                mention_raw=raw,
                mention_norm=norm,
            )
        )

    if rows:
        db.add_all(rows)


async def replace_snapshot_tagged_users(
    db: AsyncSession,
    *,
    snapshot_id: int,
    post_id: str,
    run_id: int | None,
    period_label: str,
    owner_username: str | None,
    tagged_users: Sequence[object] | None,
) -> None:
    await db.execute(
        delete(PostSnapshotTaggedUser).where(PostSnapshotTaggedUser.snapshot_id == snapshot_id)
    )

    if not tagged_users:
        return

    seen: set[str] = set()
    rows: list[PostSnapshotTaggedUser] = []
    for value in tagged_users:
        norm = _extract_username(value)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        raw = str(value).strip() if isinstance(value, str) else norm
        rows.append(
            PostSnapshotTaggedUser(
                snapshot_id=snapshot_id,
                post_id=post_id,
                run_id=run_id,
                period_label=period_label,
                owner_username=owner_username,
                tagged_user_raw=raw,
                tagged_user_norm=norm,
            )
        )

    if rows:
        db.add_all(rows)


def _clean_filter_values(values: Sequence[str] | None) -> list[str]:
    if not values:
        return []
    return list(dict.fromkeys(value.strip() for value in values if value and value.strip()))


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


async def list_posts(
    db: AsyncSession,
    username: Optional[str] = None,
    post_type: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    likes_min: Optional[int] = None,
    hashtag: Optional[str] = None,
    hashtags: Sequence[str] | None = None,
    mentions: Sequence[str] | None = None,
    tagged_users: Sequence[str] | None = None,
    keywords: Sequence[str] | None = None,
    tagged_group: Optional[str] = None,
    period_label: Optional[str] = None,
    snapshot_run_id: Optional[int] = None,
    sort: str = "likes_count",
    limit: int = 50,
    offset: int = 0,
) -> tuple[Sequence[dict], int]:
    if snapshot_run_id is not None:
        q = select(PostSnapshot).where(PostSnapshot.run_id == snapshot_run_id)
        parsed_date_from = _parse_iso_date(date_from)
        parsed_date_to = _parse_iso_date(date_to)

        if username:
            q = q.where(PostSnapshot.owner_username == username)
        if post_type:
            q = q.where(func.lower(func.coalesce(PostSnapshot.type, "")).like(f"%{post_type.lower()}%"))
        if parsed_date_from:
            q = q.where(cast(PostSnapshot.timestamp, Date) >= parsed_date_from)
        if parsed_date_to:
            q = q.where(cast(PostSnapshot.timestamp, Date) <= parsed_date_to)
        if likes_min is not None:
            q = q.where(PostSnapshot.likes_count >= likes_min)

        hashtag_terms = _clean_filter_values([*(hashtags or []), hashtag] if hashtag else hashtags)
        mention_terms = _clean_filter_values(mentions)
        tagged_user_terms = _clean_filter_values(tagged_users)
        keyword_terms = _clean_filter_values(keywords)

        content_filters = []
        if hashtag_terms:
            normalized_terms = [
                _normalize_hashtag(term)
                for term in hashtag_terms
                if _normalize_hashtag(term)
            ]
            if normalized_terms:
                content_filters.append(
                    exists(
                        select(1).where(
                            and_(
                                PostSnapshotHashtag.snapshot_id == PostSnapshot.id,
                                PostSnapshotHashtag.hashtag_norm.in_(normalized_terms),
                            )
                        )
                    )
                )
        if mention_terms:
            normalized_mention_terms = [
                _normalize_username(term)
                for term in mention_terms
                if _normalize_username(term)
            ]
            if normalized_mention_terms:
                content_filters.append(
                    exists(
                        select(1).where(
                            and_(
                                PostSnapshotMention.snapshot_id == PostSnapshot.id,
                                PostSnapshotMention.mention_norm.in_(normalized_mention_terms),
                            )
                        )
                    )
                )
        if tagged_user_terms:
            normalized_tagged_user_terms = [
                _normalize_username(term)
                for term in tagged_user_terms
                if _normalize_username(term)
            ]
            if normalized_tagged_user_terms:
                content_filters.append(
                    exists(
                        select(1).where(
                            and_(
                                PostSnapshotTaggedUser.snapshot_id == PostSnapshot.id,
                                PostSnapshotTaggedUser.tagged_user_norm.in_(normalized_tagged_user_terms),
                            )
                        )
                    )
                )
        if keyword_terms:
            caption_text = func.lower(func.coalesce(PostSnapshot.caption, ""))
            content_filters.extend(caption_text.like(f"%{term.lower()}%") for term in keyword_terms)
        if content_filters:
            q = q.where(or_(*content_filters))

        if tagged_group:
            terms = TAGGED_GROUP_TERMS.get(tagged_group.lower(), [])
            if terms:
                normalized_group_terms = [
                    _normalize_hashtag(term)
                    for term in terms
                    if _normalize_hashtag(term)
                ]
                hashtag_exists = (
                    exists(
                        select(1).where(
                            and_(
                                PostSnapshotHashtag.snapshot_id == PostSnapshot.id,
                                PostSnapshotHashtag.hashtag_norm.in_(normalized_group_terms),
                            )
                        )
                    )
                    if normalized_group_terms
                    else False
                )
                q = q.where(
                    or_(
                        *[
                            or_(
                                func.lower(func.coalesce(PostSnapshot.caption, "")).like(f"%{term}%"),
                                func.lower(func.coalesce(PostSnapshot.owner_username, "")).like(f"%{term}%"),
                                hashtag_exists,
                                func.lower(func.coalesce(cast(PostSnapshot.coauthor_producers, Text), "")).like(f"%{term}%"),
                            )
                            for term in terms
                        ]
                    )
                )
        if period_label:
            q = q.where(PostSnapshot.period_label == period_label)

        count_result = await db.execute(select(func.count()).select_from(q.subquery()))
        total = count_result.scalar_one()

        sort_col = getattr(PostSnapshot, sort, PostSnapshot.likes_count)
        q = q.order_by(sort_col.desc()).limit(limit).offset(offset)
        result = await db.execute(q)
        rows = result.scalars().all()

        items = [_snapshot_to_post_read(row) for row in rows]
        return items, total

    latest_snapshots = select(
        PostSnapshot.id.label("snapshot_id"),
        func.row_number()
        .over(
            partition_by=PostSnapshot.url,
            order_by=(PostSnapshot.scraped_at.desc(), PostSnapshot.id.desc()),
        )
        .label("snapshot_rank"),
    ).subquery()

    q = (
        select(PostSnapshot)
        .join(latest_snapshots, latest_snapshots.c.snapshot_id == PostSnapshot.id)
        .where(latest_snapshots.c.snapshot_rank == 1)
    )
    parsed_date_from = _parse_iso_date(date_from)
    parsed_date_to = _parse_iso_date(date_to)

    if username:
        q = q.where(PostSnapshot.owner_username == username)
    if post_type:
        q = q.where(func.lower(func.coalesce(PostSnapshot.type, "")).like(f"%{post_type.lower()}%"))
    if parsed_date_from:
        q = q.where(cast(PostSnapshot.timestamp, Date) >= parsed_date_from)
    if parsed_date_to:
        q = q.where(cast(PostSnapshot.timestamp, Date) <= parsed_date_to)
    if likes_min is not None:
        q = q.where(PostSnapshot.likes_count >= likes_min)

    hashtag_terms = _clean_filter_values([*(hashtags or []), hashtag] if hashtag else hashtags)
    mention_terms = _clean_filter_values(mentions)
    tagged_user_terms = _clean_filter_values(tagged_users)
    keyword_terms = _clean_filter_values(keywords)

    content_filters = []
    if hashtag_terms:
        normalized_terms = [_normalize_hashtag(term) for term in hashtag_terms if _normalize_hashtag(term)]
        if normalized_terms:
            content_filters.append(
                exists(
                    select(1).where(
                        and_(
                            PostSnapshotHashtag.snapshot_id == PostSnapshot.id,
                            PostSnapshotHashtag.hashtag_norm.in_(normalized_terms),
                        )
                    )
                )
            )
    if mention_terms:
        normalized_mention_terms = [_normalize_username(term) for term in mention_terms if _normalize_username(term)]
        if normalized_mention_terms:
            content_filters.append(
                exists(
                    select(1).where(
                        and_(
                            PostSnapshotMention.snapshot_id == PostSnapshot.id,
                            PostSnapshotMention.mention_norm.in_(normalized_mention_terms),
                        )
                    )
                )
            )
    if tagged_user_terms:
        normalized_tagged_user_terms = [_normalize_username(term) for term in tagged_user_terms if _normalize_username(term)]
        if normalized_tagged_user_terms:
            content_filters.append(
                exists(
                    select(1).where(
                        and_(
                            PostSnapshotTaggedUser.snapshot_id == PostSnapshot.id,
                            PostSnapshotTaggedUser.tagged_user_norm.in_(normalized_tagged_user_terms),
                        )
                    )
                )
            )
    if keyword_terms:
        caption_text = func.lower(func.coalesce(PostSnapshot.caption, ""))
        content_filters.extend(caption_text.like(f"%{term.lower()}%") for term in keyword_terms)
    if content_filters:
        q = q.where(or_(*content_filters))

    if tagged_group:
        terms = TAGGED_GROUP_TERMS.get(tagged_group.lower(), [])
        if terms:
            normalized_group_terms = [_normalize_hashtag(term) for term in terms if _normalize_hashtag(term)]
            hashtag_exists = (
                exists(
                    select(1).where(
                        and_(
                            PostSnapshotHashtag.snapshot_id == PostSnapshot.id,
                            PostSnapshotHashtag.hashtag_norm.in_(normalized_group_terms),
                        )
                    )
                )
                if normalized_group_terms
                else False
            )
            q = q.where(
                or_(
                    *[
                        or_(
                            func.lower(func.coalesce(PostSnapshot.caption, "")).like(f"%{term}%"),
                            func.lower(func.coalesce(PostSnapshot.owner_username, "")).like(f"%{term}%"),
                            hashtag_exists,
                            func.lower(func.coalesce(cast(PostSnapshot.coauthor_producers, Text), "")).like(f"%{term}%"),
                        )
                        for term in terms
                    ]
                )
            )
    if period_label:
        q = q.where(PostSnapshot.period_label == period_label)

    count_result = await db.execute(select(func.count()).select_from(q.subquery()))
    total = count_result.scalar_one()

    sort_col = getattr(PostSnapshot, sort, PostSnapshot.likes_count)
    q = q.order_by(sort_col.desc()).limit(limit).offset(offset)
    result = await db.execute(q)
    return [_snapshot_to_post_read(row) for row in result.scalars().all()], total
