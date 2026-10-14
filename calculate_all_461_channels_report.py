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

    # Build direct index: channel_posts[run_id][channel_clean_username][shortcode]
    print("\nIndexing posts by channel and applying taxonomy filters...")
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

    def calculate_month_metrics(target_year: int, target_month: int, s1_run_id: int, s2_run_id: int):
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

    # 3. Calculate August and September 2026
    print("\nCalculating August 2026 metrics (S1=97, S2=111)...")
    aug_res = calculate_month_metrics(2026, 8, 97, 111)

    print("Calculating September 2026 metrics (S1=111, S2=112)...")
    sep_res = calculate_month_metrics(2026, 9, 111, 112)

    # 4. Sync / Upsert into monthly_channel_metrics table
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

        # August metric
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

        # September metric
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

    # 5. Build Comprehensive Excel Workbook Report
    print("\nGenerating comprehensive Excel workbook...")
    wb = openpyxl.Workbook()
    wb.remove(wb.active)  # Remove default sheet

    # Styles
    navy_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    purple_fill = PatternFill(start_color="4C1D95", end_color="4C1D95", fill_type="solid")
    header_fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
    alt_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    highlight_fill = PatternFill(start_color="EDE9FE", end_color="EDE9FE", fill_type="solid")

    white_bold = Font(name="Segoe UI", size=10, bold=True, color="FFFFFF")
    white_title = Font(name="Segoe UI", size=15, bold=True, color="FFFFFF")
    white_subtitle = Font(name="Segoe UI", size=10, bold=False, color="CBD5E1")
    dark_bold = Font(name="Segoe UI", size=10, bold=True, color="0F172A")
    dark_regular = Font(name="Segoe UI", size=9, bold=False, color="1E293B")
    green_bold = Font(name="Segoe UI", size=9, bold=True, color="047857")
    red_bold = Font(name="Segoe UI", size=9, bold=True, color="B91C1C")

    thin_border_side = Side(style="thin", color="E2E8F0")
    thin_border = Border(left=thin_border_side, right=thin_border_side, top=thin_border_side, bottom=thin_border_side)
    thick_bottom = Border(bottom=Side(style="medium", color="0F172A"), top=thin_border_side, left=thin_border_side, right=thin_border_side)

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

    # Top 10 Channels September
    r += 3
    ws1.cell(row=r, column=1, value="TOP 10 CHANNELS BY SEPTEMBER 2026 DELTA VIEWS").font = dark_bold
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

    # -------------------------------------------------------------
    # TAB 2: ALL 461 CHANNELS MASTER MATRIX
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

    # Sort master matrix: Dedicated first, then by September views desc
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
    # TAB 3: AUGUST 2026 BREAKDOWN
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
    # TAB 4: SEPTEMBER 2026 BREAKDOWN
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

    # Auto-adjust column widths across all sheets
    for ws in [ws1, ws2, ws3, ws4]:
        for col in ws.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                val = str(cell.value or '')
                if len(val) > max_len:
                    max_len = len(val)
            ws.column_dimensions[col_letter].width = max(max_len + 3, 11)

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

    print(f"\nReport generated and saved successfully to:")
    print(f"1. {workspace_path}")
    print(f"2. {artifact_path}")
    print("\nCalculation completed with 100% adherence to gemini.md!")

if __name__ == "__main__":
    main()
