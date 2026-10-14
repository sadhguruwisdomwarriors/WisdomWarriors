import os
import shutil
import subprocess
from datetime import datetime
from backend.repositories.analytics_repo import (
    WISDOM_WARRIOR_ALLOWED_MENTIONS,
    WISDOM_WARRIOR_ALLOWED_TAGGED_USERS,
    WISDOM_WARRIOR_ALLOWED_HASHTAGS,
    WISDOM_WARRIOR_ALLOWED_CAPTION_KEYWORDS,
    _normalize_hashtag,
    _normalize_mention
)

# Categorize Hashtags for clean presentation
HASHTAG_CATEGORIES = {
    "Core & Foundation": [
        "Sadhguru", "Sadhgurujaggivasudev", "Sadguru", "Jaggi", "Isha", "Ishafoundation",
        "Ishayoga", "Ishayogacenter", "Soundsofisha", "Ishalife", "Ishaashram", "Ishaevents",
        "Ishavolunteers", "Ishakriya", "Ashramlife", "Lingaseva", "Ishausa", "Ishatamil",
        "Ishalifeindia", "Isha_foundation", "Coimbatoreashram", "Ishacrafts", "Ishahealthsolutions"
    ],
    "Programs, Initiatives & Movements": [
        "Innerengineering", "Innerengineeringonline", "Iecompletion", "Bhavaspandana",
        "Shoonyameditation", "Shoonya", "Samyama", "Sadhanapada", "Shambhavimahamudra",
        "Cauverycalling", "Savesoil", "Consciousplanet", "Consciousliving", "Consciousness",
        "Conscious", "Miracleofmind", "Climateaction", "Soilhealth", "Sustainability",
        "Consciousplanetmovement", "Innerengineeringretreat", "Savesoilmovement"
    ],
    "Consecrated Spaces, Deities & Events": [
        "Adiyogi", "Adiyogishiva", "Adhiyogi", "Dhyanalinga", "Lingabhairavi", "Bhairavi",
        "Devi", "Shiva", "Mahadev", "Mahashivratri", "Shivaratri", "Gurupoornima", "Gurupurnima",
        "Rudraksha", "Rudraksh", "Kailash", "Kailashwithsadhguru", "Kailashwithsadhguru2026",
        "Kailashyatra", "Kailashmansarovar", "Kashi", "Sacredspaces", "Bhairaviyantra",
        "Adiyogi_statue", "Adiyogistatue", "Adiyogitemple", "Dhyanalingatemple",
        "Lingabhairaviseva", "Shivamantra", "Shivashiva", "Msrww26", "Mahashivratri2026",
        "Ishamahashivratri2026", "Kalabhairava", "Krishna", "Shakti", "Humansofisha",
        "Sadhguruinlucknow", "Shiv", "Grace", "Guru", "Mysticsmusings", "Sadhgurumargam"
    ],
    "Classical Hatha Yoga & Practices": [
        "Yoga", "Hathayoga", "Classicalhathayoga", "Kaalahathayoga", "Ishahathayoga", "Suryakriya",
        "Suryashakti", "Angamardana", "Bhutashuddhi", "Upayoga", "Yogasanas", "Kriyayoga",
        "Kriya", "Asana", "Mudra", "Pranayama", "Prana", "Kundalini", "Chakra", "Meditation",
        "Meditationpractice", "Guidedmeditation", "Yogapractice", "Spiritualpractice",
        "Dailysadhana", "Sadhana", "Energybody", "Spirituality", "Sadhguruquotes",
        "Sadhguruwisdom", "Sanatandharma", "Omnamahshivaya", "Yogi", "Yogini", "Yogis",
        "Yogic", "Yogicscience", "Yogicdiet", "Sattvicfood", "Mantra", "Satsang", "Darshan",
        "Samadhi", "Mukti", "Moksha", "Vairagya", "Bhakti", "Karma", "Shambho", "Kalaripayattu",
        "Dailyyoga", "Yogaclasses", "Travelingyogi", "Dailymobility", "Breathworkhealing",
        "Yogicharya", "Ayurveda"
    ],
    "States of Being & Growth": [
        "Innerpeace", "Bliss", "Joyfulliving", "Mindfulness", "Selfawareness", "Selfrealization",
        "Innergrowth", "Innertransformation", "Spiritualawakening", "Wellbeing", "Awakening",
        "Enlightenment", "Transformation", "Stillness", "Silence", "Devotion", "Gratitude",
        "Divineenergy", "Presence", "Awareness", "Culture", "Feminine", "Spiritualjourney",
        "Spiritualgrowth", "Spiritualwisdom", "Innerjourney", "Innerwellbeing", "Selfgrowth",
        "Openingheart", "Successmindset"
    ],
    "Outreach, Events & Regional": [
        "Ishagramotsavam", "Ishagramotsavam2026", "Gramotsavam", "Sportingspiritofbharat",
        "Ruralsports", "Nepalflood", "Nepalfloods", "Nepalflashfloods", "Nagapanchami",
        "Sadhguruinmalaysia2026", "Sadhguru360", "Sadhgurulatest", "Sadhgurutamil",
        "Sadhgurutelugu", "Sadhguruhindi", "Sadhgurukannada", "Sadhgurumarathi",
        "Sadhgurumalayalam", "Sadhgurubangla", "ஈஷா"
    ]
}

# Categorize Caption Keywords for clean presentation
CAPTION_CATEGORIES = {
    "Foundation & Core": [
        "Isha", "Ishafoundation", "Isha Foundation", "Ishayoga", "Isha Yoga", "Ishayogacenter",
        "Isha Yoga Center", "Sounds of Isha", "Soundsofisha", "Isha Volunteers", "Isha Life",
        "Isha Ashram", "Isha Events", "Sacred Spaces", "Ashram Life", "Coimbatore Ashram",
        "Linga Seva", "Kala Bhairava", "Kalabhairava", "Humans of Isha", "Guru Purnima",
        "Isha Hatha Yoga", "Shakti", "Ayurveda"
    ],
    "Sadhguru & Wisdom": [
        "Sadhguru", "Sadguru", "Sadhgurujaggivasudev", "Sadhguru Jaggi Vasudev", "Jaggi",
        "Sadhguru Quotes", "Sadhguruquotes", "Sadhguru Wisdom", "Sadhguruwisdom",
        "Sadhguru Latest", "Sadhguru 360"
    ],
    "Programs, Initiatives & Movements": [
        "Inner Engineering", "Innerengineering", "Inner Engineering Online", "IE Completion",
        "Bhava Spandana", "Bhavaspandana", "Shoonya Meditation", "Shoonyameditation",
        "Shoonya", "Samyama", "Sadhanapada", "Shambhavi Mahamudra", "Isha Kriya",
        "Chith Shakti", "Cauvery Calling", "Cauverycalling", "Save Soil", "Savesoil",
        "Conscious Planet", "Consciousplanet", "Conscious Living", "Consciousliving",
        "Consciousness", "Conscious", "Miracle of Mind", "Miracleofmind"
    ],
    "Consecrated Spaces, Deities & Events": [
        "Adiyogi", "Adiyogi Shiva", "Adiyogishiva", "Dhyanalinga", "Linga Bhairavi",
        "Lingabhairavi", "Bhairavi", "Bhairavi Stuti", "Linga Bhairavi Stuti", "Bhairavi Utsav",
        "Bhairavi Yantra", "Devi", "Shiva", "Mahadev", "Mahashivratri", "Shivaratri",
        "Guru Poornima", "Rudraksha", "Kashi Yatra", "Kailash Manasarovar", "Kailash with Sadhguru",
        "Kailash Yatra", "Kailash Mansarovar", "Divine Energy", "Sanatan Dharma", "Om Namah Shivaya",
        "Naga Panchami", "Nepal Flood", "Nepal Floods", "Nepalflood", "Nepalfloods"
    ],
    "Classical Hatha Yoga & Practices": [
        "Yoga", "Hatha Yoga", "Hathayoga", "Classical Hatha Yoga", "Surya Kriya", "Surya Shakti",
        "Angamardana", "Bhuta Shuddhi", "Upa Yoga", "Yogasanas", "Kriya Yoga", "Kriyayoga",
        "Kriya", "Asana", "Mudra", "Pranayama", "Prana", "Kundalini", "Chakra", "Meditation",
        "Meditation Practice", "Guided Meditation", "Yoga Practice", "Spiritual Practice",
        "Daily Sadhana", "Sadhana", "Energy Body", "Spirituality", "Yogic Science",
        "Yogic Diet", "Sattvic Food", "Shambho", "Kalaripayattu", "Daily Yoga", "Mantra",
        "Satsang", "Darshan", "Samadhi", "Mukti", "Moksha", "Vairagya", "Bhakti", "Consecrated"
    ],
    "States of Being & Growth": [
        "Inner Peace", "Peace of Mind", "Inner Growth", "Inner Transformation", "Spiritual Awakening",
        "Self Realization", "Inner Wellbeing", "Higher Self", "Bliss", "Joyful Living",
        "Mindfulness", "Self Awareness", "Awakening", "Enlightenment", "Transformation",
        "Stillness", "Silence", "Devotion", "Gratitude", "Presence", "Awareness", "Culture",
        "Feminine", "Spiritual Journey", "Spiritual Growth", "Spiritual Wisdom", "Self Growth",
        "Opening Heart"
    ],
    "Outreach, Events & Sports": [
        "Ishagramotsavam", "Gramotsavam", "Sporting Spirit of Bharat", "Rural Sports"
    ],
    "Native Regional Language Scripts": [
        "Tamil: ஈஷா, சத்குரு",
        "Hindi / Sanskrit: ईशा, सद्गुरु, महादेव, शिव, देवी",
        "Telugu: ఇషా, సద్గురు",
        "Kannada: ಇಶಾ, ಸದ್ಗುರು",
        "Malayalam: ഇഷ, സദ്‍ഗുരു"
    ]
}

def generate_html():
    now_str = datetime.now().strftime("%B %d, %Y")
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Wisdom Warriors — Master Instagram Filter Taxonomy</title>
<style>
  @page {{
    size: A4;
    margin: 1.2cm;
    @bottom-right {{
      content: counter(page) " of " counter(pages);
      font-size: 8pt;
      color: #666;
    }}
  }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    color: #1a202c;
    background: #ffffff;
    line-height: 1.45;
    font-size: 9.5pt;
    margin: 0;
    padding: 0;
  }}
  .header {{
    border-bottom: 2px solid #800020;
    padding-bottom: 12px;
    margin-bottom: 18px;
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
  }}
  .title-group h1 {{
    color: #800020;
    font-size: 19pt;
    margin: 0 0 4px 0;
    letter-spacing: -0.5px;
  }}
  .title-group p {{
    color: #4a5568;
    font-size: 9.5pt;
    margin: 0;
    font-weight: 500;
  }}
  .meta-badge {{
    text-align: right;
    font-size: 8pt;
    color: #718096;
  }}
  .meta-badge strong {{
    color: #2d3748;
    display: block;
    font-size: 9pt;
  }}
  
  .summary-grid {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 10px;
    margin-bottom: 20px;
  }}
  .summary-card {{
    background: #f7fafc;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    padding: 8px 12px;
    text-align: center;
  }}
  .summary-card .num {{
    font-size: 15pt;
    font-weight: 700;
    color: #800020;
    display: block;
  }}
  .summary-card .label {{
    font-size: 7.5pt;
    text-transform: uppercase;
    font-weight: 600;
    color: #4a5568;
    letter-spacing: 0.5px;
  }}

  .rule-box {{
    background: #fffaf0;
    border-left: 4px solid #dd6b20;
    padding: 8px 12px;
    margin-bottom: 20px;
    font-size: 8.5pt;
    color: #7b341e;
    border-radius: 0 4px 4px 0;
  }}
  .rule-box strong {{
    color: #9c4221;
  }}

  h2 {{
    color: #2d3748;
    font-size: 12pt;
    border-bottom: 1px solid #e2e8f0;
    padding-bottom: 4px;
    margin: 18px 0 10px 0;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }}
  h2 .badge {{
    background: #800020;
    color: #ffffff;
    font-size: 7.5pt;
    padding: 2px 7px;
    border-radius: 10px;
    font-weight: 600;
  }}

  h3 {{
    color: #4a5568;
    font-size: 9.5pt;
    margin: 12px 0 6px 0;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    font-weight: 700;
  }}

  .pills-container {{
    display: flex;
    flex-wrap: wrap;
    gap: 4px 6px;
    margin-bottom: 10px;
  }}
  .pill {{
    background: #edf2f7;
    border: 1px solid #cbd5e0;
    border-radius: 4px;
    padding: 2px 6px;
    font-size: 8pt;
    color: #2d3748;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    display: inline-block;
  }}
  .pill.highlight {{
    background: #feebc8;
    border-color: #fbd38d;
    color: #7b341e;
    font-weight: 600;
  }}
  .pill.mention {{
    background: #ebf8ff;
    border-color: #bee3f8;
    color: #2b6cb0;
    font-weight: 600;
  }}

  .table-grid {{
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 15px;
    font-size: 8.5pt;
  }}
  .table-grid th, .table-grid td {{
    border: 1px solid #e2e8f0;
    padding: 6px 8px;
    text-align: left;
  }}
  .table-grid th {{
    background: #f7fafc;
    color: #4a5568;
    font-weight: 600;
    font-size: 8pt;
  }}
  .table-grid tr:nth-child(even) {{
    background: #fafafa;
  }}

  .page-break {{
    page-break-before: always;
  }}
</style>
</head>
<body>

<div class="header">
  <div class="title-group">
    <h1>Wisdom Warriors — Master Filter Taxonomy</h1>
    <p>Single Source of Truth for Instagram Content Classification</p>
  </div>
  <div class="meta-badge">
    <strong>System Specification: v2.4</strong>
    Published: {now_str}
  </div>
</div>

<div class="summary-grid">
  <div class="summary-card">
    <span class="num">{len(WISDOM_WARRIOR_ALLOWED_HASHTAGS)}</span>
    <span class="label">Allowed Hashtags</span>
  </div>
  <div class="summary-card">
    <span class="num">{len(WISDOM_WARRIOR_ALLOWED_CAPTION_KEYWORDS)}</span>
    <span class="label">Caption Keywords</span>
  </div>
  <div class="summary-card">
    <span class="num">{len(WISDOM_WARRIOR_ALLOWED_MENTIONS)}</span>
    <span class="label">Allowed Mentions</span>
  </div>
  <div class="summary-card">
    <span class="num">{len(WISDOM_WARRIOR_ALLOWED_TAGGED_USERS)}</span>
    <span class="label">Tagged Handles</span>
  </div>
</div>

<div class="rule-box">
  <strong>CHANNEL CLASSIFICATION ARCHITECTURE:</strong><br>
  • <strong>Dedicated Channels (category = 'Dedicated'):</strong> 100% of all reels are credited unconditionally without running any keyword or hashtag checks.<br>
  • <strong>In-House Influencer Channels (category = 'In-house influencer'):</strong> Must match at least <strong>one</strong> allowed hashtag, caption keyword, mention, or tagged user. Personal / unrelated reels are strictly excluded.
</div>

<h2>1. Allowed Mentions & Tagged Users <span class="badge">10 Official Handles</span></h2>
<p style="font-size: 8.5pt; color: #4a5568; margin-top: -4px;">
  Reels mentioning (@) or tagging any of these official accounts pass the verified content filter automatically (case-insensitive, '@' stripped).
</p>
<div class="pills-container">
"""
    for m in WISDOM_WARRIOR_ALLOWED_MENTIONS:
        html += f'  <span class="pill mention">@{m}</span>\n'
    html += """</div>

<h2>2. Complete Allowed Hashtags <span class="badge">195 Hashtags</span></h2>
<p style="font-size: 8.5pt; color: #4a5568; margin-top: -4px;">
  Matched normalized (case-insensitive, whitespace removed, leading '#' stripped).
</p>
"""

    for cat_name, tags in HASHTAG_CATEGORIES.items():
        html += f"<h3>{cat_name} ({len(tags)})</h3>\n"
        html += '<div class="pills-container">\n'
        for t in tags:
            html += f'  <span class="pill">#{t}</span>\n'
        html += '</div>\n'

    html += """
<div class="page-break"></div>

<div class="header">
  <div class="title-group">
    <h1>Wisdom Warriors — Master Filter Taxonomy</h1>
    <p>Caption Keywords & Native Regional Language Taxonomies</p>
  </div>
  <div class="meta-badge">
    <strong>Section 2</strong>
    Page 2 of 2
  </div>
</div>

<h2>3. Complete Allowed Caption Keywords <span class="badge">178 Keywords</span></h2>
<p style="font-size: 8.5pt; color: #4a5568; margin-top: -4px;">
  Matched as case-insensitive substrings against the entire post caption text.
</p>
"""

    for cat_name, kws in CAPTION_CATEGORIES.items():
        html += f"<h3>{cat_name} ({len(kws)})</h3>\n"
        html += '<div class="pills-container">\n'
        for kw in kws:
            html += f'  <span class="pill highlight">{kw}</span>\n'
        html += '</div>\n'

    html += """
<h2>4. Verification & Technical Matching Specification</h2>
<table class="table-grid">
  <thead>
    <tr>
      <th style="width: 25%;">Filter Type</th>
      <th style="width: 35%;">Matching Mechanism</th>
      <th>Code Reference</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><strong>Hashtags</strong></td>
      <td>Casefold match with leading <code>#</code> and internal whitespaces stripped. Exact match against set.</td>
      <td><code>backend/repositories/analytics_repo.py: check_post_matches_filters</code></td>
    </tr>
    <tr>
      <td><strong>Caption Keywords</strong></td>
      <td>Casefold substring search across full caption string. Matches phrases and multi-word terms.</td>
      <td><code>backend/repositories/analytics_repo.py</code></td>
    </tr>
    <tr>
      <td><strong>Mentions & Tagged</strong></td>
      <td>Extracted handles with leading <code>@</code> stripped, matched case-insensitively.</td>
      <td><code>backend/repositories/analytics_repo.py</code></td>
    </tr>
    <tr>
      <td><strong>Multi-Language</strong></td>
      <td>Direct Unicode script matching for Tamil, Hindi/Sanskrit, Telugu, Kannada, Malayalam.</td>
      <td><code>backend/repositories/analytics_repo.py</code></td>
    </tr>
  </tbody>
</table>

</body>
</html>
"""
    return html

def main():
    html_content = generate_html()
    
    html_file = "/Users/sadhguruwisdomwarrior/.gemini/antigravity/scratch/WisdomWarriors/scratch/taxonomy.html"
    os.makedirs(os.path.dirname(html_file), exist_ok=True)
    with open(html_file, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"Generated HTML at: {html_file}")
    
    # Target PDF paths
    pdf_downloads = "/Users/sadhguruwisdomwarrior/Downloads/Wisdom_Warriors_Instagram_Allowed_Taxonomy.pdf"
    pdf_scratch = "/Users/sadhguruwisdomwarrior/.gemini/antigravity/scratch/WisdomWarriors/Wisdom_Warriors_Instagram_Allowed_Taxonomy.pdf"
    pdf_brain = "/Users/sadhguruwisdomwarrior/.gemini/antigravity/brain/da87c5c7-cae1-4727-8648-8c431ee707c7/Wisdom_Warriors_Instagram_Allowed_Taxonomy.pdf"
    
    # Run Chrome headless to create PDF
    cmd = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "--headless",
        "--disable-gpu",
        f"--print-to-pdf={pdf_scratch}",
        html_file
    ]
    print("Compiling PDF with Google Chrome Headless...")
    subprocess.run(cmd, check=True)
    print(f"Successfully compiled PDF: {pdf_scratch}")
    
    # Copy to Downloads and Brain
    shutil.copyfile(pdf_scratch, pdf_downloads)
    print(f"Copied to Downloads: {pdf_downloads}")
    
    shutil.copyfile(pdf_scratch, pdf_brain)
    print(f"Copied to Artifacts: {pdf_brain}")
    
    print("\nALL TASKS COMPLETED SUCCESSFULLY!")

if __name__ == "__main__":
    main()
