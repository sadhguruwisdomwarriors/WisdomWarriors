import asyncio
import json
import ssl
import urllib.request
import urllib.parse
from datetime import datetime
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# SSL context
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

SUPABASE_URL = "https://juxvmzccqbroqcoleobp.supabase.co"
SERVICE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imp1eHZtemNjcWJyb3Fjb2xlb2JwIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NDY1MjE0OSwiZXhwIjoyMDkwMjI4MTQ5fQ.ayuLBYZbPhxv3DBUVvlcSX0y-0zlXSBl6jTBMkCWekE"
headers = {"apikey": SERVICE_KEY, "Authorization": f"Bearer {SERVICE_KEY}", "Content-Type": "application/json"}

from backend.services.youtube_read_service import calculate_youtube_monthly_metrics

def fetch_rest(endpoint: str):
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, context=ctx) as r:
        return json.loads(r.read().decode("utf-8"))

async def generate_centered_report():
    print("Fetching data from Supabase...")
    units = fetch_rest("micro_units?select=*&order=unit_number.asc")
    creators = fetch_rest("micro_unit_creators?select=*&order=name.asc")
    channels = fetch_rest("micro_unit_channels?select=*")
    ig_metrics = fetch_rest("monthly_channel_metrics?select=*&year_month=in.(\"2026-08\",\"2026-09\")")
    users = fetch_rest("users?select=id,full_name,email")

    user_map = {u["id"]: u["full_name"] for u in users}

    # Map Instagram metrics by instagram_id and username
    ig_map = {}
    for m in ig_metrics:
        if m.get("instagram_id"):
            ig_id = str(m["instagram_id"]).strip()
            if ig_id not in ig_map:
                ig_map[ig_id] = {}
            ig_map[ig_id][m["year_month"]] = m
        if m.get("username"):
            u_key = str(m["username"]).strip().lower().lstrip("@")
            if u_key not in ig_map:
                ig_map[u_key] = {}
            ig_map[u_key][m["year_month"]] = m

    yt_channel_ids = [
        c["username"] for c in channels 
        if (c.get("platform") or "INSTAGRAM").upper() == "YOUTUBE"
    ]
    print(f"Calculating YouTube monthly metrics for {len(yt_channel_ids)} channels...")
    yt_aug = await calculate_youtube_monthly_metrics(yt_channel_ids, 2026, 8)
    yt_sep = await calculate_youtube_monthly_metrics(yt_channel_ids, 2026, 9)

    unit_creators_map = {}
    for cr in creators:
        u_id = cr["micro_unit_id"]
        if u_id not in unit_creators_map:
            unit_creators_map[u_id] = []
        unit_creators_map[u_id].append(cr["name"])

    unit_channels_map = {}
    for ch in channels:
        u_id = ch["micro_unit_id"]
        if u_id not in unit_channels_map:
            unit_channels_map[u_id] = []
        unit_channels_map[u_id].append(ch)

    processed_units = []
    grand_aug_views = 0.0
    grand_sep_views = 0.0
    grand_aug_posts = 0
    grand_sep_posts = 0

    for u in units:
        u_id = u["id"]
        poc_name = user_map.get(u.get("poc_user_id")) or "Unassigned"
        unit_chs = unit_channels_map.get(u_id, [])
        explicit_cr_names = unit_creators_map.get(u_id, [])

        creator_groups = {}
        for c_name in explicit_cr_names:
            creator_groups[c_name] = []

        for ch in unit_chs:
            c_name = (ch.get("creator_name") or ch.get("channel_title") or ch.get("username") or "Unassigned Creator").strip()
            if c_name not in creator_groups:
                creator_groups[c_name] = []
            creator_groups[c_name].append(ch)

        # Sort creators: POC FIRST, then alphabetical
        def creator_sort_key(name):
            is_poc = poc_name and name.strip().lower() == poc_name.strip().lower()
            return (0 if is_poc else 1, name.lower())

        sorted_creator_names = sorted(creator_groups.keys(), key=creator_sort_key)

        creators_list = []
        unit_aug_views = 0.0
        unit_sep_views = 0.0
        unit_aug_posts = 0
        unit_sep_posts = 0

        for cr_name in sorted_creator_names:
            ch_list = creator_groups[cr_name]
            is_poc = bool(poc_name and cr_name.strip().lower() == poc_name.strip().lower())
            
            cr_channels_data = []
            cr_aug_views = 0.0
            cr_sep_views = 0.0
            cr_aug_posts = 0
            cr_sep_posts = 0

            yt_channel_names = []
            ig_channel_names = []

            for ch in ch_list:
                platform = (ch.get("platform") or "INSTAGRAM").upper()
                raw_handle = ch.get("username") or ""
                clean_handle = raw_handle.lstrip("@").strip()
                title = ch.get("channel_title") or raw_handle

                aug_v = 0.0
                sep_v = 0.0
                aug_p = 0
                sep_p = 0

                if platform == "YOUTUBE":
                    m_aug = yt_aug.get(raw_handle, {})
                    m_sep = yt_sep.get(raw_handle, {})
                    aug_v = float(m_aug.get("views", 0.0) or 0.0)
                    sep_v = float(m_sep.get("views", 0.0) or 0.0)
                    aug_p = int(m_aug.get("video_count", 0) or 0)
                    sep_p = int(m_sep.get("video_count", 0) or 0)
                    title = m_aug.get("title") or title
                    yt_channel_names.append(title)
                else:
                    ig_id = str(ch.get("instagram_id") or "").strip()
                    m_aug = ig_map.get(ig_id, {}).get("2026-08") or ig_map.get(clean_handle.lower(), {}).get("2026-08")
                    m_sep = ig_map.get(ig_id, {}).get("2026-09") or ig_map.get(clean_handle.lower(), {}).get("2026-09")

                    if m_aug:
                        aug_v = float(m_aug.get("monthly_views") or 0.0)
                        aug_p = int(m_aug.get("reels_count") if m_aug.get("reels_count") is not None else (m_aug.get("post_count") or 0))
                    if m_sep:
                        sep_v = float(m_sep.get("monthly_views") or 0.0)
                        sep_p = int(m_sep.get("reels_count") if m_sep.get("reels_count") is not None else (m_sep.get("post_count") or 0))
                    ig_channel_names.append(f"@{clean_handle}")

                cr_aug_views += aug_v
                cr_sep_views += sep_v
                cr_aug_posts += aug_p
                cr_sep_posts += sep_p

                cr_channels_data.append({
                    "platform": platform,
                    "handle": f"@{clean_handle}" if platform == "INSTAGRAM" else clean_handle,
                    "title": title,
                    "aug_views": aug_v,
                    "aug_posts": aug_p,
                    "sep_views": sep_v,
                    "sep_posts": sep_p,
                    "total_views": aug_v + sep_v,
                    "total_posts": aug_p + sep_p
                })

            unit_aug_views += cr_aug_views
            unit_sep_views += cr_sep_views
            unit_aug_posts += cr_aug_posts
            unit_sep_posts += cr_sep_posts

            creators_list.append({
                "creator_name": cr_name,
                "is_poc": is_poc,
                "channels_count": len(ch_list),
                "yt_channels_str": ", ".join(yt_channel_names) if yt_channel_names else "—",
                "ig_channels_str": ", ".join(ig_channel_names) if ig_channel_names else "—",
                "channels": cr_channels_data,
                "aug_views": cr_aug_views,
                "aug_posts": cr_aug_posts,
                "sep_views": cr_sep_views,
                "sep_posts": cr_sep_posts,
                "total_views": cr_aug_views + cr_sep_views,
                "total_posts": cr_aug_posts + cr_sep_posts
            })

        grand_aug_views += unit_aug_views
        grand_sep_views += unit_sep_views
        grand_aug_posts += unit_aug_posts
        grand_sep_posts += unit_sep_posts

        processed_units.append({
            "unit_number": u.get("unit_number"),
            "name": u.get("name"),
            "poc_name": poc_name,
            "creators": creators_list,
            "total_channels": len(unit_chs),
            "aug_views": unit_aug_views,
            "aug_posts": unit_aug_posts,
            "sep_views": unit_sep_views,
            "sep_posts": unit_sep_posts,
            "total_views": unit_aug_views + unit_sep_views,
            "total_posts": unit_aug_posts + unit_sep_posts
        })

    # ---------------- BUILD EXCEL WORKBOOK ----------------
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Micro Units Performance"
    ws.views.sheetView[0].showGridLines = True

    # Styling Palette
    c_banner_bg = "1E1B4B"       # Deep Purple-Navy
    c_tbl_header = "4C1D95"      # Deep Purple Header
    c_sec_header = "31104B"      # Dark Violet Section
    c_zebra = "F8FAFC"           # Light Slate
    c_unit_header_bg = "EDE9FE"  # Soft Lavender for Unit Title
    c_poc_bg = "FAF5FF"          # Light Purple for POC Row
    c_poc_badge_bg = "6B21A8"    # Purple for POC Badge text
    c_total_bg = "FEF3C7"        # Amber for Totals
    c_grand_total_bg = "FDE68A"  # Amber 200

    font_title = Font(name="Calibri", size=16, bold=True, color="FFFFFF")
    font_subtitle = Font(name="Calibri", size=10, italic=True, color="E0E7FF")
    font_kpi_label = Font(name="Calibri", size=9, bold=True, color="4B5563")
    font_kpi_val = Font(name="Calibri", size=14, bold=True, color="1E1B4B")
    font_sec_header = Font(name="Calibri", size=12, bold=True, color="FFFFFF")
    font_tbl_header = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
    
    font_data = Font(name="Calibri", size=10)
    font_data_poc = Font(name="Calibri", size=10, bold=True, color="4C1D95")
    font_data_bold = Font(name="Calibri", size=10, bold=True)
    font_unit_header = Font(name="Calibri", size=11, bold=True, color="2E1065")
    font_unit_subtotal = Font(name="Calibri", size=10, bold=True, color="31104B")
    font_grand_total = Font(name="Calibri", size=11, bold=True, color="78350F")

    fill_banner = PatternFill(start_color=c_banner_bg, end_color=c_banner_bg, fill_type="solid")
    fill_tbl_header = PatternFill(start_color=c_tbl_header, end_color=c_tbl_header, fill_type="solid")
    fill_sec_header = PatternFill(start_color=c_sec_header, end_color=c_sec_header, fill_type="solid")
    fill_zebra = PatternFill(start_color=c_zebra, end_color=c_zebra, fill_type="solid")
    fill_unit_header = PatternFill(start_color=c_unit_header_bg, end_color=c_unit_header_bg, fill_type="solid")
    fill_poc_row = PatternFill(start_color=c_poc_bg, end_color=c_poc_bg, fill_type="solid")
    fill_unit_subtotal = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
    fill_grand_total = PatternFill(start_color=c_grand_total_bg, end_color=c_grand_total_bg, fill_type="solid")

    thin_border = Side(style='thin', color='D1D5DB')
    thick_top = Side(style='medium', color='4C1D95')
    double_bottom = Side(style='double', color='1E1B4B')

    border_cell = Border(left=thin_border, right=thin_border, top=thin_border, bottom=thin_border)
    border_unit_subtotal = Border(left=thin_border, right=thin_border, top=thin_border, bottom=thin_border)
    border_grand_total = Border(left=thin_border, right=thin_border, top=thick_top, bottom=double_bottom)

    # STRICT CENTER ALIGNMENT FOR ALL VALUES AS REQUESTED
    align_center = Alignment(horizontal="center", vertical="center", wrap_text=True)

    num_fmt_int = "#,##0"
    num_fmt_views = "#,##0"
    num_fmt_pct = "0.0%"

    TOTAL_COLS = 12
    row_idx = 1

    # 1. TITLE BANNER
    ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx+1, end_column=TOTAL_COLS)
    b_cell = ws.cell(row=row_idx, column=1, value="Sadhguru Wisdom Warriors — Micro Units Performance Report")
    b_cell.font = font_title
    b_cell.alignment = align_center
    for r in range(row_idx, row_idx+2):
        for c in range(1, TOTAL_COLS+1):
            ws.cell(row=r, column=c).fill = fill_banner
    row_idx += 2

    ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=TOTAL_COLS)
    sub_cell = ws.cell(row=row_idx, column=1, value=f"August 2026 & September 2026 Reach Across All 11 Micro Units | Generated: {datetime.now().strftime('%B %d, %Y')}")
    sub_cell.font = font_subtitle
    sub_cell.alignment = align_center
    for c in range(1, TOTAL_COLS+1):
        ws.cell(row=row_idx, column=c).fill = fill_banner
    row_idx += 2

    # 2. EXECUTIVE KPI CARDS (Centered)
    kpis = [
        ("TOTAL UNITS", len(processed_units), num_fmt_int),
        ("TOTAL CREATORS", sum(len(u["creators"]) for u in processed_units), num_fmt_int),
        ("TOTAL CHANNELS", sum(u["total_channels"] for u in processed_units), num_fmt_int),
        ("AUG 2026 TOTAL VIEWS", grand_aug_views, num_fmt_views),
        ("SEP 2026 TOTAL VIEWS", grand_sep_views, num_fmt_views),
        ("COMBINED TOTAL VIEWS", grand_aug_views + grand_sep_views, num_fmt_views),
    ]

    col_start = 1
    for label, val, fmt in kpis:
        c1, c2 = col_start, col_start + 1
        ws.merge_cells(start_row=row_idx, start_column=c1, end_row=row_idx, end_column=c2)
        ws.merge_cells(start_row=row_idx+1, start_column=c1, end_row=row_idx+1, end_column=c2)

        l_cell = ws.cell(row=row_idx, column=c1, value=label)
        l_cell.font = font_kpi_label
        l_cell.alignment = align_center
        l_cell.fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")

        v_cell = ws.cell(row=row_idx+1, column=c1, value=val)
        v_cell.font = font_kpi_val
        v_cell.number_format = fmt
        v_cell.alignment = align_center
        v_cell.fill = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")

        for r in range(row_idx, row_idx+2):
            for c in range(c1, c2+1):
                ws.cell(row=r, column=c).border = border_cell

        col_start += 2

    row_idx += 3

    # 3. EXECUTIVE SUMMARY TABLE (All numbers and values centered)
    ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=TOTAL_COLS)
    s_title = ws.cell(row=row_idx, column=1, value="1. EXECUTIVE SUMMARY — ALL 11 MICRO UNITS MATRIX")
    s_title.font = font_sec_header
    s_title.fill = fill_sec_header
    s_title.alignment = align_center
    for c in range(1, TOTAL_COLS+1):
        ws.cell(row=row_idx, column=c).fill = fill_sec_header
    row_idx += 1

    summary_headers = [
        "Unit #", "Micro Unit Name", "Assigned POC", "Creators", "Channels", 
        "Aug 2026 Views", "Aug Content Items", "Sep 2026 Views", "Sep Content Items", 
        "Total Views (Aug+Sep)", "Total Content Items", "% of Overall Reach"
    ]
    for col_i, h in enumerate(summary_headers, start=1):
        cell = ws.cell(row=row_idx, column=col_i, value=h)
        cell.font = font_tbl_header
        cell.fill = fill_tbl_header
        cell.alignment = align_center
        cell.border = border_cell
    row_idx += 1

    sum_start_row = row_idx
    combined_grand_views = grand_aug_views + grand_sep_views

    for idx, u in enumerate(processed_units):
        pct = (u["total_views"] / combined_grand_views) if combined_grand_views > 0 else 0
        fill_row = fill_zebra if idx % 2 == 1 else PatternFill(fill_type=None)

        vals = [
            (u["unit_number"], num_fmt_int),
            (u["name"], "@"),
            (u["poc_name"], "@"),
            (len(u["creators"]), num_fmt_int),
            (u["total_channels"], num_fmt_int),
            (u["aug_views"], num_fmt_views),
            (u["aug_posts"], num_fmt_int),
            (u["sep_views"], num_fmt_views),
            (u["sep_posts"], num_fmt_int),
            (u["total_views"], num_fmt_views),
            (u["total_posts"], num_fmt_int),
            (pct, num_fmt_pct),
        ]

        for col_i, (v, fmt) in enumerate(vals, start=1):
            cell = ws.cell(row=row_idx, column=col_i, value=v)
            cell.font = font_data
            cell.number_format = fmt
            cell.alignment = align_center  # CENTER ALIGNED
            if fill_row.fill_type:
                cell.fill = fill_row
            cell.border = border_cell

        row_idx += 1

    # Summary Grand Total Row (Centered)
    sum_tot_vals = [
        ("TOTAL", "@"),
        ("All 11 Micro Units", "@"),
        ("—", "@"),
        (f"=SUM(D{sum_start_row}:D{row_idx-1})", num_fmt_int),
        (f"=SUM(E{sum_start_row}:E{row_idx-1})", num_fmt_int),
        (f"=SUM(F{sum_start_row}:F{row_idx-1})", num_fmt_views),
        (f"=SUM(G{sum_start_row}:G{row_idx-1})", num_fmt_int),
        (f"=SUM(H{sum_start_row}:H{row_idx-1})", num_fmt_views),
        (f"=SUM(I{sum_start_row}:I{row_idx-1})", num_fmt_int),
        (f"=SUM(J{sum_start_row}:J{row_idx-1})", num_fmt_views),
        (f"=SUM(K{sum_start_row}:K{row_idx-1})", num_fmt_int),
        (1.0, num_fmt_pct),
    ]

    for col_i, (v, fmt) in enumerate(sum_tot_vals, start=1):
        cell = ws.cell(row=row_idx, column=col_i, value=v)
        cell.font = font_grand_total
        cell.number_format = fmt
        cell.alignment = align_center  # CENTER ALIGNED
        cell.fill = fill_grand_total
        cell.border = border_grand_total

    row_idx += 3

    # 4. DETAILED BREAKDOWN TABLE — POC FIRST, THEN TEAM MEMBERS
    # Exactly matching user's request & UI Figure:
    # "Micro Unit 1, the POC, the POC August Views and September Views, and Number of Content. And next, the team members of the POC, their name, their total August Views and September Views."
    ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=TOTAL_COLS)
    d_title = ws.cell(row=row_idx, column=1, value="2. DETAILED BREAKDOWN — POC & TEAM MEMBERS BY MICRO UNIT")
    d_title.font = font_sec_header
    d_title.fill = fill_sec_header
    d_title.alignment = align_center
    for c in range(1, TOTAL_COLS+1):
        ws.cell(row=row_idx, column=c).fill = fill_sec_header
    row_idx += 1

    detail_headers = [
        "Micro Unit", "Role / Status", "Content Creator Name", "Channels Attached",
        "Aug 2026 Views", "Aug Content Count", "Sep 2026 Views", "Sep Content Count", 
        "Total Views (Aug+Sep)", "Total Content Items", "YouTube Channel(s)", "Instagram Handle(s)"
    ]
    for col_i, h in enumerate(detail_headers, start=1):
        cell = ws.cell(row=row_idx, column=col_i, value=h)
        cell.font = font_tbl_header
        cell.fill = fill_tbl_header
        cell.alignment = align_center
        cell.border = border_cell
    row_idx += 1

    detail_start_row = row_idx

    for u in processed_units:
        u_name = u["name"]
        poc = u["poc_name"]

        # Unit Section Separator Header Row
        ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=TOTAL_COLS)
        u_sec = ws.cell(row=row_idx, column=1, value=f"⭐ {u_name} — POC: {poc} (Total Creators: {len(u['creators'])}, Total Channels: {u['total_channels']})")
        u_sec.font = font_unit_header
        u_sec.fill = fill_unit_header
        u_sec.alignment = align_center
        for c in range(1, TOTAL_COLS+1):
            ws.cell(row=row_idx, column=c).fill = fill_unit_header
            ws.cell(row=row_idx, column=c).border = border_cell
        row_idx += 1

        # Creators inside this unit: POC is already first in u["creators"]
        for cr in u["creators"]:
            cr_name = cr["creator_name"]
            is_poc = cr["is_poc"]
            role_label = "POC" if is_poc else "Team Member"
            display_name = f"{cr_name} [POC]" if is_poc else cr_name

            row_fill = fill_poc_row if is_poc else (fill_zebra if row_idx % 2 == 1 else PatternFill(fill_type=None))
            name_font = font_data_poc if is_poc else font_data

            vals = [
                (u_name, "@"),
                (role_label, "@"),
                (display_name, "@"),
                (cr["channels_count"], num_fmt_int),
                (cr["aug_views"], num_fmt_views),
                (cr["aug_posts"], num_fmt_int),
                (cr["sep_views"], num_fmt_views),
                (cr["sep_posts"], num_fmt_int),
                (cr["total_views"], num_fmt_views),
                (cr["total_posts"], num_fmt_int),
                (cr["yt_channels_str"], "@"),
                (cr["ig_channels_str"], "@"),
            ]

            for col_i, (v, fmt) in enumerate(vals, start=1):
                cell = ws.cell(row=row_idx, column=col_i, value=v)
                cell.font = name_font if col_i in (2, 3) else font_data
                cell.number_format = fmt
                cell.alignment = align_center  # STRICT CENTER ALIGNMENT
                if row_fill.fill_type:
                    cell.fill = row_fill
                cell.border = border_cell

            row_idx += 1

        # Unit Subtotal Row (Centered)
        u_sub_vals = [
            (u_name, "@"),
            ("SUBTOTAL", "@"),
            (f"{u_name} Total ({len(u['creators'])} Members)", "@"),
            (u["total_channels"], num_fmt_int),
            (u["aug_views"], num_fmt_views),
            (u["aug_posts"], num_fmt_int),
            (u["sep_views"], num_fmt_views),
            (u["sep_posts"], num_fmt_int),
            (u["total_views"], num_fmt_views),
            (u["total_posts"], num_fmt_int),
            ("—", "@"),
            ("—", "@"),
        ]

        for col_i, (v, fmt) in enumerate(u_sub_vals, start=1):
            cell = ws.cell(row=row_idx, column=col_i, value=v)
            cell.font = font_unit_subtotal
            cell.number_format = fmt
            cell.alignment = align_center  # CENTER ALIGNED
            cell.fill = fill_unit_subtotal
            cell.border = border_unit_subtotal

        row_idx += 1

    # Final Overall Grand Total Row for Detailed Table (Centered)
    final_grand_vals = [
        ("ALL UNITS", "@"),
        ("GRAND TOTAL", "@"),
        ("All 11 Micro Units (54 Creators)", "@"),
        (sum(u["total_channels"] for u in processed_units), num_fmt_int),
        (grand_aug_views, num_fmt_views),
        (grand_aug_posts, num_fmt_int),
        (grand_sep_views, num_fmt_views),
        (grand_sep_posts, num_fmt_int),
        (grand_aug_views + grand_sep_views, num_fmt_views),
        (grand_aug_posts + grand_sep_posts, num_fmt_int),
        ("—", "@"),
        ("—", "@"),
    ]

    for col_i, (v, fmt) in enumerate(final_grand_vals, start=1):
        cell = ws.cell(row=row_idx, column=col_i, value=v)
        cell.font = font_grand_total
        cell.number_format = fmt
        cell.alignment = align_center  # CENTER ALIGNED
        cell.fill = fill_grand_total
        cell.border = border_grand_total

    # Set Column Widths (Adjusted for Center Alignment & Readability)
    column_widths = {
        1: 18,  # Micro Unit
        2: 16,  # Role / Status
        3: 28,  # Content Creator Name
        4: 18,  # Channels Attached
        5: 20,  # Aug 2026 Views
        6: 18,  # Aug Content Count
        7: 20,  # Sep 2026 Views
        8: 18,  # Sep Content Count
        9: 24,  # Total Views (Aug+Sep)
        10: 20, # Total Content Items
        11: 34, # YouTube Channel(s)
        12: 32, # Instagram Handle(s)
    }

    for col_idx_num, w in column_widths.items():
        col_letter = get_column_letter(col_idx_num)
        ws.column_dimensions[col_letter].width = w

    output_path = "/Users/sadhguruwisdomwarrior/.gemini/antigravity/scratch/WisdomWarriors/Wisdom_Warriors_Micro_Units_August_September_2026_Report.xlsx"
    wb.save(output_path)
    print(f"Report saved to {output_path}")

    # Copy to Downloads folder directly
    dl_path = "/Users/sadhguruwisdomwarrior/Downloads/Wisdom_Warriors_Micro_Units_August_September_2026_Report.xlsx"
    wb.save(dl_path)
    print(f"Report updated in Downloads: {dl_path}")

    # Copy to artifacts path
    artifact_path = "/Users/sadhguruwisdomwarrior/.gemini/antigravity/brain/da87c5c7-cae1-4727-8648-8c431ee707c7/Wisdom_Warriors_Micro_Units_August_September_2026_Report.xlsx"
    wb.save(artifact_path)
    print(f"Copied to artifact path: {artifact_path}")

if __name__ == "__main__":
    asyncio.run(generate_centered_report())
