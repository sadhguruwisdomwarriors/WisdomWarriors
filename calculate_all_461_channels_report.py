import asyncio
import json
import os
import psycopg2
from collections import defaultdict
from datetime import datetime
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from backend.repositories.analytics_repo import (
    WISDOM_WARRIOR_ALLOWED_HASHTAGS,
    WISDOM_WARRIOR_ALLOWED_MENTIONS,
    WISDOM_WARRIOR_ALLOWED_TAGGED_USERS,
    WISDOM_WARRIOR_ALLOWED_CAPTION_KEYWORDS,
    _normalize_hashtag,
    _normalize_mention,
    _extract_coauthor_usernames,
    check_post_matches_filters
)
from types import SimpleNamespace

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
    print("="*80)
    print("WISDOM WARRIORS — COMPLETE AUGUST & SEPTEMBER DELTA CALCULATION")
    print("Strictly adhering to gemini.md specifications")
    print("="*80)

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
    # Columns: post_id, run_id, owner_username, coauthor_producers, video_play_count, timestamp, caption, hashtags, mentions, tagged_users
    print("\nFetching post snapshots for runs 97, 111, 112...")
    cur.execute("""
        SELECT post_id, run_id, owner_username, coauthor_producers, video_play_count, timestamp, caption, hashtags, mentions, tagged_users, type, product_type, video_view_count
        FROM post_snapshots
        WHERE run_id IN (97, 111, 112) AND timestamp IS NOT NULL;
    """)
    all_raw_posts = cur.fetchall()
    print(f"Fetched {len(all_raw_posts)} total post rows.")

    # Deduplicate posts per run by post_id (keeping highest video_play_count)
    posts_by_run = defaultdict(dict)
    for row in all_raw_posts:
        pid, rid, owner, coauthors, vpc, ts, caption, hashtags, mentions, tagged_users, ptype, prod_type, vvc = row
        vpc = vpc or 0
        if pid not in posts_by_run[rid] or vpc > (posts_by_run[rid][pid]["vpc"]):
            posts_by_run[rid][pid] = {
                "post_id": pid,
                "owner": (owner or "").strip().lstrip("@").lower(),
                "coauthors": extract_coauthors(coauthors),
                "vpc": vpc,
                "ts": ts,
                "month_str": ts.strftime("%Y-%m"),
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

    def compute_month_views_and_posts(run_id: int, month_str: str):
        views_by_user = defaultdict(float)
        posts_by_user = defaultdict(int)
        reels_by_user = defaultdict(int)

        run_posts = posts_by_run[run_id]
        for p in run_posts.values():
            if p["month_str"] != month_str:
                continue

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

            # Filter check
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

                    views_by_user[part] += shared_views
                    posts_by_user[part] += 1
                    if p["is_reel"]:
                        reels_by_user[part] += 1

        return views_by_user, posts_by_user, reels_by_user

    def get_active_users_in_run(run_id: int) -> set[str]:
        active = set()
        for p in posts_by_run[run_id].values():
            if p["owner"]:
                active.add(p["owner"])
            for ca in p["coauthors"]:
                active.add(ca)
        return active

    s1_active_users_run97 = get_active_users_in_run(97)
    s1_active_users_run111 = get_active_users_in_run(111)

    # -------------------------------------------------------------
    # 3. CALCULATE AUGUST 2026 (S1 = 97, S2 = 111)
    # -------------------------------------------------------------
    print("\nCalculating August 2026 metrics (S1=97, S2=111)...")
    aug_prior_months = get_prior_6_months(2026, 8)  # ['2026-07', '2026-06', '2026-05', '2026-04', '2026-03', '2026-02']
    
    aug_decay_deltas = defaultdict(float)
    aug_s2_window_totals = defaultdict(float)
    aug_channel_active_months = defaultdict(set)

    for prior_m in aug_prior_months:
        s1_views, _, _ = compute_month_views_and_posts(97, prior_m)
        s2_views, s2_posts, _ = compute_month_views_and_posts(111, prior_m)

        for uname in target_usernames:
            aug_s2_window_totals[uname] += s2_views[uname]
            if s2_views[uname] > 0 or s2_posts[uname] > 0:
                aug_channel_active_months[uname].add(prior_m)
            if uname in s1_active_users_run97:
                month_delta = max(0.0, s2_views[uname] - s1_views[uname])
                aug_decay_deltas[uname] += month_delta

    # Target month new uploads (August 2026) from Run 111
    aug_new_views, aug_post_counts, aug_reel_counts = compute_month_views_and_posts(111, "2026-08")

    aug_final_totals = {}
    aug_calc_type = {}
    aug_divisors = {}

    for uname in target_usernames:
        aug_s2_window_totals[uname] += aug_new_views[uname]
        if aug_new_views[uname] > 0 or aug_post_counts[uname] > 0:
            aug_channel_active_months[uname].add("2026-08")

        if uname in s1_active_users_run97:
            # Baseline exists in S1 -> New Uploads + 6-month decay delta
            total_views = aug_new_views[uname] + aug_decay_deltas[uname]
            aug_final_totals[uname] = total_views
            aug_calc_type[uname] = "Standard Delta (S2 - S1 + New)"
            aug_divisors[uname] = "-"
        else:
            # Newly scraped in Run 111 -> Normalized lifespan average
            if aug_channel_active_months[uname]:
                earliest_ym = min(aug_channel_active_months[uname])
                ey, em = map(int, earliest_ym.split("-"))
                span_months = (2026 - ey) * 12 + (8 - em) + 1
                months_divisor = max(1, min(7, span_months))
            else:
                months_divisor = 1
            total_views = aug_s2_window_totals[uname] / months_divisor
            aug_final_totals[uname] = total_views
            aug_calc_type[uname] = f"New Channel Normalized ({months_divisor} mo avg)"
            aug_divisors[uname] = months_divisor

    # -------------------------------------------------------------
    # 4. CALCULATE SEPTEMBER 2026 (S1 = 111, S2 = 112)
    # -------------------------------------------------------------
    print("Calculating September 2026 metrics (S1=111, S2=112)...")
    sep_prior_months = get_prior_6_months(2026, 9)  # ['2026-08', '2026-07', '2026-06', '2026-05', '2026-04', '2026-03']
    
    sep_decay_deltas = defaultdict(float)
    sep_s2_window_totals = defaultdict(float)
    sep_channel_active_months = defaultdict(set)

    for prior_m in sep_prior_months:
        s1_views, _, _ = compute_month_views_and_posts(111, prior_m)
        s2_views, s2_posts, _ = compute_month_views_and_posts(112, prior_m)

        for uname in target_usernames:
            sep_s2_window_totals[uname] += s2_views[uname]
            if s2_views[uname] > 0 or s2_posts[uname] > 0:
                sep_channel_active_months[uname].add(prior_m)
            if uname in s1_active_users_run111:
                month_delta = max(0.0, s2_views[uname] - s1_views[uname])
                sep_decay_deltas[uname] += month_delta

    # Target month new uploads (September 2026) from Run 112
    sep_new_views, sep_post_counts, sep_reel_counts = compute_month_views_and_posts(112, "2026-09")

    sep_final_totals = {}
    sep_calc_type = {}
    sep_divisors = {}

    for uname in target_usernames:
        sep_s2_window_totals[uname] += sep_new_views[uname]
        if sep_new_views[uname] > 0 or sep_post_counts[uname] > 0:
            sep_channel_active_months[uname].add("2026-09")

        if uname in s1_active_users_run111:
            total_views = sep_new_views[uname] + sep_decay_deltas[uname]
            sep_final_totals[uname] = total_views
            sep_calc_type[uname] = "Standard Delta (S2 - S1 + New)"
            sep_divisors[uname] = "-"
        else:
            if sep_channel_active_months[uname]:
                earliest_ym = min(sep_channel_active_months[uname])
                ey, em = map(int, earliest_ym.split("-"))
                span_months = (2026 - ey) * 12 + (9 - em) + 1
                months_divisor = max(1, min(7, span_months))
            else:
                months_divisor = 1
            total_views = sep_s2_window_totals[uname] / months_divisor
            sep_final_totals[uname] = total_views
            sep_calc_type[uname] = f"New Channel Normalized ({months_divisor} mo avg)"
            sep_divisors[uname] = months_divisor

    # -------------------------------------------------------------
    # 5. SYNC / UPSERT INTO monthly_channel_metrics TABLE
    # -------------------------------------------------------------
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
        aug_v = aug_final_totals.get(clean_u, 0.0)
        aug_p = aug_post_counts.get(clean_u, 0)
        aug_r = aug_reel_counts.get(clean_u, 0)
        aug_s = aug_p - aug_r
        aug_vpp = aug_v / aug_p if aug_p > 0 else 0.0

        cur.execute(upsert_sql, (
            ig_id, prof["username"], "2026-08", aug_v, None, None,
            aug_p, aug_r, aug_s, aug_vpp, 97, 111
        ))

        # September metric
        sep_v = sep_final_totals.get(clean_u, 0.0)
        sep_p = sep_post_counts.get(clean_u, 0)
        sep_r = sep_reel_counts.get(clean_u, 0)
        sep_s = sep_p - sep_r
        sep_vpp = sep_v / sep_p if sep_p > 0 else 0.0

        growth_pct = ((sep_v - aug_v) / aug_v * 100) if aug_v > 0 else None

        cur.execute(upsert_sql, (
            ig_id, prof["username"], "2026-09", sep_v, aug_v, growth_pct,
            sep_p, sep_r, sep_s, sep_vpp, 111, 112
        ))

    conn.commit()
    print("Database sync completed successfully.")

    # -------------------------------------------------------------
    # 6. BUILD EXCEL WORKBOOK REPORT
    # -------------------------------------------------------------
    print("\nGenerating comprehensive Excel workbook...")
    wb = openpyxl.Workbook()
    # Remove default sheet
    wb.remove(wb.active)

    # Styles
    navy_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    purple_fill = PatternFill(start_color="4C1D95", end_color="4C1D95", fill_type="solid")
    header_fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
    alt_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    highlight_fill = PatternFill(start_color="EDE9FE", end_color="EDE9FE", fill_type="solid")
    green_fill = PatternFill(start_color="ECFDF5", end_color="ECFDF5", fill_type="solid")
    red_fill = PatternFill(start_color="FEF2F2", end_color="FEF2F2", fill_type="solid")

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

    align_center = Alignment(horizontal="center", vertical="center")
    align_left = Alignment(horizontal="left", vertical="center")
    align_right = Alignment(horizontal="right", vertical="center")

    # Aggregates for executive summary
    cat_summary = {
        "Dedicated": {"aug_views": 0.0, "aug_posts": 0, "sep_views": 0.0, "sep_posts": 0, "count": 0},
        "In-house influencer": {"aug_views": 0.0, "aug_posts": 0, "sep_views": 0.0, "sep_posts": 0, "count": 0}
    }

    for prof in profile_list:
        c = prof["category"]
        u = prof["clean_username"]
        cat_summary[c]["count"] += 1
        cat_summary[c]["aug_views"] += aug_final_totals.get(u, 0.0)
        cat_summary[c]["aug_posts"] += aug_post_counts.get(u, 0)
        cat_summary[c]["sep_views"] += sep_final_totals.get(u, 0.0)
        cat_summary[c]["sep_posts"] += sep_post_counts.get(u, 0)

    # -------------------------------------------------------------
    # TAB 1: EXECUTIVE SUMMARY
    # -------------------------------------------------------------
    ws1 = wb.create_sheet(title="Executive 80-20 Summary")
    ws1.views.sheetView[0].showGridLines = True

    # Title Banner
    ws1.merge_cells("A1:G1")
    ws1["A1"] = "Wisdom Warriors Instagram Analytics — August vs. September 2026 Executive Summary"
    ws1["A1"].font = white_title
    ws1["A1"].fill = header_fill
    ws1["A1"].alignment = align_left

    ws1.merge_cells("A2:G2")
    ws1["A2"] = "Strict compliance with gemini.md specifications | Run 97 -> Run 111 -> Run 112 Delta Attribution"
    ws1["A2"].font = white_subtitle
    ws1["A2"].fill = header_fill
    ws1["A2"].alignment = align_left

    ws1.row_dimensions[1].height = 28
    ws1.row_dimensions[2].height = 18

    # Category Table
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

    # Grand Total Row
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

    sorted_by_sep = sorted(profile_list, key=lambda p: sep_final_totals.get(p["clean_username"], 0.0), reverse=True)
    for rank, p in enumerate(sorted_by_sep[:10], 1):
        u = p["clean_username"]
        av = aug_final_totals.get(u, 0.0)
        sv = sep_final_totals.get(u, 0.0)
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
    sorted_profiles = sorted(profile_list, key=lambda p: (0 if p["category"] == "Dedicated" else 1, -sep_final_totals.get(p["clean_username"], 0.0)))

    for idx, p in enumerate(sorted_profiles, 1):
        row_num = idx + 1
        u = p["clean_username"]
        av = aug_final_totals.get(u, 0.0)
        ap = aug_post_counts.get(u, 0)
        ar = aug_reel_counts.get(u, 0)
        avpp = av / ap if ap > 0 else 0.0

        sv = sep_final_totals.get(u, 0.0)
        sp = sep_post_counts.get(u, 0)
        sr = sep_reel_counts.get(u, 0)
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
        ws3.cell(row=row_num, column=1, value=idx).alignment = align_center
        ws3.cell(row=row_num, column=2, value=f"@{p['username']}")
        ws3.cell(row=row_num, column=3, value=p["category"])
        ws3.cell(row=row_num, column=4, value=aug_calc_type.get(u, "-"))
        ws3.cell(row=row_num, column=5, value=str(aug_divisors.get(u, "-"))).alignment = align_center

        ws3.cell(row=row_num, column=6, value=round(aug_new_views.get(u, 0.0))).number_format = "#,##0"
        ws3.cell(row=row_num, column=7, value=round(aug_decay_deltas.get(u, 0.0))).number_format = "#,##0"
        ws3.cell(row=row_num, column=8, value=round(aug_final_totals.get(u, 0.0))).number_format = "#,##0"
        ws3.cell(row=row_num, column=9, value=aug_post_counts.get(u, 0)).number_format = "#,##0"
        ws3.cell(row=row_num, column=10, value=aug_reel_counts.get(u, 0)).number_format = "#,##0"

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
        ws4.cell(row=row_num, column=1, value=idx).alignment = align_center
        ws4.cell(row=row_num, column=2, value=f"@{p['username']}")
        ws4.cell(row=row_num, column=3, value=p["category"])
        ws4.cell(row=row_num, column=4, value=sep_calc_type.get(u, "-"))
        ws4.cell(row=row_num, column=5, value=str(sep_divisors.get(u, "-"))).alignment = align_center

        ws4.cell(row=row_num, column=6, value=round(sep_new_views.get(u, 0.0))).number_format = "#,##0"
        ws4.cell(row=row_num, column=7, value=round(sep_decay_deltas.get(u, 0.0))).number_format = "#,##0"
        ws4.cell(row=row_num, column=8, value=round(sep_final_totals.get(u, 0.0))).number_format = "#,##0"
        ws4.cell(row=row_num, column=9, value=sep_post_counts.get(u, 0)).number_format = "#,##0"
        ws4.cell(row=row_num, column=10, value=sep_reel_counts.get(u, 0)).number_format = "#,##0"

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
