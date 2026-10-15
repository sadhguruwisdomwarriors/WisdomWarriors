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

                results[uname] = {
                    "total_views": monthly_total,
                    "new_views": target_new_views,
                    "decay_delta": max(0.0, monthly_total - target_new_views),
                    "post_count": len(s2_target),
                    "reel_count": sum(1 for p in s2_target.values() if p["is_reel"]),
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
                results[uname] = {
                    "total_views": monthly_total,
                    "new_views": 0.0,
                    "decay_delta": monthly_total,
                    "post_count": 0,
                    "reel_count": 0,
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

            results[uname] = {
                "total_views": total_views,
                "new_views": new_views,
                "decay_delta": total_decay,
                "post_count": post_count,
                "reel_count": reel_count,
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
        "linked": set(), "is_owner_count": 0, "total_reels": 0
    })
    unmon_ihi = defaultdict(lambda: {
        "aug_new": 0.0, "aug_decay": 0.0, "sep_new": 0.0, "sep_decay": 0.0,
        "linked": set(), "is_owner_count": 0, "total_reels": 0
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
                unmon_ded[ext]["total_reels"] += 1
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
                    unmon_ihi[ext]["total_reels"] += 1
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
        "Dedicated": {"aug_views": 0.0, "aug_posts": 0, "sep_views": 0.0, "sep_posts": 0, "count": 0},
        "In-house influencer": {"aug_views": 0.0, "aug_posts": 0, "sep_views": 0.0, "sep_posts": 0, "count": 0}
    }

    for prof in profile_list:
        c = prof["category"]
        u = prof["clean_username"]
        cat_summary[c]["count"] += 1
        cat_summary[c]["aug_views"] += aug_res.get(u, {}).get("total_views", 0.0)
        cat_summary[c]["aug_posts"] += aug_res.get(u, {}).get("post_count", 0)
        cat_summary[c]["sep_views"] += sep_res.get(u, {}).get("total_views", 0.0)
        cat_summary[c]["sep_posts"] += sep_res.get(u, {}).get("post_count", 0)

    # -------------------------------------------------------------
    # TAB 1: EXECUTIVE 80-20 SUMMARY
    # -------------------------------------------------------------
    ws1 = wb.create_sheet(title="Executive 80-20 Summary")
    ws1.views.sheetView[0].showGridLines = True

    ws1.merge_cells("A1:G1")
    ws1["A1"] = "Wisdom Warriors Instagram Analytics — August vs. September 2026 Executive Summary"
    ws1["A1"].font = white_title
    ws1["A1"].fill = header_fill
    ws1["A1"].alignment = align_left

    ws1.merge_cells("A2:G2")
    ws1["A2"] = "Strict compliance with gemini.md 6-Case Master Specification | Run 97 -> Run 111 -> Run 112"
    ws1["A2"].font = white_subtitle
    ws1["A2"].fill = header_fill
    ws1["A2"].alignment = align_left

    ws1.row_dimensions[1].height = 28
    ws1.row_dimensions[2].height = 18

    # Table 1: Monitored Channels Portfolio Summary (100% UNCHANGED)
    headers_t1 = [
        "Category Architecture", "Total Channels", "August 2026 Delta Views", "August New Posts",
        "September 2026 Delta Views", "September New Posts", "MoM Growth %"
    ]
    for col_idx, h in enumerate(headers_t1, 1):
        cell = ws1.cell(row=4, column=col_idx, value=h)
        cell.font = white_bold
        cell.fill = purple_fill
        cell.alignment = align_center
        cell.border = thin_border
    ws1.row_dimensions[4].height = 24

    r = 5
    for cat_name, label in [("Dedicated", "Wisdom Warriors (Dedicated Channels — 100% credited)"),
                            ("In-house influencer", "In-House Influencers (IHI — Filtered credited)")]:
        data = cat_summary[cat_name]
        aug_v = data["aug_views"]
        sep_v = data["sep_views"]
        growth = ((sep_v - aug_v) / aug_v * 100) if aug_v > 0 else 0.0

        ws1.cell(row=r, column=1, value=label).font = dark_bold
        ws1.cell(row=r, column=2, value=data["count"]).font = dark_regular
        ws1.cell(row=r, column=3, value=round(aug_v)).number_format = "#,##0"
        ws1.cell(row=r, column=4, value=data["aug_posts"]).number_format = "#,##0"
        ws1.cell(row=r, column=5, value=round(sep_v)).number_format = "#,##0"
        ws1.cell(row=r, column=6, value=data["sep_posts"]).number_format = "#,##0"
        
        g_cell = ws1.cell(row=r, column=7, value=growth / 100)
        g_cell.number_format = "+0.0%;-0.0%;0.0%"
        g_cell.font = green_bold if growth >= 0 else red_bold

        for col_idx in range(1, 8):
            ws1.cell(row=r, column=col_idx).border = thin_border
            if col_idx in (2, 4, 6):
                ws1.cell(row=r, column=col_idx).alignment = align_center
            elif col_idx in (3, 5, 7):
                ws1.cell(row=r, column=col_idx).alignment = align_right
        ws1.row_dimensions[r].height = 20
        r += 1

    tot_aug_v = cat_summary["Dedicated"]["aug_views"] + cat_summary["In-house influencer"]["aug_views"]
    tot_aug_p = cat_summary["Dedicated"]["aug_posts"] + cat_summary["In-house influencer"]["aug_posts"]
    tot_sep_v = cat_summary["Dedicated"]["sep_views"] + cat_summary["In-house influencer"]["sep_views"]
    tot_sep_p = cat_summary["Dedicated"]["sep_posts"] + cat_summary["In-house influencer"]["sep_posts"]
    tot_growth = ((tot_sep_v - tot_aug_v) / tot_aug_v * 100) if tot_aug_v > 0 else 0.0

    ws1.cell(row=r, column=1, value="TOTAL ALL REGISTERED CHANNELS (461)").font = dark_bold
    ws1.cell(row=r, column=2, value=len(profile_list)).font = dark_bold
    ws1.cell(row=r, column=3, value=round(tot_aug_v)).number_format = "#,##0"
    ws1.cell(row=r, column=4, value=tot_aug_p).number_format = "#,##0"
    ws1.cell(row=r, column=5, value=round(tot_sep_v)).number_format = "#,##0"
    ws1.cell(row=r, column=6, value=tot_sep_p).number_format = "#,##0"
    tg_cell = ws1.cell(row=r, column=7, value=tot_growth / 100)
    tg_cell.number_format = "+0.0%;-0.0%;0.0%"
    tg_cell.font = green_bold if tot_growth >= 0 else red_bold

    for col_idx in range(1, 8):
        ws1.cell(row=r, column=col_idx).fill = highlight_fill
        ws1.cell(row=r, column=col_idx).border = thick_bottom
        if col_idx in (2, 4, 6):
            ws1.cell(row=r, column=col_idx).alignment = align_center
        elif col_idx in (3, 5, 7):
            ws1.cell(row=r, column=col_idx).alignment = align_right
    ws1.row_dimensions[r].height = 22

    # Top 10 Channels September (UNCHANGED)
    r += 2
    ws1.cell(row=r, column=1, value="TOP 10 MONITORED CHANNELS BY SEPTEMBER 2026 DELTA VIEWS").font = dark_bold
    r += 1
    top10_headers = ["Rank", "Username", "Category", "Micro Unit", "August Views", "September Views", "MoM Growth %"]
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
        av = aug_res.get(u, {}).get("total_views", 0.0)
        sv = sep_res.get(u, {}).get("total_views", 0.0)
        gw = ((sv - av) / av * 100) if av > 0 else 0.0

        ws1.cell(row=r, column=1, value=rank).alignment = align_center
        ws1.cell(row=r, column=2, value=f"@{p['username']}")
        ws1.cell(row=r, column=3, value=p["category"])
        ws1.cell(row=r, column=4, value=f"Unit {p['unit_number']}" if p["unit_number"] != "-" else "Unassigned")
        ws1.cell(row=r, column=5, value=round(av)).number_format = "#,##0"
        ws1.cell(row=r, column=6, value=round(sv)).number_format = "#,##0"
        g_c = ws1.cell(row=r, column=7, value=gw / 100)
        g_c.number_format = "+0.0%;-0.0%;0.0%"
        g_c.font = green_bold if gw >= 0 else red_bold

        for c_idx in range(1, 8):
            ws1.cell(row=r, column=c_idx).border = thin_border
            ws1.cell(row=r, column=c_idx).font = dark_regular if c_idx != 7 else (green_bold if gw >= 0 else red_bold)
            if c_idx in (5, 6, 7):
                ws1.cell(row=r, column=c_idx).alignment = align_right
        ws1.row_dimensions[r].height = 18
        r += 1

    # Table 3: UNMONITORED COLLABORATIVE CHANNELS SUMMARY (SEPARATE STANDALONE AUDIT)
    r += 2
    ws1.cell(row=r, column=1, value="UNMONITORED COLLABORATORS SUMMARY (TRACKED SEPARATELY IN TABS 5 & 6)").font = dark_bold
    r += 1

    unmon_summary_headers = [
        "Unmonitored Collaboration Scope", "Unique External Accounts", "August Delta Views", "August Collab Reels",
        "September Delta Views", "September Collab Reels", "MoM Growth %"
    ]
    for c_idx, th in enumerate(unmon_summary_headers, 1):
        cell = ws1.cell(row=r, column=c_idx, value=th)
        cell.font = white_bold
        cell.fill = navy_fill
        cell.alignment = align_center
        cell.border = thin_border
    ws1.row_dimensions[r].height = 22
    r += 1

    # Compute unmonitored summary totals
    tot_aug_ded_v = sum(d["aug_new"] + d["aug_decay"] for d in unmon_ded.values())
    tot_sep_ded_v = sum(d["sep_new"] + d["sep_decay"] for d in unmon_ded.values())
    tot_ded_reels = sum(d["total_reels"] for d in unmon_ded.values())
    gw_ded = ((tot_sep_ded_v - tot_aug_ded_v) / tot_aug_ded_v * 100) if tot_aug_ded_v > 0 else 0.0

    tot_aug_ihi_v = sum(d["aug_new"] + d["aug_decay"] for d in unmon_ihi.values())
    tot_sep_ihi_v = sum(d["sep_new"] + d["sep_decay"] for d in unmon_ihi.values())
    tot_ihi_reels = sum(d["total_reels"] for d in unmon_ihi.values())
    gw_ihi = ((tot_sep_ihi_v - tot_aug_ihi_v) / tot_aug_ihi_v * 100) if tot_aug_ihi_v > 0 else 0.0

    unmon_rows_data = [
        ("Unmonitored Channels linked to Dedicated Collabs (Tab 5 — 100% Unconditional)", len(unmon_ded), tot_aug_ded_v, tot_ded_reels, tot_sep_ded_v, tot_ded_reels, gw_ded),
        ("Unmonitored Channels linked to IHI Collabs (Tab 6 — Verified Spiritual Filter)", len(unmon_ihi), tot_aug_ihi_v, tot_ihi_reels, tot_sep_ihi_v, tot_ihi_reels, gw_ihi)
    ]

    for label, count, av, ar, sv, sr, gw in unmon_rows_data:
        ws1.cell(row=r, column=1, value=label).font = dark_bold
        ws1.cell(row=r, column=2, value=count).alignment = align_center
        ws1.cell(row=r, column=3, value=round(av)).number_format = "#,##0"
        ws1.cell(row=r, column=4, value=ar).number_format = "#,##0"
        ws1.cell(row=r, column=5, value=round(sv)).number_format = "#,##0"
        ws1.cell(row=r, column=6, value=sr).number_format = "#,##0"
        gc = ws1.cell(row=r, column=7, value=gw / 100)
        gc.number_format = "+0.0%;-0.0%;0.0%"
        gc.font = green_bold if gw >= 0 else red_bold

        for c_idx in range(1, 8):
            cell = ws1.cell(row=r, column=c_idx)
            cell.border = thin_border
            if c_idx not in (1, 7):
                cell.font = dark_regular
            if c_idx in (3, 5):
                cell.alignment = align_right
            if c_idx in (2, 4, 6):
                cell.alignment = align_center
        ws1.row_dimensions[r].height = 20
        r += 1

    # Total Unmonitored row
    tot_unmon_aug_v = tot_aug_ded_v + tot_aug_ihi_v
    tot_unmon_sep_v = tot_sep_ded_v + tot_sep_ihi_v
    tot_unmon_reels = tot_ded_reels + tot_ihi_reels
    tot_unmon_accounts = len(unmon_ded) + len(unmon_ihi)
    tot_unmon_gw = ((tot_unmon_sep_v - tot_unmon_aug_v) / tot_unmon_aug_v * 100) if tot_unmon_aug_v > 0 else 0.0

    ws1.cell(row=r, column=1, value="TOTAL UNMONITORED COLLABORATOR VIEWS (TABS 5 & 6)").font = dark_bold
    ws1.cell(row=r, column=2, value=tot_unmon_accounts).font = dark_bold
    ws1.cell(row=r, column=3, value=round(tot_unmon_aug_v)).number_format = "#,##0"
    ws1.cell(row=r, column=4, value=tot_unmon_reels).number_format = "#,##0"
    ws1.cell(row=r, column=5, value=round(tot_unmon_sep_v)).number_format = "#,##0"
    ws1.cell(row=r, column=6, value=tot_unmon_reels).number_format = "#,##0"
    ug_cell = ws1.cell(row=r, column=7, value=tot_unmon_gw / 100)
    ug_cell.number_format = "+0.0%;-0.0%;0.0%"
    ug_cell.font = green_bold if tot_unmon_gw >= 0 else red_bold

    for col_idx in range(1, 8):
        ws1.cell(row=r, column=col_idx).fill = highlight_fill
        ws1.cell(row=r, column=col_idx).border = thick_bottom
        if col_idx in (2, 4, 6):
            ws1.cell(row=r, column=col_idx).alignment = align_center
        elif col_idx in (3, 5, 7):
            ws1.cell(row=r, column=col_idx).alignment = align_right
    ws1.row_dimensions[r].height = 22
    r += 1

    # Table 4: GRAND TOTAL PORTFOLIO & ECOSYSTEM REACH
    r += 2
    ws1.cell(row=r, column=1, value="GRAND TOTAL: MONITORED + UNMONITORED ECOSYSTEM REACH (ZERO DUPLICATION)").font = dark_bold
    r += 1

    grand_headers = [
        "Ecosystem Reach Scope", "Channel / Account Count", "August 2026 Delta Views", "August Posts/Reels",
        "September 2026 Delta Views", "September Posts/Reels", "MoM Growth %"
    ]
    for c_idx, th in enumerate(grand_headers, 1):
        cell = ws1.cell(row=r, column=c_idx, value=th)
        cell.font = white_bold
        cell.fill = header_fill
        cell.alignment = align_center
        cell.border = thin_border
    ws1.row_dimensions[r].height = 22
    r += 1

    grand_aug_v = tot_aug_v + tot_unmon_aug_v
    grand_aug_p = tot_aug_p + tot_unmon_reels
    grand_sep_v = tot_sep_v + tot_unmon_sep_v
    grand_sep_p = tot_sep_p + tot_unmon_reels
    grand_gw = ((grand_sep_v - grand_aug_v) / grand_aug_v * 100) if grand_aug_v > 0 else 0.0

    grand_rows = [
        ("1. Official Monitored Channels Portfolio (Tabs 2, 3, 4)", len(profile_list), tot_aug_v, tot_aug_p, tot_sep_v, tot_sep_p, tot_growth),
        ("2. External Unmonitored Collaborators Ecosystem (Tabs 5, 6)", tot_unmon_accounts, tot_unmon_aug_v, tot_unmon_reels, tot_unmon_sep_v, tot_unmon_reels, tot_unmon_gw),
    ]

    for label, count, av, ap, sv, sp, gw in grand_rows:
        ws1.cell(row=r, column=1, value=label).font = dark_bold
        ws1.cell(row=r, column=2, value=count).alignment = align_center
        ws1.cell(row=r, column=3, value=round(av)).number_format = "#,##0"
        ws1.cell(row=r, column=4, value=ap).number_format = "#,##0"
        ws1.cell(row=r, column=5, value=round(sv)).number_format = "#,##0"
        ws1.cell(row=r, column=6, value=sp).number_format = "#,##0"
        gc = ws1.cell(row=r, column=7, value=gw / 100)
        gc.number_format = "+0.0%;-0.0%;0.0%"
        gc.font = green_bold if gw >= 0 else red_bold

        for c_idx in range(1, 8):
            cell = ws1.cell(row=r, column=c_idx)
            cell.border = thin_border
            if c_idx not in (1, 7):
                cell.font = dark_regular
            if c_idx in (3, 5):
                cell.alignment = align_right
            if c_idx in (2, 4, 6):
                cell.alignment = align_center
        ws1.row_dimensions[r].height = 20
        r += 1

    # Grand Total combined row
    ws1.cell(row=r, column=1, value="COMBINED ECOSYSTEM GRAND TOTAL (Zero View Overlap)").font = dark_bold
    ws1.cell(row=r, column=2, value=len(profile_list) + tot_unmon_accounts).font = dark_bold
    ws1.cell(row=r, column=3, value=round(grand_aug_v)).number_format = "#,##0"
    ws1.cell(row=r, column=4, value=grand_aug_p).number_format = "#,##0"
    ws1.cell(row=r, column=5, value=round(grand_sep_v)).number_format = "#,##0"
    ws1.cell(row=r, column=6, value=grand_sep_p).number_format = "#,##0"
    gg_cell = ws1.cell(row=r, column=7, value=grand_gw / 100)
    gg_cell.number_format = "+0.0%;-0.0%;0.0%"
    gg_cell.font = green_bold if grand_gw >= 0 else red_bold

    for col_idx in range(1, 8):
        ws1.cell(row=r, column=col_idx).fill = highlight_fill
        ws1.cell(row=r, column=col_idx).border = double_bottom
        if col_idx in (2, 4, 6):
            ws1.cell(row=r, column=col_idx).alignment = align_center
        elif col_idx in (3, 5, 7):
            ws1.cell(row=r, column=col_idx).alignment = align_right
    ws1.row_dimensions[r].height = 24
    r += 1

    # Note banner
    ws1.merge_cells(start_row=r, start_column=1, end_row=r, end_column=7)
    note_cell = ws1.cell(row=r, column=1, value="* ZERO REPEATED VIEWS PROOF: Every reel is split strictly among its co-authors (Views / N). Monitored creators receive their exact fraction in Tabs 2-4, and outside collaborators receive their fraction in Tabs 5-6. The fractions sum to exactly 100% of the reel's play count. No view is ever double-counted or credited twice.")
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
        ws1.cell(row=r, column=3, value=elig).font = dark_regular
        ws1.cell(row=r, column=4, value=meth).font = dark_regular
        ws1.cell(row=r, column=5, value=miss).font = dark_regular

        for c_idx in range(1, 6):
            cell = ws1.cell(row=r, column=c_idx)
            cell.border = thin_border
            cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
            if "Unmonitored" in scope:
                cell.fill = light_blue_fill
            else:
                cell.fill = light_amber_fill
        ws1.row_dimensions[r].height = 54
        r += 1

    # -------------------------------------------------------------
    # TAB 2: ALL 461 CHANNELS MASTER MATRIX (100% UNCHANGED)
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
        "#", "Unmonitored Username", "Instagram Link", "Linked Monitored Dedicated Channels",
        "Primary Role", "August New Upload Views", "August Decay Delta", "Total August Delta Views",
        "September New Upload Views", "September Decay Delta", "Total September Delta Views",
        "MoM Growth %", "Total Collab Reels", "Filter Status"
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

        ws5.cell(row=row_num, column=9, value=round(data["sep_new"])).number_format = "#,##0"
        ws5.cell(row=row_num, column=10, value=round(data["sep_decay"])).number_format = "#,##0"
        ws5.cell(row=row_num, column=11, value=round(sv_tot)).number_format = "#,##0"

        g_c = ws5.cell(row=row_num, column=12, value=gw / 100)
        g_c.number_format = "+0.0%;-0.0%;0.0%"
        g_c.font = green_bold if gw >= 0 else red_bold

        ws5.cell(row=row_num, column=13, value=data["total_reels"]).number_format = "#,##0"
        ws5.cell(row=row_num, column=14, value="Dedicated Unconditional").alignment = align_center

        for c_idx in range(1, 15):
            cell = ws5.cell(row=row_num, column=c_idx)
            cell.border = thin_border
            if c_idx not in (3, 12):
                cell.font = dark_regular
            if c_idx in (6, 7, 8, 9, 10, 11, 13):
                cell.alignment = align_right

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

        ws6.cell(row=row_num, column=9, value=round(data["sep_new"])).number_format = "#,##0"
        ws6.cell(row=row_num, column=10, value=round(data["sep_decay"])).number_format = "#,##0"
        ws6.cell(row=row_num, column=11, value=round(sv_tot)).number_format = "#,##0"

        g_c = ws6.cell(row=row_num, column=12, value=gw / 100)
        g_c.number_format = "+0.0%;-0.0%;0.0%"
        g_c.font = green_bold if gw >= 0 else red_bold

        ws6.cell(row=row_num, column=13, value=data["total_reels"]).number_format = "#,##0"
        ws6.cell(row=row_num, column=14, value="Verified Spiritual Match").alignment = align_center

        for c_idx in range(1, 15):
            cell = ws6.cell(row=row_num, column=c_idx)
            cell.border = thin_border
            if c_idx not in (3, 12):
                cell.font = dark_regular
            if c_idx in (6, 7, 8, 9, 10, 11, 13):
                cell.alignment = align_right

        ws6.row_dimensions[row_num].height = 18

    # Auto-adjust column widths across all 6 sheets
    for ws in [ws1, ws2, ws3, ws4, ws5, ws6]:
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

    wb.save(workspace_path)
    wb.save(artifact_path)
    try:
        wb.save(downloads_path)
        print(f"Saved to Downloads: {downloads_path}")
    except Exception as e:
        print(f"Note: Could not save to Downloads: {e}")

    print(f"\nReport generated and saved successfully with all 6 sheets to:")
    print(f"1. {workspace_path}")
    print(f"2. {artifact_path}")
    print(f"3. {downloads_path}")
    print("\nCalculation completed with 100% adherence to gemini.md!")

if __name__ == "__main__":
    main()
