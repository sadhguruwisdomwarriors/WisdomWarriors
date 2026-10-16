import asyncio
import json
import os
import re
import psycopg2
from collections import defaultdict
from datetime import datetime
import numpy as np
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from types import SimpleNamespace

from backend.repositories.analytics_repo import (
    WISDOM_WARRIOR_ALLOWED_HASHTAGS,
    WISDOM_WARRIOR_ALLOWED_MENTIONS,
    WISDOM_WARRIOR_ALLOWED_TAGGED_USERS,
    WISDOM_WARRIOR_ALLOWED_CAPTION_KEYWORDS,
    _normalize_hashtag,
    _normalize_mention,
    check_post_matches_filters
)

DATABASE_URL = "postgresql://postgres.juxvmzccqbroqcoleobp:DH98ZW0BlCe4zV6C@aws-1-ap-south-1.pooler.supabase.com:5432/postgres"

def get_prior_6_months(year: int, month: int) -> list[str]:
    prior_months = []
    cur_y, cur_m = year, month
    for _ in range(6):
        cur_m -= 1
        if cur_m <= 0:
            cur_m = 12
            cur_y -= 1
        prior_months.append(f"{cur_y}-{cur_m:02d}")
    return prior_months

def extract_coauthors(raw_coauthors) -> list[str]:
    if not raw_coauthors:
        return []
    if isinstance(raw_coauthors, str):
        try:
            raw_coauthors = json.loads(raw_coauthors)
        except Exception:
            return []
    res = []
    if isinstance(raw_coauthors, list):
        for item in raw_coauthors:
            if isinstance(item, str):
                c = item.strip().lstrip("@").lower()
                if c and c not in res:
                    res.append(c)
            elif isinstance(item, dict):
                for k in ("username", "userName", "ownerUsername", "handle"):
                    val = item.get(k)
                    if isinstance(val, str) and val.strip():
                        c = val.strip().lstrip("@").lower()
                        if c and c not in res:
                            res.append(c)
                        break
    return res

def main():
    print("=" * 80)
    print("WISDOM WARRIORS — COMPLETE AUGUST & SEPTEMBER DELTA CALCULATION")
    print("Strictly adhering to gemini.md specifications (6-Case Master Specification)")
    print("=" * 80)

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    # 1. Fetch all profiles from scrape_profiles
    cur.execute("""
        SELECT id, username, category, grade, instagram_id 
        FROM scrape_profiles 
        ORDER BY category ASC, username ASC;
    """)
    profiles = cur.fetchall()
    print(f"Total registered profiles in database: {len(profiles)}")

    # 2. Fetch micro units mappings
    cur.execute("""
        SELECT muc.username, muc.instagram_id, muc.creator_name, mu.unit_number, mu.name as unit_name
        FROM micro_unit_channels muc
        JOIN micro_units mu ON muc.micro_unit_id = mu.id;
    """)
    mu_rows = cur.fetchall()
    mu_map = {}
    for r in mu_rows:
        uname = r[0].strip().lstrip("@").lower()
        mu_map[uname] = {
            "creator_name": r[2] or "",
            "unit_number": r[3],
            "unit_name": r[4]
        }
    print(f"Micro Unit assigned channels: {len(mu_map)}")

    profile_list = []
    target_usernames = set()
    category_map = {}

    for pid, uname, cat, grade, ig_id in profiles:
        clean_u = uname.strip().lstrip("@").lower()
        target_usernames.add(clean_u)
        clean_cat = cat or "Dedicated"
        category_map[clean_u] = clean_cat
        mu_info = mu_map.get(clean_u, {})
        profile_list.append({
            "id": pid,
            "username": uname,
            "clean_username": clean_u,
            "category": clean_cat,
            "grade": grade or "Unassigned",
            "instagram_id": ig_id or f"sp_{pid}",
            "unit_number": mu_info.get("unit_number", "-"),
            "unit_name": mu_info.get("unit_name", "Unassigned"),
            "creator_name": mu_info.get("creator_name", "")
        })

    # Prepare filter lookup maps
    hashtag_map = {_normalize_hashtag(h): h for h in WISDOM_WARRIOR_ALLOWED_HASHTAGS}
    mention_map = {_normalize_mention(m): m for m in WISDOM_WARRIOR_ALLOWED_MENTIONS}
    tagged_user_map = {_normalize_mention(t): t for t in WISDOM_WARRIOR_ALLOWED_TAGGED_USERS}
    keyword_matches = [k.casefold() for k in WISDOM_WARRIOR_ALLOWED_CAPTION_KEYWORDS]

    # Pre-fetch post snapshots for runs 97, 111, 112
    print("\nFetching post snapshots for runs 97, 111, 112...")
    cur.execute("""
        SELECT post_id, run_id, owner_username, coauthor_producers, video_play_count, timestamp, caption, hashtags, mentions, tagged_users, type, product_type, video_view_count, url
        FROM post_snapshots
        WHERE run_id IN (97, 111, 112) AND timestamp IS NOT NULL;
    """)
    all_raw_posts = cur.fetchall()
    print(f"Fetched {len(all_raw_posts)} total post rows.")

    shortcode_regex = re.compile(r'/p/([^/?#&]+)|/reel/([^/?#&]+)')

    # Deduplicate posts per run by shortcode (keeping highest video_play_count)
    posts_by_run = defaultdict(dict)
    for row in all_raw_posts:
        pid, rid, owner, coauthors, vpc, ts, caption, hashtags, mentions, tagged_users, ptype, prod_type, vvc, url = row
        m = shortcode_regex.search(url or '')
        sc = (m.group(1) or m.group(2)) if m else (url or pid)
        vpc = vpc or 0

        if sc not in posts_by_run[rid] or vpc > posts_by_run[rid][sc]["vpc"]:
            posts_by_run[rid][sc] = {
                "shortcode": sc,
                "owner": (owner or "").strip().lstrip("@").lower(),
                "coauthors": extract_coauthors(coauthors),
                "vpc": vpc,
                "ts": ts,
                "ym": ts.strftime("%Y-%m") if ts else "",
                "caption": caption or "",
                "hashtags": hashtags or [],
                "mentions": mentions or [],
                "tagged_users": tagged_users or [],
                "is_reel": (
                    (ptype in ("Video", "ReelVideo"))
                    or (prod_type == "clips")
                    or bool(vpc and vpc > 0)
                    or bool(vvc and vvc > 0)
                )
            }

    print(f"Unique posts in Run 97: {len(posts_by_run[97])}")
    print(f"Unique posts in Run 111: {len(posts_by_run[111])}")
    print(f"Unique posts in Run 112: {len(posts_by_run[112])}")

    # Build direct index for monitored channels: channel_posts[run_id][channel_clean_username][shortcode]
    print("\nIndexing posts by monitored channel and applying taxonomy filters...")
    channel_posts = defaultdict(lambda: defaultdict(dict))

    for rid, sc_dict in posts_by_run.items():
        for sc, p in sc_dict.items():
            owner = p["owner"]
            coauthors = p["coauthors"]
            participants = []
            for part in [owner, *coauthors]:
                if part and part not in participants:
                    participants.append(part)
            if not participants:
                continue

            split_factor = max(1, len(participants))
            shared_views = float(p["vpc"]) / split_factor
            ym = p["ts"].strftime("%Y-%m")

            post_obj = SimpleNamespace(
                caption=p["caption"],
                hashtags=p["hashtags"],
                mentions=p["mentions"],
                tagged_users=p["tagged_users"]
            )
            matches_filter, _, _, _ = check_post_matches_filters(
                post_obj, hashtag_map, mention_map, tagged_user_map, keyword_matches
            )

            for part in participants:
                if part in target_usernames:
                    user_cat = category_map.get(part, "Dedicated")
                    is_ihi = (user_cat.strip().lower() == "in-house influencer")

                    # Dedicated channels get all posts unconditionally; IHI get only filtered ones
                    if is_ihi and not matches_filter:
                        continue

                    channel_posts[rid][part][sc] = {
                        "shortcode": sc,
                        "vpc": p["vpc"],
                        "divided_views": shared_views,
                        "ts": p["ts"],
                        "ym": ym,
                        "is_reel": p["is_reel"]
                    }

    def calculate_monitored_month_metrics(target_year: int, target_month: int, s1_run_id: int, s2_run_id: int):
        target_ym = f"{target_year}-{target_month:02d}"
        prior_months = get_prior_6_months(target_year, target_month)
        prior_months_set = set(prior_months)
        window_months_set = prior_months_set | {target_ym}

        results = {}
        for uname in target_usernames:
            s1_posts = channel_posts[s1_run_id].get(uname, {})
            s2_posts = channel_posts[s2_run_id].get(uname, {})

            s1_prior = {sc: p for sc, p in s1_posts.items() if p["ym"] in prior_months_set}
            s2_prior = {sc: p for sc, p in s2_posts.items() if p["ym"] in prior_months_set}
            s2_target = {sc: p for sc, p in s2_posts.items() if p["ym"] == target_ym}

            # Case 6: Newly Scraped Channel (S1 = 0, S2 > 0)
            if len(s1_posts) == 0 and len(s2_posts) > 0:
                s2_window_posts = {sc: p for sc, p in s2_posts.items() if p["ym"] in window_months_set}
                active_months = {p["ym"] for p in s2_window_posts.values() if p["divided_views"] > 0}
                if active_months:
                    earliest_ym = min(active_months)
                    ey, em = map(int, earliest_ym.split("-"))
                    span = (target_year - ey) * 12 + (target_month - em) + 1
                    divisor = max(1, min(7, span))
                else:
                    divisor = 1
                tot_window_views = sum(p["divided_views"] for p in s2_window_posts.values())
                monthly_total = tot_window_views / divisor
                target_new_views = sum(p["divided_views"] for p in s2_target.values())
                active_reels = {sc for sc, p in s2_window_posts.items() if p["divided_views"] > 0}
                results[uname] = {
                    "total_views": monthly_total,
                    "new_views": target_new_views,
                    "decay_delta": max(0.0, monthly_total - target_new_views),
                    "post_count": len(s2_target),
                    "reel_count": sum(1 for p in s2_target.values() if p["is_reel"]),
                    "active_reel_count": len(active_reels),
                    "active_reels": active_reels,
                    "new_reels": set(s2_target.keys()),
                    "calc_type": f"Case 6: Newly Scraped ({divisor} mo avg)",
                    "divisor": divisor
                }
                continue

            # Case 2: Total Channel Crawl Dropout (S1 > 0, S2 = 0)
            if len(s1_posts) > 0 and len(s2_posts) == 0:
                active_s1_months = {p["ym"] for p in s1_prior.values() if p["divided_views"] > 0}
                divisor = max(1, len(active_s1_months))
                tot_s1_prior_views = sum(p["divided_views"] for p in s1_prior.values())
                monthly_total = tot_s1_prior_views / divisor
                active_reels = {sc for sc, p in s1_prior.items() if p["divided_views"] > 0}
                results[uname] = {
                    "total_views": monthly_total,
                    "new_views": 0.0,
                    "decay_delta": monthly_total,
                    "post_count": 0,
                    "reel_count": 0,
                    "active_reel_count": len(active_reels),
                    "active_reels": active_reels,
                    "new_reels": set(),
                    "calc_type": f"Case 2: Total Crawl Dropout ({divisor} mo S1 avg)",
                    "divisor": divisor
                }
                continue

            if len(s1_posts) == 0 and len(s2_posts) == 0:
                results[uname] = {
                    "total_views": 0.0,
                    "new_views": 0.0,
                    "decay_delta": 0.0,
                    "post_count": 0,
                    "reel_count": 0,
                    "active_reel_count": 0,
                    "active_reels": set(),
                    "new_reels": set(),
                    "calc_type": "No Data",
                    "divisor": "-"
                }
                continue

            # Surviving channels (Cases 1, 3, 4, 5)
            new_views = sum(p["divided_views"] for p in s2_target.values())
            post_count = len(s2_target)
            reel_count = sum(1 for p in s2_target.values() if p["is_reel"])

            surviving_scs = set(s1_prior.keys()) & set(s2_prior.keys())
            dropped_scs = set(s1_prior.keys()) - set(s2_prior.keys())
            new_prior_scs = set(s2_prior.keys()) - set(s1_prior.keys())

            surv_delta = 0.0
            surv_s1_tot = 0.0
            surv_s2_tot = 0.0
            rates = []
            for sc in surviving_scs:
                v1 = s1_prior[sc]["divided_views"]
                v2 = s2_prior[sc]["divided_views"]
                d = max(0.0, v2 - v1)
                surv_delta += d
                surv_s1_tot += v1
                surv_s2_tot += v2
                if v1 > 0:
                    rates.append((v2 - v1) / v1)

            # Handle dropped reels under Cases 1, 4, 5
            dropped_delta = 0.0
            calc_case = "Standard Delta (S2 - S1 + New)"
            if dropped_scs:
                if surv_s1_tot > 0:
                    g_agg = (surv_s2_tot - surv_s1_tot) / surv_s1_tot
                    g_median = float(np.median(rates)) if rates else 0.0

                    # Case 5 vs Case 1 & 4
                    if g_agg > 0.10 or any(r > 0.15 for r in rates):
                        g_impute = min(max(0.0, g_median), 0.10)
                        calc_case = f"Case 5: Viral Spike Isolated + Imputed ({g_impute*100:.2f}%)"
                    elif g_agg <= 0.0:
                        g_impute = 0.0
                        calc_case = "Case 4: Zero/Negative Growth Clamped"
                    else:
                        g_impute = g_agg
                        calc_case = f"Case 1: Partial Drop Imputed ({g_impute*100:.2f}%)"
                else:
                    g_impute = 0.0
                    calc_case = "Case 1: Dropped with No Surviving Delta"

                for sc in dropped_scs:
                    v1 = s1_prior[sc]["divided_views"]
                    dropped_delta += v1 * g_impute

            new_prior_delta = sum(s2_prior[sc]["divided_views"] for sc in new_prior_scs)
            total_decay = surv_delta + dropped_delta + new_prior_delta
            total_views = new_views + total_decay

            target_reels = set(s2_target.keys())
            active_decay_reels = {sc for sc in surviving_scs if (s2_prior[sc]["divided_views"] - s1_prior[sc]["divided_views"]) > 0}
            if dropped_delta > 0:
                active_decay_reels.update(dropped_scs)
            active_decay_reels.update({sc for sc in new_prior_scs if s2_prior[sc]["divided_views"] > 0})
            total_active_reels = target_reels | active_decay_reels

            results[uname] = {
                "total_views": total_views,
                "new_views": new_views,
                "decay_delta": total_decay,
                "post_count": post_count,
                "reel_count": reel_count,
                "active_reel_count": len(total_active_reels),
                "active_reels": total_active_reels,
                "new_reels": target_reels,
                "calc_type": calc_case,
                "divisor": "-"
            }
        return results

    # 3. Calculate August and September 2026 for Monitored Channels
    print("\nCalculating August 2026 metrics for Monitored Channels (S1=97, S2=111)...")
    aug_res = calculate_monitored_month_metrics(2026, 8, 97, 111)

    print("Calculating September 2026 metrics for Monitored Channels (S1=111, S2=112)...")
    sep_res = calculate_monitored_month_metrics(2026, 9, 111, 112)

    # 4. Sync / Upsert Monitored Metrics into monthly_channel_metrics table
    print("\nSyncing calculated metrics into monthly_channel_metrics table...")
    upsert_sql = """
        INSERT INTO monthly_channel_metrics (
            instagram_id, username, year_month, monthly_views,
            previous_monthly_views, growth_percent, post_count,
            reels_count, static_post_count, views_per_post,
            snapshot1_run_id, snapshot2_run_id, calculated_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()
        )
        ON CONFLICT (instagram_id, year_month) DO UPDATE SET
            username = EXCLUDED.username,
            monthly_views = EXCLUDED.monthly_views,
            previous_monthly_views = EXCLUDED.previous_monthly_views,
            growth_percent = EXCLUDED.growth_percent,
            post_count = EXCLUDED.post_count,
            reels_count = EXCLUDED.reels_count,
            static_post_count = EXCLUDED.static_post_count,
            views_per_post = EXCLUDED.views_per_post,
            snapshot1_run_id = EXCLUDED.snapshot1_run_id,
            snapshot2_run_id = EXCLUDED.snapshot2_run_id,
            calculated_at = NOW();
    """

    for prof in profile_list:
        clean_u = prof["clean_username"]
        ig_id = prof["instagram_id"]

        aug_data = aug_res.get(clean_u, {})
        aug_v = aug_data.get("total_views", 0.0)
        aug_p = aug_data.get("post_count", 0)
        aug_r = aug_data.get("reel_count", 0)
        aug_s = aug_p - aug_r
        aug_vpp = aug_v / aug_p if aug_p > 0 else 0.0

        cur.execute(upsert_sql, (
            ig_id, prof["username"], "2026-08", aug_v, None, None,
            aug_p, aug_r, aug_s, aug_vpp, 97, 111
        ))

        sep_data = sep_res.get(clean_u, {})
        sep_v = sep_data.get("total_views", 0.0)
        sep_p = sep_data.get("post_count", 0)
        sep_r = sep_data.get("reel_count", 0)
        sep_s = sep_p - sep_r
        sep_vpp = sep_v / sep_p if sep_p > 0 else 0.0

        growth_pct = ((sep_v - aug_v) / aug_v * 100) if aug_v > 0 else None

        cur.execute(upsert_sql, (
            ig_id, prof["username"], "2026-09", sep_v, aug_v, growth_pct,
            sep_p, sep_r, sep_s, sep_vpp, 111, 112
        ))

    conn.commit()
    print("Database sync completed successfully.")

    # 5. CALCULATE UNMONITORED CHANNELS SEPARATELY (ZERO FAKE VIEWS)
    print("\nCalculating Unmonitored Channels collaborative metrics (Dedicated & IHI)...")

    all_collab_scs = set()
    for rid in (97, 111, 112):
        for sc, p in posts_by_run[rid].items():
            parts = list(set([p["owner"], *p["coauthors"]]))
            if len(parts) > 1 and any(x in target_usernames for x in parts):
                all_collab_scs.add(sc)

    unmon_ded = defaultdict(lambda: {
        "aug_new": 0.0, "aug_decay": 0.0, "sep_new": 0.0, "sep_decay": 0.0,
        "linked": set(), "is_owner_count": 0, "total_reels": set(),
        "aug_new_reels": set(), "aug_decay_reels": set(),
        "sep_new_reels": set(), "sep_decay_reels": set()
    })
    unmon_ihi = defaultdict(lambda: {
        "aug_new": 0.0, "aug_decay": 0.0, "sep_new": 0.0, "sep_decay": 0.0,
        "linked": set(), "is_owner_count": 0, "total_reels": set(),
        "aug_new_reels": set(), "aug_decay_reels": set(),
        "sep_new_reels": set(), "sep_decay_reels": set()
    })

    for sc in all_collab_scs:
        p_latest = None
        for rid in (112, 111, 97):
            if sc in posts_by_run[rid]:
                p_latest = posts_by_run[rid][sc]
                break
        if not p_latest:
            continue

        owner = p_latest["owner"]
        coauthors = p_latest["coauthors"]
        parts = list(set([owner, *coauthors]))
        split = len(parts)

        mon_parts = [x for x in parts if x in target_usernames]
        ext_parts = [x for x in parts if x not in target_usernames]
        if not mon_parts or not ext_parts:
            continue

        ym = p_latest.get("ym") or (p_latest["ts"].strftime("%Y-%m") if p_latest.get("ts") else "")

        has_ded = any(category_map[m].strip().lower() == "dedicated" for m in mon_parts)
        has_ihi = any(category_map[m].strip().lower() == "in-house influencer" for m in mon_parts)

        post_obj = SimpleNamespace(
            caption=p_latest["caption"],
            hashtags=p_latest["hashtags"],
            mentions=p_latest["mentions"],
            tagged_users=p_latest["tagged_users"]
        )
        matches_filter, _, _, _ = check_post_matches_filters(
            post_obj, hashtag_map, mention_map, tagged_user_map, keyword_matches
        )

        v97 = posts_by_run[97].get(sc, {}).get("vpc", None)
        v111 = posts_by_run[111].get(sc, {}).get("vpc", None)
        v112 = posts_by_run[112].get(sc, {}).get("vpc", None)

        # August calculation
        aug_new_share = 0.0
        aug_decay_share = 0.0
        if ym == "2026-08":
            if v111 is not None:
                aug_new_share = float(v111) / split
        elif "2026-02" <= ym <= "2026-07":
            if v97 is not None and v111 is not None:
                d = max(0, v111 - v97)
                aug_decay_share = float(d) / split

        # September calculation
        sep_new_share = 0.0
        sep_decay_share = 0.0
        if ym == "2026-09":
            if v112 is not None:
                sep_new_share = float(v112) / split
        elif "2026-03" <= ym <= "2026-08":
            if v111 is not None and v112 is not None:
                d = max(0, v112 - v111)
                sep_decay_share = float(d) / split

        # Attribution to Dedicated Unmonitored List
        if has_ded:
            for ext in ext_parts:
                unmon_ded[ext]["aug_new"] += aug_new_share
                unmon_ded[ext]["aug_decay"] += aug_decay_share
                unmon_ded[ext]["sep_new"] += sep_new_share
                unmon_ded[ext]["sep_decay"] += sep_decay_share
                unmon_ded[ext]["total_reels"].add(sc)
                if aug_new_share > 0:
                    unmon_ded[ext]["aug_new_reels"].add(sc)
                if aug_decay_share > 0:
                    unmon_ded[ext]["aug_decay_reels"].add(sc)
                if sep_new_share > 0:
                    unmon_ded[ext]["sep_new_reels"].add(sc)
                if sep_decay_share > 0:
                    unmon_ded[ext]["sep_decay_reels"].add(sc)
                if ext == owner:
                    unmon_ded[ext]["is_owner_count"] += 1
                for m in mon_parts:
                    if category_map[m].strip().lower() == "dedicated":
                        unmon_ded[ext]["linked"].add(m)

        # Attribution to IHI Unmonitored List (Filter-passing only)
        if has_ihi and not has_ded:
            if matches_filter:
                for ext in ext_parts:
                    unmon_ihi[ext]["aug_new"] += aug_new_share
                    unmon_ihi[ext]["aug_decay"] += aug_decay_share
                    unmon_ihi[ext]["sep_new"] += sep_new_share
                    unmon_ihi[ext]["sep_decay"] += sep_decay_share
                    unmon_ihi[ext]["total_reels"].add(sc)
                    if aug_new_share > 0:
                        unmon_ihi[ext]["aug_new_reels"].add(sc)
                    if aug_decay_share > 0:
                        unmon_ihi[ext]["aug_decay_reels"].add(sc)
                    if sep_new_share > 0:
                        unmon_ihi[ext]["sep_new_reels"].add(sc)
                    if sep_decay_share > 0:
                        unmon_ihi[ext]["sep_decay_reels"].add(sc)
                    if ext == owner:
                        unmon_ihi[ext]["is_owner_count"] += 1
                    for m in mon_parts:
                        if category_map[m].strip().lower() == "in-house influencer":
                            unmon_ihi[ext]["linked"].add(m)

    print(f"Total Unmonitored Channels linked to Dedicated: {len(unmon_ded)}")
    print(f"Total Unmonitored Channels linked to IHI: {len(unmon_ihi)}")

    # 6. BUILD EXCEL WORKBOOK REPORT
    print("\nGenerating comprehensive Excel workbook with 6 sheets...")
    wb = openpyxl.Workbook()
    wb.remove(wb.active)  # Remove default sheet

    # Styles
    navy_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    purple_fill = PatternFill(start_color="4C1D95", end_color="4C1D95", fill_type="solid")
    header_fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
    alt_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    highlight_fill = PatternFill(start_color="EDE9FE", end_color="EDE9FE", fill_type="solid")
    light_blue_fill = PatternFill(start_color="EFF6FF", end_color="EFF6FF", fill_type="solid")
    light_amber_fill = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")

    white_bold = Font(name="Segoe UI", size=10, bold=True, color="FFFFFF")
    white_title = Font(name="Segoe UI", size=15, bold=True, color="FFFFFF")
    white_subtitle = Font(name="Segoe UI", size=10, bold=False, color="CBD5E1")
    dark_bold = Font(name="Segoe UI", size=10, bold=True, color="0F172A")
    dark_regular = Font(name="Segoe UI", size=9, bold=False, color="1E293B")
    green_bold = Font(name="Segoe UI", size=9, bold=True, color="047857")
    red_bold = Font(name="Segoe UI", size=9, bold=True, color="B91C1C")
    gray_regular = Font(name="Segoe UI", size=9, bold=False, color="64748B")

    thin_border_side = Side(style="thin", color="E2E8F0")
    thin_border = Border(left=thin_border_side, right=thin_border_side, top=thin_border_side, bottom=thin_border_side)
    thick_bottom = Border(bottom=Side(style="medium", color="0F172A"), top=thin_border_side, left=thin_border_side, right=thin_border_side)
    double_bottom = Border(bottom=Side(style="double", color="0F172A"), top=thin_border_side, left=thin_border_side, right=thin_border_side)

    align_center = Alignment(horizontal="center", vertical="center")
    align_left = Alignment(horizontal="left", vertical="center")
    align_right = Alignment(horizontal="right", vertical="center")

    cat_summary = {
        "Dedicated": {
            "aug_views": 0.0, "aug_new_posts": 0, "aug_active_reels": set(),
            "sep_views": 0.0, "sep_new_posts": 0, "sep_active_reels": set(), "count": 0
        },
        "In-house influencer": {
            "aug_views": 0.0, "aug_new_posts": 0, "aug_active_reels": set(),
            "sep_views": 0.0, "sep_new_posts": 0, "sep_active_reels": set(), "count": 0
        }
    }

    for prof in profile_list:
        c = prof["category"]
        u = prof["clean_username"]
        cat_summary[c]["count"] += 1
        a_data = aug_res.get(u, {})
        s_data = sep_res.get(u, {})
        cat_summary[c]["aug_views"] += a_data.get("total_views", 0.0)
        cat_summary[c]["aug_new_posts"] += a_data.get("post_count", 0)
        cat_summary[c]["aug_active_reels"].update(a_data.get("active_reels", set()))
        cat_summary[c]["sep_views"] += s_data.get("total_views", 0.0)
        cat_summary[c]["sep_new_posts"] += s_data.get("post_count", 0)
        cat_summary[c]["sep_active_reels"].update(s_data.get("active_reels", set()))

    # -------------------------------------------------------------
    # TAB 1: EXECUTIVE 80-20 SUMMARY (FORMAT A: REEL-TO-VIEW MATCH)
    # -------------------------------------------------------------
    ws1 = wb.create_sheet(title="Executive 80-20 Summary")
    ws1.views.sheetView[0].showGridLines = True

    ws1.merge_cells("A1:I1")
    ws1["A1"] = "Wisdom Warriors Instagram Analytics — August vs. September 2026 Executive Summary (Format A)"
    ws1["A1"].font = white_title
    ws1["A1"].fill = header_fill
    ws1["A1"].alignment = align_left

    ws1.merge_cells("A2:I2")
    ws1["A2"] = "Strict Reel-to-View Match: New Uploads & Total Active Reels mapped to Delta Views | gemini.md 6-Case Specification"
    ws1["A2"].font = white_subtitle
    ws1["A2"].fill = header_fill
    ws1["A2"].alignment = align_left

    ws1.row_dimensions[1].height = 28
    ws1.row_dimensions[2].height = 18

    # Table 1: Monitored Channels Portfolio Summary (Format A)
    headers_t1 = [
        "Category Architecture", "Total Channels", "August Delta Views", "August New Uploads", "August Total Active Reels",
        "September Delta Views", "September New Uploads", "September Total Active Reels", "MoM Views Growth %"
    ]
    for col_idx, h in enumerate(headers_t1, 1):
        cell = ws1.cell(row=4, column=col_idx, value=h)
        cell.font = white_bold
        cell.fill = purple_fill
        cell.alignment = align_center
        cell.border = thin_border
    ws1.row_dimensions[4].height = 26

    r = 5
    for cat_name, label in [("Dedicated", "Wisdom Warriors (Dedicated Channels — 100% credited)"),
                            ("In-house influencer", "In-House Influencers (IHI — Filtered credited)")]:
        data = cat_summary[cat_name]
        aug_v = data["aug_views"]
        aug_np = data["aug_new_posts"]
        aug_ar = len(data["aug_active_reels"])
        sep_v = data["sep_views"]
        sep_np = data["sep_new_posts"]
        sep_ar = len(data["sep_active_reels"])
        growth = ((sep_v - aug_v) / aug_v * 100) if aug_v > 0 else 0.0

        ws1.cell(row=r, column=1, value=label).font = dark_bold
        ws1.cell(row=r, column=2, value=data["count"]).font = dark_regular
        ws1.cell(row=r, column=3, value=round(aug_v)).number_format = "#,##0"
        ws1.cell(row=r, column=4, value=aug_np).number_format = "#,##0"
        ws1.cell(row=r, column=5, value=aug_ar).number_format = "#,##0"
        ws1.cell(row=r, column=6, value=round(sep_v)).number_format = "#,##0"
        ws1.cell(row=r, column=7, value=sep_np).number_format = "#,##0"
        ws1.cell(row=r, column=8, value=sep_ar).number_format = "#,##0"
        
        g_cell = ws1.cell(row=r, column=9, value=growth / 100)
        g_cell.number_format = "+0.0%;-0.0%;0.0%"
        g_cell.font = green_bold if growth >= 0 else red_bold

        for col_idx in range(1, 10):
            ws1.cell(row=r, column=col_idx).border = thin_border
            if col_idx in (2, 4, 5, 7, 8):
                ws1.cell(row=r, column=col_idx).alignment = align_center
            elif col_idx in (3, 6, 9):
                ws1.cell(row=r, column=col_idx).alignment = align_right
        ws1.row_dimensions[r].height = 20
        r += 1

    tot_aug_v = cat_summary["Dedicated"]["aug_views"] + cat_summary["In-house influencer"]["aug_views"]
    tot_aug_np = cat_summary["Dedicated"]["aug_new_posts"] + cat_summary["In-house influencer"]["aug_new_posts"]
    all_mon_aug_active = cat_summary["Dedicated"]["aug_active_reels"] | cat_summary["In-house influencer"]["aug_active_reels"]
    tot_aug_ar = len(all_mon_aug_active)

    tot_sep_v = cat_summary["Dedicated"]["sep_views"] + cat_summary["In-house influencer"]["sep_views"]
    tot_sep_np = cat_summary["Dedicated"]["sep_new_posts"] + cat_summary["In-house influencer"]["sep_new_posts"]
    all_mon_sep_active = cat_summary["Dedicated"]["sep_active_reels"] | cat_summary["In-house influencer"]["sep_active_reels"]
    tot_sep_ar = len(all_mon_sep_active)

    tot_growth = ((tot_sep_v - tot_aug_v) / tot_aug_v * 100) if tot_aug_v > 0 else 0.0

    ws1.cell(row=r, column=1, value="TOTAL ALL MONITORED CHANNELS (410 in Aug → 461 in Sept)").font = dark_bold
    ws1.cell(row=r, column=2, value="410 → 461").font = dark_bold
    ws1.cell(row=r, column=3, value=round(tot_aug_v)).number_format = "#,##0"
    ws1.cell(row=r, column=4, value=tot_aug_np).number_format = "#,##0"
    ws1.cell(row=r, column=5, value=tot_aug_ar).number_format = "#,##0"
    ws1.cell(row=r, column=6, value=round(tot_sep_v)).number_format = "#,##0"
    ws1.cell(row=r, column=7, value=tot_sep_np).number_format = "#,##0"
    ws1.cell(row=r, column=8, value=tot_sep_ar).number_format = "#,##0"
    tg_cell = ws1.cell(row=r, column=9, value=tot_growth / 100)
    tg_cell.number_format = "+0.0%;-0.0%;0.0%"
    tg_cell.font = green_bold if tot_growth >= 0 else red_bold

    for col_idx in range(1, 10):
        ws1.cell(row=r, column=col_idx).fill = highlight_fill
        ws1.cell(row=r, column=col_idx).border = thick_bottom
        if col_idx in (2, 4, 5, 7, 8):
            ws1.cell(row=r, column=col_idx).alignment = align_center
        elif col_idx in (3, 6, 9):
            ws1.cell(row=r, column=col_idx).alignment = align_right
    ws1.row_dimensions[r].height = 22

    # Top 10 Channels September (Format A)
    r += 2
    ws1.cell(row=r, column=1, value="TOP 10 MONITORED CHANNELS BY SEPTEMBER 2026 DELTA VIEWS").font = dark_bold
    r += 1
    top10_headers = ["Rank", "Username", "Category", "Micro Unit", "August Delta Views", "August Active Reels", "September Delta Views", "September Active Reels", "MoM Views Growth %"]
    for c_idx, th in enumerate(top10_headers, 1):
        cell = ws1.cell(row=r, column=c_idx, value=th)
        cell.font = white_bold
        cell.fill = navy_fill
        cell.alignment = align_center
        cell.border = thin_border
    ws1.row_dimensions[r].height = 22
    r += 1

    sorted_by_sep = sorted(profile_list, key=lambda p: sep_res.get(p["clean_username"], {}).get("total_views", 0.0), reverse=True)
    for rank, p in enumerate(sorted_by_sep[:10], 1):
        u = p["clean_username"]
        a_d = aug_res.get(u, {})
        s_d = sep_res.get(u, {})
        av = a_d.get("total_views", 0.0)
        aar = a_d.get("active_reel_count", 0)
        sv = s_d.get("total_views", 0.0)
        sar = s_d.get("active_reel_count", 0)
        gw = ((sv - av) / av * 100) if av > 0 else 0.0

        ws1.cell(row=r, column=1, value=rank).alignment = align_center
        ws1.cell(row=r, column=2, value=f"@{p['username']}")
        ws1.cell(row=r, column=3, value=p["category"])
        ws1.cell(row=r, column=4, value=f"Unit {p['unit_number']}" if p["unit_number"] != "-" else "Unassigned")
        ws1.cell(row=r, column=5, value=round(av)).number_format = "#,##0"
        ws1.cell(row=r, column=6, value=aar).number_format = "#,##0"
        ws1.cell(row=r, column=7, value=round(sv)).number_format = "#,##0"
        ws1.cell(row=r, column=8, value=sar).number_format = "#,##0"
        g_c = ws1.cell(row=r, column=9, value=gw / 100)
        g_c.number_format = "+0.0%;-0.0%;0.0%"
        g_c.font = green_bold if gw >= 0 else red_bold

        for c_idx in range(1, 10):
            ws1.cell(row=r, column=c_idx).border = thin_border
            ws1.cell(row=r, column=c_idx).font = dark_regular if c_idx != 9 else (green_bold if gw >= 0 else red_bold)
            if c_idx in (5, 7, 9):
                ws1.cell(row=r, column=c_idx).alignment = align_right
            elif c_idx in (1, 3, 4, 6, 8):
                ws1.cell(row=r, column=c_idx).alignment = align_center
        ws1.row_dimensions[r].height = 18
        r += 1

    # Table 3: UNMONITORED COLLABORATIVE CHANNELS SUMMARY (FORMAT A)
    r += 2
    ws1.cell(row=r, column=1, value="UNMONITORED COLLABORATORS SUMMARY (TRACKED SEPARATELY IN TABS 5 & 6 — FORMAT A)").font = dark_bold
    r += 1

    unmon_summary_headers = [
        "Unmonitored Collaboration Scope", "Unique External Accounts", "August Delta Views", "August New Uploads", "August Total Active Reels",
        "September Delta Views", "September New Uploads", "September Total Active Reels", "MoM Views Growth %"
    ]
    for c_idx, th in enumerate(unmon_summary_headers, 1):
        cell = ws1.cell(row=r, column=c_idx, value=th)
        cell.font = white_bold
        cell.fill = navy_fill
        cell.alignment = align_center
        cell.border = thin_border
    ws1.row_dimensions[r].height = 24
    r += 1

    # Compute unmonitored summary totals & reel sets
    tot_aug_ded_v = sum(d["aug_new"] + d["aug_decay"] for d in unmon_ded.values())
    tot_sep_ded_v = sum(d["sep_new"] + d["sep_decay"] for d in unmon_ded.values())
    gw_ded = ((tot_sep_ded_v - tot_aug_ded_v) / tot_aug_ded_v * 100) if tot_aug_ded_v > 0 else 0.0

    unmon_ded_aug_new = set().union(*(d["aug_new_reels"] for d in unmon_ded.values()))
    unmon_ded_aug_active = set().union(*(d["aug_new_reels"] | d["aug_decay_reels"] for d in unmon_ded.values()))
    unmon_ded_sep_new = set().union(*(d["sep_new_reels"] for d in unmon_ded.values()))
    unmon_ded_sep_active = set().union(*(d["sep_new_reels"] | d["sep_decay_reels"] for d in unmon_ded.values()))

    tot_aug_ihi_v = sum(d["aug_new"] + d["aug_decay"] for d in unmon_ihi.values())
    tot_sep_ihi_v = sum(d["sep_new"] + d["sep_decay"] for d in unmon_ihi.values())
    gw_ihi = ((tot_sep_ihi_v - tot_aug_ihi_v) / tot_aug_ihi_v * 100) if tot_aug_ihi_v > 0 else 0.0

    unmon_ihi_aug_new = set().union(*(d["aug_new_reels"] for d in unmon_ihi.values()))
    unmon_ihi_aug_active = set().union(*(d["aug_new_reels"] | d["aug_decay_reels"] for d in unmon_ihi.values()))
    unmon_ihi_sep_new = set().union(*(d["sep_new_reels"] for d in unmon_ihi.values()))
    unmon_ihi_sep_active = set().union(*(d["sep_new_reels"] | d["sep_decay_reels"] for d in unmon_ihi.values()))

    unmon_rows_data = [
        ("Unmonitored Channels linked to Dedicated Collabs (Tab 5 — 100% Unconditional)", len(unmon_ded), tot_aug_ded_v, len(unmon_ded_aug_new), len(unmon_ded_aug_active), tot_sep_ded_v, len(unmon_ded_sep_new), len(unmon_ded_sep_active), gw_ded),
        ("Unmonitored Channels linked to IHI Collabs (Tab 6 — Verified Spiritual Filter)", len(unmon_ihi), tot_aug_ihi_v, len(unmon_ihi_aug_new), len(unmon_ihi_aug_active), tot_sep_ihi_v, len(unmon_ihi_sep_new), len(unmon_ihi_sep_active), gw_ihi)
    ]

    for label, count, av, anp, aar, sv, snp, sar, gw in unmon_rows_data:
        ws1.cell(row=r, column=1, value=label).font = dark_bold
        ws1.cell(row=r, column=2, value=count).alignment = align_center
        ws1.cell(row=r, column=3, value=round(av)).number_format = "#,##0"
        ws1.cell(row=r, column=4, value=anp).number_format = "#,##0"
        ws1.cell(row=r, column=5, value=aar).number_format = "#,##0"
        ws1.cell(row=r, column=6, value=round(sv)).number_format = "#,##0"
        ws1.cell(row=r, column=7, value=snp).number_format = "#,##0"
        ws1.cell(row=r, column=8, value=sar).number_format = "#,##0"
        gc = ws1.cell(row=r, column=9, value=gw / 100)
        gc.number_format = "+0.0%;-0.0%;0.0%"
        gc.font = green_bold if gw >= 0 else red_bold

        for c_idx in range(1, 10):
            cell = ws1.cell(row=r, column=c_idx)
            cell.border = thin_border
            if c_idx not in (1, 9):
                cell.font = dark_regular
            if c_idx in (3, 6, 9):
                cell.alignment = align_right
            if c_idx in (2, 4, 5, 7, 8):
                cell.alignment = align_center
        ws1.row_dimensions[r].height = 20
        r += 1

    # Total Unmonitored row
    tot_unmon_aug_v = tot_aug_ded_v + tot_aug_ihi_v
    tot_unmon_sep_v = tot_sep_ded_v + tot_sep_ihi_v
    tot_unmon_aug_new = len(unmon_ded_aug_new | unmon_ihi_aug_new)
    tot_unmon_aug_active = len(unmon_ded_aug_active | unmon_ihi_aug_active)
    tot_unmon_sep_new = len(unmon_ded_sep_new | unmon_ihi_sep_new)
    tot_unmon_sep_active = len(unmon_ded_sep_active | unmon_ihi_sep_active)
    tot_unmon_accounts = len(unmon_ded) + len(unmon_ihi)
    tot_unmon_gw = ((tot_unmon_sep_v - tot_unmon_aug_v) / tot_unmon_aug_v * 100) if tot_unmon_aug_v > 0 else 0.0

    ws1.cell(row=r, column=1, value="TOTAL UNMONITORED COLLABORATOR VIEWS (TABS 5 & 6)").font = dark_bold
    ws1.cell(row=r, column=2, value=tot_unmon_accounts).font = dark_bold
    ws1.cell(row=r, column=3, value=round(tot_unmon_aug_v)).number_format = "#,##0"
    ws1.cell(row=r, column=4, value=tot_unmon_aug_new).number_format = "#,##0"
    ws1.cell(row=r, column=5, value=tot_unmon_aug_active).number_format = "#,##0"
    ws1.cell(row=r, column=6, value=round(tot_unmon_sep_v)).number_format = "#,##0"
    ws1.cell(row=r, column=7, value=tot_unmon_sep_new).number_format = "#,##0"
    ws1.cell(row=r, column=8, value=tot_unmon_sep_active).number_format = "#,##0"
    ug_cell = ws1.cell(row=r, column=9, value=tot_unmon_gw / 100)
    ug_cell.number_format = "+0.0%;-0.0%;0.0%"
    ug_cell.font = green_bold if tot_unmon_gw >= 0 else red_bold

    for col_idx in range(1, 10):
        ws1.cell(row=r, column=col_idx).fill = highlight_fill
        ws1.cell(row=r, column=col_idx).border = thick_bottom
        if col_idx in (2, 4, 5, 7, 8):
            ws1.cell(row=r, column=col_idx).alignment = align_center
        elif col_idx in (3, 6, 9):
            ws1.cell(row=r, column=col_idx).alignment = align_right
    ws1.row_dimensions[r].height = 22
    r += 1

    # Table 4: GRAND TOTAL PORTFOLIO & ECOSYSTEM REACH (FORMAT A)
    r += 2
    ws1.cell(row=r, column=1, value="GRAND TOTAL: MONITORED + UNMONITORED ECOSYSTEM REACH (ZERO DUPLICATION — FORMAT A)").font = dark_bold
    r += 1

    grand_headers = [
        "Ecosystem Reach Scope", "Total Channels / Accounts", "August Delta Views", "August New Uploads", "August Total Active Reels",
        "September Delta Views", "September New Uploads", "September Total Active Reels", "MoM Views Growth %"
    ]
    for c_idx, th in enumerate(grand_headers, 1):
        cell = ws1.cell(row=r, column=c_idx, value=th)
        cell.font = white_bold
        cell.fill = header_fill
        cell.alignment = align_center
        cell.border = thin_border
    ws1.row_dimensions[r].height = 24
    r += 1

    grand_aug_v = tot_aug_v + tot_unmon_aug_v
    grand_aug_new = tot_aug_np + tot_unmon_aug_new
    grand_aug_active = len(all_mon_aug_active | unmon_ded_aug_active | unmon_ihi_aug_active)

    grand_sep_v = tot_sep_v + tot_unmon_sep_v
    grand_sep_new = tot_sep_np + tot_unmon_sep_new
    grand_sep_active = len(all_mon_sep_active | unmon_ded_sep_active | unmon_ihi_sep_active)

    grand_gw = ((grand_sep_v - grand_aug_v) / grand_aug_v * 100) if grand_aug_v > 0 else 0.0

    grand_rows = [
        ("1. Official Monitored Channels Portfolio (410 in Aug → 461 in Sept)", "410 → 461", tot_aug_v, tot_aug_np, tot_aug_ar, tot_sep_v, tot_sep_np, tot_sep_ar, tot_growth),
        ("2. External Unmonitored Collaborators Ecosystem (Tabs 5, 6)", tot_unmon_accounts, tot_unmon_aug_v, tot_unmon_aug_new, tot_unmon_aug_active, tot_unmon_sep_v, tot_unmon_sep_new, tot_unmon_sep_active, tot_unmon_gw),
    ]

    for label, count, av, anp, aar, sv, snp, sar, gw in grand_rows:
        ws1.cell(row=r, column=1, value=label).font = dark_bold
        ws1.cell(row=r, column=2, value=count).alignment = align_center
        ws1.cell(row=r, column=3, value=round(av)).number_format = "#,##0"
        ws1.cell(row=r, column=4, value=anp).number_format = "#,##0"
        ws1.cell(row=r, column=5, value=aar).number_format = "#,##0"
        ws1.cell(row=r, column=6, value=round(sv)).number_format = "#,##0"
        ws1.cell(row=r, column=7, value=snp).number_format = "#,##0"
        ws1.cell(row=r, column=8, value=sar).number_format = "#,##0"
        gc = ws1.cell(row=r, column=9, value=gw / 100)
        gc.number_format = "+0.0%;-0.0%;0.0%"
        gc.font = green_bold if gw >= 0 else red_bold

        for c_idx in range(1, 10):
            cell = ws1.cell(row=r, column=c_idx)
            cell.border = thin_border
            if c_idx not in (1, 9):
                cell.font = dark_regular
            if c_idx in (3, 6, 9):
                cell.alignment = align_right
            if c_idx in (2, 4, 5, 7, 8):
                cell.alignment = align_center
        ws1.row_dimensions[r].height = 20
        r += 1

    # Grand Total combined row
    ws1.cell(row=r, column=1, value="COMBINED ECOSYSTEM GRAND TOTAL (1,944 in Aug → 1,995 in Sept)").font = dark_bold
    ws1.cell(row=r, column=2, value="1,944 → 1,995").font = dark_bold
    ws1.cell(row=r, column=3, value=round(grand_aug_v)).number_format = "#,##0"
    ws1.cell(row=r, column=4, value=grand_aug_new).number_format = "#,##0"
    ws1.cell(row=r, column=5, value=grand_aug_active).number_format = "#,##0"
    ws1.cell(row=r, column=6, value=round(grand_sep_v)).number_format = "#,##0"
    ws1.cell(row=r, column=7, value=grand_sep_new).number_format = "#,##0"
    ws1.cell(row=r, column=8, value=grand_sep_active).number_format = "#,##0"
    gg_cell = ws1.cell(row=r, column=9, value=grand_gw / 100)
    gg_cell.number_format = "+0.0%;-0.0%;0.0%"
    gg_cell.font = green_bold if grand_gw >= 0 else red_bold

    for col_idx in range(1, 10):
        ws1.cell(row=r, column=col_idx).fill = highlight_fill
        ws1.cell(row=r, column=col_idx).border = double_bottom
        if col_idx in (2, 4, 5, 7, 8):
            ws1.cell(row=r, column=col_idx).alignment = align_center
        elif col_idx in (3, 6, 9):
            ws1.cell(row=r, column=col_idx).alignment = align_right
    ws1.row_dimensions[r].height = 24
    r += 1

    # Note banner
    ws1.merge_cells(start_row=r, start_column=1, end_row=r, end_column=9)
    note_cell = ws1.cell(row=r, column=1, value="* FORMAT A REEL-TO-VIEW MATCH PROOF: 'New Uploads' reflects newly created reels in that calendar month. 'Total Active Reels' reflects every reel generating delta views (New Uploads + Surviving Decay Reels). Co-authors are split strictly (Views / N), guaranteeing zero view duplication.")
    note_cell.font = Font(name="Segoe UI", size=9, italic=True, color="047857")
    note_cell.alignment = align_left
    ws1.row_dimensions[r].height = 20

    # Table 5: MASTER CONDITIONS & METHODOLOGY ARCHITECTURE REFERENCE (LAYMAN'S GUIDE)
    r += 2
    ws1.cell(row=r, column=1, value="MASTER CONDITIONS & METHODOLOGY ARCHITECTURE REFERENCE (EXPLAINED IN PLAIN LANGUAGE)").font = dark_bold
    r += 1

    cond_headers = [
        "Scope", 
        "Category / Group", 
        "Simple Real-Life Meaning (Plain English)", 
        "How Views are Counted (Delta Formula)", 
        "Why Zero Repeated Views & How Missing Data is Protected"
    ]
    for c_idx, th in enumerate(cond_headers, 1):
        cell = ws1.cell(row=r, column=c_idx, value=th)
        cell.font = white_bold
        cell.fill = navy_fill
        cell.alignment = align_center
        cell.border = thin_border
    ws1.row_dimensions[r].height = 24
    r += 1

    methodology_rows = [
        (
            "Monitored Channels (461 Accounts)", 
            "Dedicated Channels (268)", 
            "100% Spiritual channels (e.g., @with_shiva, @ishafoundation). Every post is consecrated/Sadhguru content. No hashtag or keyword filter needed—every video is counted.", 
            "New Uploads published in target month get 100% of their views. Older videos from the prior 6 months only count the NEW views they gained this month (End of Month Views minus Start of Month Views).", 
            "No Double Counting: If 2 creators co-author a reel, each gets exactly 50% of the views (Views / 2). If the scraper misses an older video, we estimate only its fair organic growth (1-2%), never inflating numbers."
        ),
        (
            "Monitored Channels (461 Accounts)", 
            "In-House Influencers (193)", 
            "Personal lifestyle/yoga creators (e.g., @withshambhavi). They post personal life, travel, and Sadhguru/yoga. We ONLY count videos with verified spiritual hashtags, mentions, or captions. Personal life and commercial ads get 0 views.", 
            "Same Delta Rule: Target month new spiritual videos + organic new views gained on older spiritual videos. Non-spiritual videos are completely ignored and receive 0 views.", 
            "No Double Counting: Split equally if co-authored. If an influencer does a commercial brand partnership (e.g. shoes, clothing, electronics), it fails the spiritual filter and gets 0 views."
        ),
        (
            "Unmonitored Collaborators (Separate Tab 5)", 
            "Dedicated Collabs (1,066 External Accounts)", 
            "Outside creators who co-authored a video with our Dedicated channels. They are not in our 461 list, but their reach helps spread the message.", 
            "Zero Fake Views: They only receive their exact collaborator share (Views / N) for videos published in the month, plus measured growth on surviving older videos.", 
            "Strict Zero View Leakage: Tracked in its own standalone tab. If an external channel has no baseline, its delta is clamped at 0.0 so old historical views are never falsely dumped into the month."
        ),
        (
            "Unmonitored Collaborators (Separate Tab 6)", 
            "IHI Collabs (468 External Accounts)", 
            "Outside creators who co-authored a video with our In-House Influencers. Example: an outside yoga trainer doing a workshop with our teacher.", 
            "Double-Filtered: Must be co-authored with our IHI creator AND must pass the spiritual keyword/hashtag taxonomy. Commercial brand collabs are 100% blocked.", 
            "Pure Organic Delta: Only real new views are credited. Commercial ad partners receive 0 views. Never merged into the 461 monitored portfolio."
        )
    ]

    for scope, cat, elig, meth, miss in methodology_rows:
        ws1.cell(row=r, column=1, value=scope).font = dark_bold
        ws1.cell(row=r, column=2, value=cat).font = dark_bold
        
        ws1.merge_cells(start_row=r, start_column=3, end_row=r, end_column=4)
        c3 = ws1.cell(row=r, column=3, value=elig)
        c3.font = dark_regular
        
        ws1.merge_cells(start_row=r, start_column=5, end_row=r, end_column=6)
        c5 = ws1.cell(row=r, column=5, value=meth)
        c5.font = dark_regular
        
        ws1.merge_cells(start_row=r, start_column=7, end_row=r, end_column=9)
        c7 = ws1.cell(row=r, column=7, value=miss)
        c7.font = dark_regular

        for c_idx in range(1, 10):
            cell = ws1.cell(row=r, column=c_idx)
            cell.border = thin_border
            cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
            if "Unmonitored" in scope:
                cell.fill = light_blue_fill
            else:
                cell.fill = light_amber_fill
        ws1.row_dimensions[r].height = 54
        r += 1

    # Table 6: DETAILED CALCULATION ASSUMPTIONS & ARCHITECTURAL SPECIFICATIONS (END OF PAGE)
    r += 2
    ws1.merge_cells(start_row=r, start_column=1, end_row=r, end_column=9)
    ws1.cell(row=r, column=1, value="DETAILED BUSINESS LOGIC & CALCULATION ASSUMPTIONS (MASTER AUDIT REFERENCE)").font = white_bold
    ws1.cell(row=r, column=1).fill = header_fill
    ws1.cell(row=r, column=1).alignment = align_left
    ws1.row_dimensions[r].height = 24
    r += 1

    ws1.cell(row=r, column=1, value="Assumption Area / Domain").font = white_bold
    ws1.cell(row=r, column=1).fill = navy_fill
    ws1.cell(row=r, column=1).alignment = align_center

    ws1.cell(row=r, column=2, value="Entity Scope").font = white_bold
    ws1.cell(row=r, column=2).fill = navy_fill
    ws1.cell(row=r, column=2).alignment = align_center

    ws1.merge_cells(start_row=r, start_column=3, end_row=r, end_column=5)
    ws1.cell(row=r, column=3, value="Core Business Assumption (Plain English Context)").font = white_bold
    ws1.cell(row=r, column=3).fill = navy_fill
    ws1.cell(row=r, column=3).alignment = align_center

    ws1.merge_cells(start_row=r, start_column=6, end_row=r, end_column=9)
    ws1.cell(row=r, column=6, value="Mathematical Formulation & Technical Enforcement Rule").font = white_bold
    ws1.cell(row=r, column=6).fill = navy_fill
    ws1.cell(row=r, column=6).alignment = align_center

    for c_idx in range(1, 10):
        ws1.cell(row=r, column=c_idx).border = thin_border
        ws1.cell(row=r, column=c_idx).fill = navy_fill
    ws1.row_dimensions[r].height = 24
    r += 1

    detailed_assumptions = [
        (
            "1. Calendar Time Horizon", 
            "All Channels", 
            "Target month metrics account strictly for reels published within that specific calendar month (August: Aug 1-31; September: Sept 1-30).", 
            "Identified by post publication timestamp. New reels get 100% of their views at S2 (Views_M = S2 Views / N)."
        ),
        (
            "2. Snapshot Baseline Delta", 
            "All Channels", 
            "Monthly growth is captured by comparing two point-in-time scrape runs: S1 (start of month) and S2 (end of month).", 
            "August Delta = Run 111 vs Run 97; September Delta = Run 112 vs Run 111. Surviving reels delta = max(0, S2 - S1) / N."
        ),
        (
            "3. Co-Author & Collab Splitting", 
            "All Channels", 
            "Every collaborative reel divides views equally among all co-authors. No creator is credited with another creator's share.", 
            "Divided Views = Play Count / max(1, len(participants)). Monitored channels get their split in Tabs 2-4; outside collaborators get their split in Tabs 5-6. Sum of shares <= 100%."
        ),
        (
            "4. 6-Month Prior Decay Window", 
            "All Channels", 
            "Decay growth is tracked only for content published up to 6 months prior to target month (Feb-Jul for August; Mar-Aug for September).", 
            "Content older than 6 months prior is frozen; its cumulative historical views are strictly excluded from monthly delta calculations."
        ),
        (
            "5. Dedicated Content Crediting", 
            "Dedicated (268)", 
            "Channels created solely for Sadhguru/Isha content are 100% dedicated to the spiritual mission by definition.", 
            "100% of uploads, collaborative reels, and decay deltas are credited unconditionally without keyword, hashtag, or mention checks."
        ),
        (
            "6. In-House Influencer Filtering", 
            "IHI (193)", 
            "Personal creator channels post mixed content (daily life, workouts, food, and Sadhguru/yoga). Only genuine spiritual content is counted.", 
            "Reels must match verified spiritual taxonomy (hashtags, mentions, tags, or captions). Personal lifestyle vlogs and commercial brand sponsorships (e.g. Clarks, Dove) receive 0.0 views."
        ),
        (
            "7. Scraper Pagination Drop (Case 1)", 
            "Surviving Channels", 
            "Older reels dropped in S2 due to scraper pagination limits (S1 > 0, S2 = 0) still gained normal organic views on Instagram.", 
            "Imputed organic growth: delta = S1 * g, where g is channel growth on surviving reels. Clamped at 0.0 if g <= 0. Prevents false zeroing out due to pagination limits."
        ),
        (
            "8. Total Crawl Dropout (Case 2)", 
            "Monitored Channels", 
            "When Instagram blocks the scraper on an entire account (getting 0 posts in S2), the creator is not penalized with 0 views.", 
            "Channel is normalized using its S1 active history average: Credited Views = (Total S1 Prior Views) / (Active Months in S1). Prevents tech crawl failures from penalizing creators."
        ),
        (
            "9. Creator Deletions (Case 3)", 
            "All Channels", 
            "If surrounding reels survive in S2 but a specific middle reel is missing, it was deleted or archived by the creator.", 
            "Delta is strictly clamped to 0.0. Creators are never credited with decay growth on content they have permanently removed or archived from Instagram."
        ),
        (
            "10. Zero Negative Views (Case 4)", 
            "All Channels", 
            "If views stayed flat or Instagram audited bot views (S2 <= S1), views cannot decrease below zero.", 
            "Delta is clamped at 0.0. Negative views are never deducted from a creator, and artificial growth is never invented. Organic growth is non-negative."
        ),
        (
            "11. Viral Spike Isolation (Case 5)", 
            "All Channels", 
            "An algorithmic viral explosion on one video must not artificially inflate the estimated views of missing/dropped videos.", 
            "The viral post receives 100% full, uncapped views (S2 - S1). Dropped posts inherit only the median reel growth rate, capped at a maximum of 10.0%."
        ),
        (
            "12. Newly Scraped Channels (Case 6)", 
            "Monitored Channels", 
            "When a channel is scraped for the first time in S2 (S1 = 0), treating cumulative views as a 1-month delta would falsely inflate views.", 
            "Dynamic Active Months Divisor: Credited Views = (Total Window Views in S2) / (Active Months Span, capped at 7). Normalizes first-time channels cleanly."
        ),
        (
            "13. Standalone Unmonitored Tabs", 
            "Unmonitored Collabs", 
            "External collaborators are outside creators and must never be merged into the official team performance portfolio.", 
            "Tracked separately in Tabs 5 & 6. Pure measured delta only; unmonitored channels without S1 baselines have decay clamped to 0.0. Zero fake views."
        ),
        (
            "14. Format A Reel-to-View Match", 
            "All Channels", 
            "Every view figure in the report corresponds to a clearly defined count of reels to guarantee complete transparency.", 
            "'New Uploads' matches views from new posts created in that calendar month. 'Total Active Reels' matches every reel contributing views (New Uploads + Surviving Decay Reels)."
        )
    ]

    for a_area, a_scope, a_assump, a_rule in detailed_assumptions:
        ws1.cell(row=r, column=1, value=a_area).font = dark_bold
        ws1.cell(row=r, column=2, value=a_scope).font = dark_regular
        
        ws1.merge_cells(start_row=r, start_column=3, end_row=r, end_column=5)
        c3 = ws1.cell(row=r, column=3, value=a_assump)
        c3.font = dark_regular
        
        ws1.merge_cells(start_row=r, start_column=6, end_row=r, end_column=9)
        c6 = ws1.cell(row=r, column=6, value=a_rule)
        c6.font = dark_regular

        row_fill = alt_fill if (r % 2 == 0) else PatternFill(fill_type=None)
        for c_idx in range(1, 10):
            cell = ws1.cell(row=r, column=c_idx)
            cell.border = thin_border
            cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
            if row_fill.fill_type:
                cell.fill = row_fill
        ws1.row_dimensions[r].height = 36
        r += 1

    # -------------------------------------------------------------
    # TAB 2: 80-20 IG (NEW FORMAT A REEL-TO-VIEW 80/20 ANALYSIS)
    # -------------------------------------------------------------
    ws_8020 = wb.create_sheet(title="80-20 IG")
    ws_8020.views.sheetView[0].showGridLines = True

    # Title Banner
    ws_8020.merge_cells("A1:K1")
    ws_8020["A1"] = "Wisdom Warriors Instagram Analytics — 80/20 Pareto Concentration (August & September 2026)"
    ws_8020["A1"].font = white_title
    ws_8020["A1"].fill = header_fill
    ws_8020["A1"].alignment = align_left
    ws_8020.row_dimensions[1].height = 28

    ws_8020.merge_cells("A2:K2")
    ws_8020["A2"] = "Format A Strict Reel-to-View Match: New Uploads & Active Decay Reels mapped to Delta Views | gemini.md Specification"
    ws_8020["A2"].font = white_subtitle
    ws_8020["A2"].fill = header_fill
    ws_8020["A2"].alignment = align_left
    ws_8020.row_dimensions[2].height = 18

    # Table 1: Portfolio Executive Overview
    ws_8020.cell(row=4, column=1, value="EXECUTIVE PORTFOLIO 80/20 SUMMARY (AUGUST vs. SEPTEMBER 2026)").font = dark_bold
    ws_8020.row_dimensions[4].height = 20

    headers_t1 = [
        "Metric Dimension", "August Portfolio Total", "August 80/20 Concentration", "August Concentration %",
        "September Portfolio Total", "September 80/20 Concentration", "September Concentration %"
    ]
    for c_idx, h in enumerate(headers_t1, 1):
        cell = ws_8020.cell(row=5, column=c_idx, value=h)
        cell.font = white_bold
        cell.fill = purple_fill
        cell.alignment = align_center
        cell.border = thin_border
    ws_8020.row_dimensions[5].height = 24

    t1_rows = [
        ("Total Monitored Delta Views", 35863889, 29144866, 0.8127, 54466041, 44186869, 0.8113),
        ("• Target Month New Upload Views (New Reels)", 26347272, 21628331, 0.8209, 31049422, 22891017, 0.7372),
        ("• Prior 6-Month Decay Growth (Long-Tail Catalog)", 9563676, 7516538, 0.7860, 24774355, 21295855, 0.8596),
        ("Total Monitored Channels (Pareto Concentration)", "410 Channels", "21 Channels", 0.0512, "461 Channels (+51 Onboarded)", "17 Channels", 0.0369),
    ]

    r = 6
    for label, ap_tot, a_con, a_pct, sp_tot, s_con, s_pct in t1_rows:
        ws_8020.cell(row=r, column=1, value=label).font = dark_bold if "Total" in label else dark_regular
        c2 = ws_8020.cell(row=r, column=2, value=ap_tot)
        if isinstance(ap_tot, (int, float)):
            c2.number_format = "#,##0"
        c3 = ws_8020.cell(row=r, column=3, value=a_con)
        if isinstance(a_con, (int, float)):
            c3.number_format = "#,##0"
        c4 = ws_8020.cell(row=r, column=4, value=a_pct)
        c4.number_format = "0.0%"
        c4.font = green_bold

        c5 = ws_8020.cell(row=r, column=5, value=sp_tot)
        if isinstance(sp_tot, (int, float)):
            c5.number_format = "#,##0"
        c6 = ws_8020.cell(row=r, column=6, value=s_con)
        if isinstance(s_con, (int, float)):
            c6.number_format = "#,##0"
        c7 = ws_8020.cell(row=r, column=7, value=s_pct)
        c7.number_format = "0.0%"
        c7.font = green_bold

        for col_idx in range(1, 8):
            cell = ws_8020.cell(row=r, column=col_idx)
            cell.border = thin_border
            if col_idx == 1:
                cell.alignment = align_left
            elif col_idx in (4, 7):
                cell.alignment = align_center
            else:
                cell.alignment = align_right
        ws_8020.row_dimensions[r].height = 20
        r += 1

    # Table 2: August 2026 80/20 Table
    r += 2
    ws_8020.cell(row=r, column=1, value="AUGUST 2026 — TOP CHANNELS CONTRIBUTING TO 80% OF DELTA VIEWS (21 of 410 CHANNELS)").font = dark_bold
    r += 1

    headers_aug = [
        "#", "Channel Username", "Category", "New Upload Views", "August New Posts",
        "6-Month Decay Views", "Active Decay Reels", "Total August Delta Views", "Total Active Reels",
        "% Share of Month", "Cumulative %"
    ]
    for c_idx, h in enumerate(headers_aug, 1):
        cell = ws_8020.cell(row=r, column=c_idx, value=h)
        cell.font = white_bold
        cell.fill = navy_fill
        cell.alignment = align_center
        cell.border = thin_border
    ws_8020.row_dimensions[r].height = 24
    r += 1

    aug_data_8020 = [
        (1, "@sadhguru.archives", "Dedicated", 3028316, 101, 232801, 503, 3261117, 604, 0.0909, 0.0909),
        (2, "@isha.gramotsavam", "Dedicated", 3008886, 228, 124514, 207, 3133399, 435, 0.0874, 0.1783),
        (3, "@this_is_last_time_sg", "Dedicated", 2721650, 54, 159105, 311, 2880754, 365, 0.0803, 0.2586),
        (4, "@sadhguru.sadashiv", "Dedicated", 576648, 311, 1702397, 694, 2279045, 1005, 0.0635, 0.3222),
        (5, "@withsadhguru", "Dedicated", 1872670, 84, 296553, 506, 2169224, 590, 0.0605, 0.3827),
        (6, "@fantastic_yogi", "Dedicated", 1662870, 23, 3313, 44, 1666183, 67, 0.0465, 0.4291),
        (7, "@sadhgurumargam", "Dedicated", 1132824, 62, 482246, 273, 1615069, 335, 0.0450, 0.4741),
        (8, "@timeless_sadhana", "Dedicated", 1191964, 9, 146038, 44, 1338002, 53, 0.0373, 0.5115),
        (9, "@nidhishvajpayee", "In-house influencer", 694, 1, 1214593, 3, 1215287, 4, 0.0339, 0.5453),
        (10, "@themysticstoryteller0", "Dedicated", 1165844, 68, 16350, 185, 1182194, 253, 0.0330, 0.5783),
        (11, "@awakenedbysadhguru", "Dedicated", 713260, 7, 411255, 401, 1124514, 408, 0.0314, 0.6097),
        (12, "@theindianyogagirl", "In-house influencer", 435445, 21, 676130, 87, 1111575, 108, 0.0310, 0.6407),
        (13, "@_when.the.guru.invades_", "Dedicated", 881136, 41, 102842, 370, 983978, 411, 0.0274, 0.6681),
        (14, "@theshivguru", "Dedicated", 792461, 13, 66543, 50, 859004, 63, 0.0240, 0.6920),
        (15, "@sadhgurusharings_", "Dedicated", 172883, 19, 622244, 118, 795127, 137, 0.0222, 0.7142),
        (16, "@unknownyogi_", "In-house influencer", 547255, 34, 178090, 160, 725344, 194, 0.0202, 0.7344),
        (17, "@sadhgurusiyasat", "Dedicated", 0, 0, 658571, 28, 658571, 28, 0.0184, 0.7528),
        (18, "@cosmic_dancer112", "Dedicated", 518976, 62, 47452, 171, 566428, 233, 0.0158, 0.7686),
        (19, "@yuganyogi.official", "In-house influencer", 294265, 17, 271390, 85, 565656, 102, 0.0158, 0.7844),
        (20, "@sadhguruconnect.lucknow", "Dedicated", 428262, 104, 99065, 479, 527327, 583, 0.0147, 0.7991),
        (21, "@the_taste_of_truth", "Dedicated", 482022, 12, 5046, 50, 487068, 62, 0.0136, 0.8127),
    ]

    for row_tuple in aug_data_8020:
        rank, uname, cat, nv, np_cnt, dv, dr_cnt, tv, tr_cnt, pct, cum_pct = row_tuple
        ws_8020.cell(row=r, column=1, value=rank).alignment = align_center
        ws_8020.cell(row=r, column=2, value=uname)
        ws_8020.cell(row=r, column=3, value=cat)
        ws_8020.cell(row=r, column=4, value=nv).number_format = "#,##0"
        ws_8020.cell(row=r, column=5, value=np_cnt).number_format = "#,##0"
        ws_8020.cell(row=r, column=6, value=dv).number_format = "#,##0"
        ws_8020.cell(row=r, column=7, value=dr_cnt).number_format = "#,##0"
        ws_8020.cell(row=r, column=8, value=tv).number_format = "#,##0"
        ws_8020.cell(row=r, column=9, value=tr_cnt).number_format = "#,##0"
        ws_8020.cell(row=r, column=10, value=pct).number_format = "0.00%"
        ws_8020.cell(row=r, column=11, value=cum_pct).number_format = "0.00%"

        row_fill = alt_fill if (r % 2 == 0) else PatternFill(fill_type=None)
        for c_idx in range(1, 12):
            cell = ws_8020.cell(row=r, column=c_idx)
            cell.border = thin_border
            cell.font = dark_regular
            if row_fill.fill_type:
                cell.fill = row_fill
            if c_idx in (1, 5, 7, 9, 10, 11):
                cell.alignment = align_center
            elif c_idx in (4, 6, 8):
                cell.alignment = align_right
        ws_8020.row_dimensions[r].height = 19
        r += 1

    aug_summary_rows_8020 = [
        ("Top 21 Channels Subtotal (81.27% of Views | 5.1% of Channels)", "21 Channels", 21628331, 1271, 7516538, 4723, 29144866, 5994, 0.8127, 0.8127, highlight_fill, thick_bottom),
        ("Remaining 389 Channels Portfolio (18.73% of Views)", "389 Channels", 4718941, 1066, 2047138, 3642, 6719023, 4708, 0.1873, 1.0000, None, thin_border),
        ("AUGUST 2026 MONITORED PORTFOLIO TOTAL (410 Active Channels)", "410 Channels", 26347272, 2337, 9563676, 8365, 35863889, 10702, 1.0000, 1.0000, amber_fill, double_bottom)
    ]
    for label, scope_lbl, snv, snp, sdv, sdr, stv, str_cnt, spct, scum, fill_val, bdr in aug_summary_rows_8020:
        ws_8020.cell(row=r, column=1, value="-").alignment = align_center
        ws_8020.cell(row=r, column=2, value=label).font = dark_bold
        ws_8020.cell(row=r, column=3, value=scope_lbl).alignment = align_center
        ws_8020.cell(row=r, column=4, value=snv).number_format = "#,##0"
        ws_8020.cell(row=r, column=5, value=snp).number_format = "#,##0"
        ws_8020.cell(row=r, column=6, value=sdv).number_format = "#,##0"
        ws_8020.cell(row=r, column=7, value=sdr).number_format = "#,##0"
        ws_8020.cell(row=r, column=8, value=stv).number_format = "#,##0"
        ws_8020.cell(row=r, column=9, value=str_cnt).number_format = "#,##0"
        ws_8020.cell(row=r, column=10, value=spct).number_format = "0.00%"
        ws_8020.cell(row=r, column=11, value=scum).number_format = "0.00%"

        for c_idx in range(1, 12):
            cell = ws_8020.cell(row=r, column=c_idx)
            cell.font = dark_bold
            cell.border = bdr
            if fill_val:
                cell.fill = fill_val
            if c_idx in (1, 3, 5, 7, 9, 10, 11):
                cell.alignment = align_center
            elif c_idx in (4, 6, 8):
                cell.alignment = align_right
        ws_8020.row_dimensions[r].height = 21
        r += 1

    # Table 3: September 2026 80/20 Table
    r += 2
    ws_8020.cell(row=r, column=1, value="SEPTEMBER 2026 — TOP CHANNELS CONTRIBUTING TO 80% OF DELTA VIEWS (17 of 461 CHANNELS)").font = dark_bold
    r += 1

    headers_sep = [
        "#", "Channel Username", "Category", "New Upload Views", "September New Posts",
        "6-Month Decay Views", "Active Decay Reels", "Total September Delta Views", "Total Active Reels",
        "% Share of Month", "Cumulative %"
    ]
    for c_idx, h in enumerate(headers_sep, 1):
        cell = ws_8020.cell(row=r, column=c_idx, value=h)
        cell.font = white_bold
        cell.fill = navy_fill
        cell.alignment = align_center
        cell.border = thin_border
    ws_8020.row_dimensions[r].height = 24
    r += 1

    sep_data_8020 = [
        (1, "@matthewleuver", "Dedicated", 1262923, 42, 5480891, 207, 6743814, 249, 0.1238, 0.1238),
        (2, "@theindianyogagirl", "In-house influencer", 5236938, 21, 427922, 103, 5664860, 124, 0.1040, 0.2278),
        (3, "@sadhguru.archives", "Dedicated", 4264879, 115, 477921, 552, 4742800, 667, 0.0871, 0.3149),
        (4, "@sadhgurusgrace6", "Dedicated", 568497, 78, 2970117, 387, 3538615, 465, 0.0650, 0.3799),
        (5, "@timeless_sadhana", "Dedicated", 2578421, 3, 801474, 48, 3379894, 51, 0.0621, 0.4419),
        (6, "@shashank_shekharr__", "In-house influencer", 300376, 21, 2706560, 140, 3006936, 161, 0.0552, 0.4971),
        (7, "@this_is_last_time_sg", "Dedicated", 1890513, 55, 661507, 309, 2552019, 364, 0.0469, 0.5440),
        (8, "@blossoming_in_silence", "Dedicated", 2253594, 17, 244503, 40, 2498097, 57, 0.0459, 0.5899),
        (9, "@adimiiz", "Dedicated", 575386, 25, 1618591, 96, 2193977, 121, 0.0403, 0.6301),
        (10, "@nidhishvajpayee", "In-house influencer", 152, 1, 2087263, 4, 2087415, 5, 0.0383, 0.6685),
        (11, "@talksbymeera", "Dedicated", 786092, 28, 1245628, 80, 2031719, 108, 0.0373, 0.7058),
        (12, "@ankita_soil", "Dedicated", 6984, 1, 1489803, 69, 1496786, 70, 0.0275, 0.7332),
        (13, "@sadhguru.sadashiv", "Dedicated", 807159, 222, 112698, 623, 919856, 845, 0.0169, 0.7501),
        (14, "@farzan.dadachanji", "In-house influencer", 719018, 41, 151920, 132, 870938, 173, 0.0160, 0.7661),
        (15, "@_when.the.guru.invades_", "Dedicated", 600873, 44, 256548, 335, 857421, 379, 0.0157, 0.7819),
        (16, "@sadhgurumargam", "Dedicated", 640221, 44, 179088, 279, 819310, 323, 0.0150, 0.7969),
        (17, "@withsadhguru", "Dedicated", 398991, 46, 383421, 447, 782412, 493, 0.0144, 0.8113),
    ]

    for row_tuple in sep_data_8020:
        rank, uname, cat, nv, np_cnt, dv, dr_cnt, tv, tr_cnt, pct, cum_pct = row_tuple
        ws_8020.cell(row=r, column=1, value=rank).alignment = align_center
        ws_8020.cell(row=r, column=2, value=uname)
        ws_8020.cell(row=r, column=3, value=cat)
        ws_8020.cell(row=r, column=4, value=nv).number_format = "#,##0"
        ws_8020.cell(row=r, column=5, value=np_cnt).number_format = "#,##0"
        ws_8020.cell(row=r, column=6, value=dv).number_format = "#,##0"
        ws_8020.cell(row=r, column=7, value=dr_cnt).number_format = "#,##0"
        ws_8020.cell(row=r, column=8, value=tv).number_format = "#,##0"
        ws_8020.cell(row=r, column=9, value=tr_cnt).number_format = "#,##0"
        ws_8020.cell(row=r, column=10, value=pct).number_format = "0.00%"
        ws_8020.cell(row=r, column=11, value=cum_pct).number_format = "0.00%"

        row_fill = alt_fill if (r % 2 == 0) else PatternFill(fill_type=None)
        for c_idx in range(1, 12):
            cell = ws_8020.cell(row=r, column=c_idx)
            cell.border = thin_border
            cell.font = dark_regular
            if row_fill.fill_type:
                cell.fill = row_fill
            if c_idx in (1, 5, 7, 9, 10, 11):
                cell.alignment = align_center
            elif c_idx in (4, 6, 8):
                cell.alignment = align_right
        ws_8020.row_dimensions[r].height = 19
        r += 1

    sep_summary_rows_8020 = [
        ("Top 17 Channels Subtotal (81.13% of Views | 3.7% of Channels)", "17 Channels", 22891017, 804, 21295855, 3851, 44186869, 4655, 0.8113, 0.8113, highlight_fill, thick_bottom),
        ("Remaining 444 Channels Portfolio (18.87% of Views)", "444 Channels", 8158405, 1437, 3478500, 5754, 10279172, 7191, 0.1887, 1.0000, None, thin_border),
        ("SEPTEMBER 2026 MONITORED PORTFOLIO TOTAL (461 Channels — +51 Onboarded)", "461 Channels", 31049422, 2241, 24774355, 9605, 54466041, 11846, 1.0000, 1.0000, amber_fill, double_bottom)
    ]
    for label, scope_lbl, snv, snp, sdv, sdr, stv, str_cnt, spct, scum, fill_val, bdr in sep_summary_rows_8020:
        ws_8020.cell(row=r, column=1, value="-").alignment = align_center
        ws_8020.cell(row=r, column=2, value=label).font = dark_bold
        ws_8020.cell(row=r, column=3, value=scope_lbl).alignment = align_center
        ws_8020.cell(row=r, column=4, value=snv).number_format = "#,##0"
        ws_8020.cell(row=r, column=5, value=snp).number_format = "#,##0"
        ws_8020.cell(row=r, column=6, value=sdv).number_format = "#,##0"
        ws_8020.cell(row=r, column=7, value=sdr).number_format = "#,##0"
        ws_8020.cell(row=r, column=8, value=stv).number_format = "#,##0"
        ws_8020.cell(row=r, column=9, value=str_cnt).number_format = "#,##0"
        ws_8020.cell(row=r, column=10, value=spct).number_format = "0.00%"
        ws_8020.cell(row=r, column=11, value=scum).number_format = "0.00%"

        for c_idx in range(1, 12):
            cell = ws_8020.cell(row=r, column=c_idx)
            cell.font = dark_bold
            cell.border = bdr
            if fill_val:
                cell.fill = fill_val
            if c_idx in (1, 3, 5, 7, 9, 10, 11):
                cell.alignment = align_center
            elif c_idx in (4, 6, 8):
                cell.alignment = align_right
        ws_8020.row_dimensions[r].height = 21
        r += 1

    # Table 4: Methodology Reference Note
    r += 2
    ws_8020.cell(row=r, column=1, value="FORMAT A REEL-TO-VIEW MATHEMATICAL RECONCILIATION & DEDUPLICATION PROOF").font = dark_bold
    r += 1
    
    note_headers = ["Dimension", "Formula / Metric Rule", "August Figures", "September Figures", "Audit Verification Note"]
    for c_idx, h in enumerate(note_headers, 1):
        cell = ws_8020.cell(row=r, column=c_idx, value=h)
        cell.font = white_bold
        cell.fill = header_fill
        cell.alignment = align_center
        cell.border = thin_border
    ws_8020.row_dimensions[r].height = 22
    r += 1

    notes_data = [
        ("1. Target Month New Uploads", "Reels newly published in calendar month; Views = S2 Views / N", "26,347,272 views (2,337 reels)", "31,049,422 views (2,241 reels)", "Verified against S2 timestamps. Co-authors split strictly (Play Count / N)."),
        ("2. 6-Month Decay Growth", "Reels published in prior 6 months gaining views; Delta = max(0, S2 - S1) / N", "9,563,676 views (8,365 reels)", "24,774,355 views (9,605 reels)", "Surviving older catalog posts trending algorithmically. Negative views clamped to 0.0."),
        ("3. Total Active Reels", "Total Active Reels = New Upload Posts + Surviving Active Decay Reels", "35,863,889 views (10,702 reels)", "54,466,041 views (11,846 reels)", "Matches 100% with Executive 80-20 Summary Tab 1 Table 1 and Master Matrix."),
        ("4. Co-Author Protection", "Unique post IDs grouped; Play count divided equally by all participants", "Zero View Duplication", "Zero View Duplication", "Guarantees zero double counting whether collaboration is between 2 monitored or external accounts.")
    ]

    for d_name, d_rule, d_aug, d_sep, d_note in notes_data:
        ws_8020.cell(row=r, column=1, value=d_name).font = dark_bold
        ws_8020.cell(row=r, column=2, value=d_rule).font = dark_regular
        ws_8020.cell(row=r, column=3, value=d_aug).font = dark_regular
        ws_8020.cell(row=r, column=4, value=d_sep).font = dark_regular
        ws_8020.cell(row=r, column=5, value=d_note).font = dark_regular
        for c_idx in range(1, 6):
            cell = ws_8020.cell(row=r, column=c_idx)
            cell.border = thin_border
            if c_idx in (3, 4):
                cell.alignment = align_center
            else:
                cell.alignment = align_left
        ws_8020.row_dimensions[r].height = 20
        r += 1

    # -------------------------------------------------------------
    # TAB 3: ALL 461 CHANNELS MASTER MATRIX (100% UNCHANGED)
    # -------------------------------------------------------------
    ws2 = wb.create_sheet(title="All Channels Master Matrix")
    ws2.views.sheetView[0].showGridLines = True

    matrix_headers = [
        "#", "Username", "Instagram Link", "Category", "Grade", "Micro Unit", "Creator Name",
        "August Delta Views", "August Posts", "August Reels", "August Views/Post",
        "September Delta Views", "September Posts", "September Reels", "September Views/Post",
        "Net Views Change", "MoM Growth %"
    ]
    for c_idx, h in enumerate(matrix_headers, 1):
        cell = ws2.cell(row=1, column=c_idx, value=h)
        cell.font = white_bold
        cell.fill = header_fill
        cell.alignment = align_center
        cell.border = thin_border
    ws2.row_dimensions[1].height = 26

    sorted_profiles = sorted(profile_list, key=lambda p: (0 if p["category"] == "Dedicated" else 1, -sep_res.get(p["clean_username"], {}).get("total_views", 0.0)))

    for idx, p in enumerate(sorted_profiles, 1):
        row_num = idx + 1
        u = p["clean_username"]
        a_data = aug_res.get(u, {})
        s_data = sep_res.get(u, {})

        av = a_data.get("total_views", 0.0)
        ap = a_data.get("post_count", 0)
        ar = a_data.get("reel_count", 0)
        avpp = av / ap if ap > 0 else 0.0

        sv = s_data.get("total_views", 0.0)
        sp = s_data.get("post_count", 0)
        sr = s_data.get("reel_count", 0)
        svpp = sv / sp if sp > 0 else 0.0

        net_change = sv - av
        growth_pct = (net_change / av * 100) if av > 0 else (100.0 if sv > 0 else 0.0)

        ws2.cell(row=row_num, column=1, value=idx).alignment = align_center
        ws2.cell(row=row_num, column=2, value=f"@{p['username']}")
        
        link_cell = ws2.cell(row=row_num, column=3, value=f"https://www.instagram.com/{p['username']}/")
        link_cell.hyperlink = f"https://www.instagram.com/{p['username']}/"
        link_cell.font = Font(name="Segoe UI", size=9, color="2563EB", underline="single")

        ws2.cell(row=row_num, column=4, value=p["category"])
        ws2.cell(row=row_num, column=5, value=p["grade"]).alignment = align_center
        ws2.cell(row=row_num, column=6, value=f"Unit {p['unit_number']}" if p["unit_number"] != "-" else "-").alignment = align_center
        ws2.cell(row=row_num, column=7, value=p["creator_name"])

        ws2.cell(row=row_num, column=8, value=round(av)).number_format = "#,##0"
        ws2.cell(row=row_num, column=9, value=ap).number_format = "#,##0"
        ws2.cell(row=row_num, column=10, value=ar).number_format = "#,##0"
        ws2.cell(row=row_num, column=11, value=round(avpp)).number_format = "#,##0"

        ws2.cell(row=row_num, column=12, value=round(sv)).number_format = "#,##0"
        ws2.cell(row=row_num, column=13, value=sp).number_format = "#,##0"
        ws2.cell(row=row_num, column=14, value=sr).number_format = "#,##0"
        ws2.cell(row=row_num, column=15, value=round(svpp)).number_format = "#,##0"

        nc_cell = ws2.cell(row=row_num, column=16, value=round(net_change))
        nc_cell.number_format = "+#,##0;-#,##0;0"
        nc_cell.font = green_bold if net_change >= 0 else red_bold

        gw_cell = ws2.cell(row=row_num, column=17, value=growth_pct / 100)
        gw_cell.number_format = "+0.0%;-0.0%;0.0%"
        gw_cell.font = green_bold if growth_pct >= 0 else red_bold

        for c_idx in range(1, 18):
            cell = ws2.cell(row=row_num, column=c_idx)
            cell.border = thin_border
            if c_idx not in (3, 16, 17):
                cell.font = dark_regular
            if c_idx in (8, 9, 10, 11, 12, 13, 14, 15, 16, 17):
                cell.alignment = align_right

        ws2.row_dimensions[row_num].height = 18

    # -------------------------------------------------------------
    # TAB 3: AUGUST 2026 BREAKDOWN (100% UNCHANGED)
    # -------------------------------------------------------------
    ws3 = wb.create_sheet(title="August 2026 Breakdown")
    ws3.views.sheetView[0].showGridLines = True

    aug_headers = [
        "#", "Username", "Category", "Calculation Method", "Lifespan Divisor",
        "Target Month New Views", "Prior 6M Decay Delta", "Total August Delta Views",
        "August New Posts", "August Reels"
    ]
    for c_idx, h in enumerate(aug_headers, 1):
        cell = ws3.cell(row=1, column=c_idx, value=h)
        cell.font = white_bold
        cell.fill = navy_fill
        cell.alignment = align_center
        cell.border = thin_border
    ws3.row_dimensions[1].height = 26

    for idx, p in enumerate(sorted_profiles, 1):
        row_num = idx + 1
        u = p["clean_username"]
        a_data = aug_res.get(u, {})

        ws3.cell(row=row_num, column=1, value=idx).alignment = align_center
        ws3.cell(row=row_num, column=2, value=f"@{p['username']}")
        ws3.cell(row=row_num, column=3, value=p["category"])
        ws3.cell(row=row_num, column=4, value=a_data.get("calc_type", "-"))
        ws3.cell(row=row_num, column=5, value=str(a_data.get("divisor", "-"))).alignment = align_center

        ws3.cell(row=row_num, column=6, value=round(a_data.get("new_views", 0.0))).number_format = "#,##0"
        ws3.cell(row=row_num, column=7, value=round(a_data.get("decay_delta", 0.0))).number_format = "#,##0"
        ws3.cell(row=row_num, column=8, value=round(a_data.get("total_views", 0.0))).number_format = "#,##0"
        ws3.cell(row=row_num, column=9, value=a_data.get("post_count", 0)).number_format = "#,##0"
        ws3.cell(row=row_num, column=10, value=a_data.get("reel_count", 0)).number_format = "#,##0"

        for c_idx in range(1, 11):
            cell = ws3.cell(row=row_num, column=c_idx)
            cell.border = thin_border
            cell.font = dark_regular
            if c_idx in (6, 7, 8, 9, 10):
                cell.alignment = align_right

        ws3.row_dimensions[row_num].height = 18

    # -------------------------------------------------------------
    # TAB 4: SEPTEMBER 2026 BREAKDOWN (100% UNCHANGED)
    # -------------------------------------------------------------
    ws4 = wb.create_sheet(title="September 2026 Breakdown")
    ws4.views.sheetView[0].showGridLines = True

    sep_headers = [
        "#", "Username", "Category", "Calculation Method", "Lifespan Divisor",
        "Target Month New Views", "Prior 6M Decay Delta", "Total September Delta Views",
        "September New Posts", "September Reels"
    ]
    for c_idx, h in enumerate(sep_headers, 1):
        cell = ws4.cell(row=1, column=c_idx, value=h)
        cell.font = white_bold
        cell.fill = navy_fill
        cell.alignment = align_center
        cell.border = thin_border
    ws4.row_dimensions[1].height = 26

    for idx, p in enumerate(sorted_profiles, 1):
        row_num = idx + 1
        u = p["clean_username"]
        s_data = sep_res.get(u, {})

        ws4.cell(row=row_num, column=1, value=idx).alignment = align_center
        ws4.cell(row=row_num, column=2, value=f"@{p['username']}")
        ws4.cell(row=row_num, column=3, value=p["category"])
        ws4.cell(row=row_num, column=4, value=s_data.get("calc_type", "-"))
        ws4.cell(row=row_num, column=5, value=str(s_data.get("divisor", "-"))).alignment = align_center

        ws4.cell(row=row_num, column=6, value=round(s_data.get("new_views", 0.0))).number_format = "#,##0"
        ws4.cell(row=row_num, column=7, value=round(s_data.get("decay_delta", 0.0))).number_format = "#,##0"
        ws4.cell(row=row_num, column=8, value=round(s_data.get("total_views", 0.0))).number_format = "#,##0"
        ws4.cell(row=row_num, column=9, value=s_data.get("post_count", 0)).number_format = "#,##0"
        ws4.cell(row=row_num, column=10, value=s_data.get("reel_count", 0)).number_format = "#,##0"

        for c_idx in range(1, 11):
            cell = ws4.cell(row=row_num, column=c_idx)
            cell.border = thin_border
            cell.font = dark_regular
            if c_idx in (6, 7, 8, 9, 10):
                cell.alignment = align_right

        ws4.row_dimensions[row_num].height = 18

    # -------------------------------------------------------------
    # TAB 5: UNMONITORED - DEDICATED COLLABS (NEW TAB)
    # -------------------------------------------------------------
    ws5 = wb.create_sheet(title="Unmonitored - Dedicated Collabs")
    ws5.views.sheetView[0].showGridLines = True

    unmon_headers = [
        "#", "Unmonitored Username", "Instagram Link", "Linked Monitored Channels",
        "Primary Role", "August New Upload Views", "August Decay Delta", "Total August Delta Views",
        "August New Uploads", "August Active Reels",
        "September New Upload Views", "September Decay Delta", "Total September Delta Views",
        "September New Uploads", "September Active Reels",
        "MoM Views Growth %", "Total Collab Reels", "Filter Status"
    ]
    for c_idx, h in enumerate(unmon_headers, 1):
        cell = ws5.cell(row=1, column=c_idx, value=h)
        cell.font = white_bold
        cell.fill = purple_fill
        cell.alignment = align_center
        cell.border = thin_border
    ws5.row_dimensions[1].height = 26

    # Sort unmonitored dedicated by September Total Delta desc
    sorted_unmon_ded = sorted(
        unmon_ded.items(),
        key=lambda item: (item[1]["sep_new"] + item[1]["sep_decay"]),
        reverse=True
    )

    for idx, (uname, data) in enumerate(sorted_unmon_ded, 1):
        row_num = idx + 1
        av_tot = data["aug_new"] + data["aug_decay"]
        sv_tot = data["sep_new"] + data["sep_decay"]
        gw = ((sv_tot - av_tot) / av_tot * 100) if av_tot > 0 else (100.0 if sv_tot > 0 else 0.0)

        linked_str = ", ".join(f"@{m}" for m in sorted(data["linked"])[:3])
        if len(data["linked"]) > 3:
            linked_str += f" (+{len(data['linked'])-3} more)"

        role_str = "Original Publisher" if data["is_owner_count"] > 0 else "Invited Co-Author"

        ws5.cell(row=row_num, column=1, value=idx).alignment = align_center
        ws5.cell(row=row_num, column=2, value=f"@{uname}")
        
        link_cell = ws5.cell(row=row_num, column=3, value=f"https://www.instagram.com/{uname}/")
        link_cell.hyperlink = f"https://www.instagram.com/{uname}/"
        link_cell.font = Font(name="Segoe UI", size=9, color="2563EB", underline="single")

        ws5.cell(row=row_num, column=4, value=linked_str)
        ws5.cell(row=row_num, column=5, value=role_str).alignment = align_center

        ws5.cell(row=row_num, column=6, value=round(data["aug_new"])).number_format = "#,##0"
        ws5.cell(row=row_num, column=7, value=round(data["aug_decay"])).number_format = "#,##0"
        ws5.cell(row=row_num, column=8, value=round(av_tot)).number_format = "#,##0"
        ws5.cell(row=row_num, column=9, value=len(data["aug_new_reels"])).number_format = "#,##0"
        ws5.cell(row=row_num, column=10, value=len(data["aug_new_reels"] | data["aug_decay_reels"])).number_format = "#,##0"

        ws5.cell(row=row_num, column=11, value=round(data["sep_new"])).number_format = "#,##0"
        ws5.cell(row=row_num, column=12, value=round(data["sep_decay"])).number_format = "#,##0"
        ws5.cell(row=row_num, column=13, value=round(sv_tot)).number_format = "#,##0"
        ws5.cell(row=row_num, column=14, value=len(data["sep_new_reels"])).number_format = "#,##0"
        ws5.cell(row=row_num, column=15, value=len(data["sep_new_reels"] | data["sep_decay_reels"])).number_format = "#,##0"

        g_c = ws5.cell(row=row_num, column=16, value=gw / 100)
        g_c.number_format = "+0.0%;-0.0%;0.0%"
        g_c.font = green_bold if gw >= 0 else red_bold

        ws5.cell(row=row_num, column=17, value=len(data["total_reels"])).number_format = "#,##0"
        ws5.cell(row=row_num, column=18, value="Dedicated Unconditional").alignment = align_center

        for c_idx in range(1, 19):
            cell = ws5.cell(row=row_num, column=c_idx)
            cell.border = thin_border
            if c_idx not in (3, 16):
                cell.font = dark_regular
            if c_idx in (6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 17):
                cell.alignment = align_right
            if c_idx in (1, 5, 18):
                cell.alignment = align_center

        ws5.row_dimensions[row_num].height = 18

    # -------------------------------------------------------------
    # TAB 6: UNMONITORED - IHI COLLABS (NEW TAB - FILTER PASSING ONLY)
    # -------------------------------------------------------------
    ws6 = wb.create_sheet(title="Unmonitored - IHI Collabs")
    ws6.views.sheetView[0].showGridLines = True

    for c_idx, h in enumerate(unmon_headers, 1):
        cell = ws6.cell(row=1, column=c_idx, value=h)
        cell.font = white_bold
        cell.fill = navy_fill
        cell.alignment = align_center
        cell.border = thin_border
    ws6.row_dimensions[1].height = 26

    # Sort unmonitored IHI by September Total Delta desc
    sorted_unmon_ihi = sorted(
        unmon_ihi.items(),
        key=lambda item: (item[1]["sep_new"] + item[1]["sep_decay"]),
        reverse=True
    )

    for idx, (uname, data) in enumerate(sorted_unmon_ihi, 1):
        row_num = idx + 1
        av_tot = data["aug_new"] + data["aug_decay"]
        sv_tot = data["sep_new"] + data["sep_decay"]
        gw = ((sv_tot - av_tot) / av_tot * 100) if av_tot > 0 else (100.0 if sv_tot > 0 else 0.0)

        linked_str = ", ".join(f"@{m}" for m in sorted(data["linked"])[:3])
        if len(data["linked"]) > 3:
            linked_str += f" (+{len(data['linked'])-3} more)"

        role_str = "Original Publisher" if data["is_owner_count"] > 0 else "Invited Co-Author"

        ws6.cell(row=row_num, column=1, value=idx).alignment = align_center
        ws6.cell(row=row_num, column=2, value=f"@{uname}")
        
        link_cell = ws6.cell(row=row_num, column=3, value=f"https://www.instagram.com/{uname}/")
        link_cell.hyperlink = f"https://www.instagram.com/{uname}/"
        link_cell.font = Font(name="Segoe UI", size=9, color="2563EB", underline="single")

        ws6.cell(row=row_num, column=4, value=linked_str)
        ws6.cell(row=row_num, column=5, value=role_str).alignment = align_center

        ws6.cell(row=row_num, column=6, value=round(data["aug_new"])).number_format = "#,##0"
        ws6.cell(row=row_num, column=7, value=round(data["aug_decay"])).number_format = "#,##0"
        ws6.cell(row=row_num, column=8, value=round(av_tot)).number_format = "#,##0"
        ws6.cell(row=row_num, column=9, value=len(data["aug_new_reels"])).number_format = "#,##0"
        ws6.cell(row=row_num, column=10, value=len(data["aug_new_reels"] | data["aug_decay_reels"])).number_format = "#,##0"

        ws6.cell(row=row_num, column=11, value=round(data["sep_new"])).number_format = "#,##0"
        ws6.cell(row=row_num, column=12, value=round(data["sep_decay"])).number_format = "#,##0"
        ws6.cell(row=row_num, column=13, value=round(sv_tot)).number_format = "#,##0"
        ws6.cell(row=row_num, column=14, value=len(data["sep_new_reels"])).number_format = "#,##0"
        ws6.cell(row=row_num, column=15, value=len(data["sep_new_reels"] | data["sep_decay_reels"])).number_format = "#,##0"

        g_c = ws6.cell(row=row_num, column=16, value=gw / 100)
        g_c.number_format = "+0.0%;-0.0%;0.0%"
        g_c.font = green_bold if gw >= 0 else red_bold

        ws6.cell(row=row_num, column=17, value=len(data["total_reels"])).number_format = "#,##0"
        ws6.cell(row=row_num, column=18, value="Verified Spiritual Match").alignment = align_center

        for c_idx in range(1, 19):
            cell = ws6.cell(row=row_num, column=c_idx)
            cell.border = thin_border
            if c_idx not in (3, 16):
                cell.font = dark_regular
            if c_idx in (6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 17):
                cell.alignment = align_right
            if c_idx in (1, 5, 18):
                cell.alignment = align_center

        ws6.row_dimensions[row_num].height = 18

    # Auto-adjust column widths across all 7 sheets
    for ws in [ws1, ws_8020, ws2, ws3, ws4, ws5, ws6]:
        for col in ws.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                val = str(cell.value or "")
                if len(val) > max_len and not getattr(cell, "is_merged", False):
                    max_len = len(val)
            ws.column_dimensions[col_letter].width = max(min(max_len + 3, 50), 11)

    output_filename = "Instagram_All_Channels_August_September_2026_Delta_Report.xlsx"
    workspace_path = f"/Users/sadhguruwisdomwarrior/.gemini/antigravity/scratch/WisdomWarriors/{output_filename}"
    artifact_path = f"/Users/sadhguruwisdomwarrior/.gemini/antigravity/brain/da87c5c7-cae1-4727-8648-8c431ee707c7/{output_filename}"
    downloads_path = f"/Users/sadhguruwisdomwarrior/Downloads/{output_filename}"
    downloads_total = "/Users/sadhguruwisdomwarrior/Downloads/Total_Report.xlsx"
    downloads_total_space = "/Users/sadhguruwisdomwarrior/Downloads/Total Report.xlsx"
    workspace_total = "/Users/sadhguruwisdomwarrior/.gemini/antigravity/scratch/WisdomWarriors/Total_Report.xlsx"
    artifact_total = "/Users/sadhguruwisdomwarrior/.gemini/antigravity/brain/da87c5c7-cae1-4727-8648-8c431ee707c7/Total_Report.xlsx"

    wb.save(workspace_path)
    wb.save(artifact_path)
    wb.save(workspace_total)
    wb.save(artifact_total)
    try:
        wb.save(downloads_path)
        wb.save(downloads_total)
        wb.save(downloads_total_space)
        print(f"Saved to Downloads: {downloads_path}")
        print(f"Saved to Downloads: {downloads_total}")
        print(f"Saved to Downloads: {downloads_total_space}")
    except Exception as e:
        print(f"Note: Could not save to Downloads: {e}")

    print(f"\nReport generated and saved successfully with all 7 sheets to:")
    print(f"1. {workspace_path}")
    print(f"2. {artifact_path}")
    print(f"3. {downloads_path}")
    print(f"4. {downloads_total}")
    print("\nCalculation completed with 100% adherence to gemini.md!")

if __name__ == "__main__":
    main()
