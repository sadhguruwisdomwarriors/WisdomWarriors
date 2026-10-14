# Wisdom Warriors Instagram Analytics — Specifications, Rules & Constraints

**File Location:** `/Users/sadhguruwisdomwarrior/.gemini/antigravity/scratch/WisdomWarriors/gemini.md`  
*(Root directory of the WisdomWarriors project)*

This document serves as the **single source of truth** for the **Wisdom Warriors Instagram Web Application**. It details the business logic, channel categorization, view calculations, collaboration & co-author rules, scraper configurations, and exhaustive filter taxonomies (mentions, tagged users, hashtags, captions).

> [!IMPORTANT]
> **PERMANENT INVIOLABILITY RULE:**  
> All formulas, channel classification rules, collaboration attribution mechanics, deduplication constraints, and filter taxonomies defined in this document are **strictly fixed**.  
> **Under NO circumstances should any future feature implementation, bug fix, or refactor modify, weaken, or omit these rules without explicit, prior user instruction.**

---

## 1. Channel Classification Architecture

Every channel monitored in the system belongs to one of two categories:

### A. Dedicated Channels (`category = 'Dedicated'`)
- **Core Principle:** Channels built specifically for Sadhguru, Isha Foundation, or consecrated spiritual content (e.g., `@with_shiva`, `@sadhguru_sharings`, `@ishafoundation`).
- **Rule:** **100% of all reel views are credited without any keyword/filter checks**.
- **No Keyword Check:** Does not check hashtags, mentions, tags, or captions. All reel uploads, collaborative reels, and historical decay deltas are included automatically.

### B. In-House Influencer (IHI) Channels (`category = 'In-house influencer'`)
- **Core Principle:** Personal creators or influencers who post a mix of lifestyle/personal content and Isha/spiritual content (e.g., `@withshambhavi`, `@saritaguptaaa`).
- **Rule:** **Only reels passing the verified filter conditions are credited**.
- **Requirement:** A reel must contain at least **one** matching allowed hashtag, mention, tagged user, or caption keyword.
- **Exclusion:** Personal reels (e.g., personal vlogs, algorithm tutorials, external travel, non-Isha content) are strictly excluded from both target month uploads and historical decay delta calculations.

---

## 2. Co-Author & Collaboration Logic

For all reels involving co-authors, collaborators, or multiple producers:

### A. Core Mathematical Formulation
1. **Participants Extraction:**
   $$\text{participants} = \text{Unique}\left(\{\text{owner\_username}\} \cup \text{coauthor\_producers}\right)$$
2. **Split Factor:**
   $$\text{split\_factor} = \max\left(1, \text{len}(\text{participants})\right)$$
3. **Divided Views per Participant:**
   $$\text{divided\_views} = \frac{\text{video\_play\_count}}{\text{split\_factor}}$$

### B. Ownership & Collaboration Attribution Scenarios
Whether a monitored channel is the **original publisher/owner** or an **invited collaborator/co-author**, every divided view is credited to that particular channel:

1. **Scenario 1: Monitored Channel is the Primary Owner**
   - If our monitored channel (e.g., `@with_shiva`) posts a reel and invites external collaborator(s), `@with_shiva` receives its divided views: $\frac{\text{views}}{\text{split\_factor}}$.
2. **Scenario 2: Monitored Channel is a Collaborator on Another Post**
   - If another creator (external or tracked) posts a reel and tags our monitored channel (e.g., `@with_shiva`) as a collaborator / co-author producer, the reel appears in the scraped data under our monitored channel's feed.
   - The divided views ($\frac{\text{views}}{\text{split\_factor}}$) **strictly go into our monitored channel** (`@with_shiva`).
3. **Scenario 3: Collaboration Between Two Monitored Channels in Our Database**
   - If **both** Channel A and Channel B exist in our database and collaborate on the same reel (e.g., 2 co-authors), **both channels receive their divided views independently**.
   - Channel A gets $50\%$ of the views credited to its monthly total.
   - Channel B gets $50\%$ of the views credited to its monthly total.
4. **Scenario 4: External Collaborator Participants**
   - If an external unmonitored account is a co-author, its divided share is discarded and not tracked. It does not diminish the tracked channels' rightful divided fractions.

### C. Channel Classification Enforcement on Collaborative Reels
- **If the participant is Dedicated:** Always receives its `divided_views` unconditionally (100% of all collaborative reels).
- **If the participant is In-House Influencer (IHI):** Receives its `divided_views` **ONLY IF** the reel matches the verified filter taxonomy. If the reel fails the filter, the IHI channel receives 0 views for that reel.

### D. Multi-Feed Scraper De-duplication Protection
- When Apify scrapes multiple channels, a collaborative reel may be scraped multiple times across different channels' feeds or scrape runs.
- **Rule:** In any calculation run, reels are strictly grouped by unique `post_id`.
- For any individual channel, a reel is processed **exactly once** using its latest/highest play count for that run. A reel is **never duplicated or double-counted** for the same channel.

---

## 3. Monthly Views Calculation Architecture (6-Month Decay Window + Target Month)

For any target calculation month $M$ (e.g., August or September 2026):
- **Snapshot 1 ($S1$):** Baseline scrape run at the beginning of Month $M$ (e.g., Run 89, 97, or 111).
- **Snapshot 2 ($S2$):** Post-month scrape run at the beginning of Month $M+1$ (e.g., Run 111 or 112).

### Standard Calculation Pipeline:
1. **Target Month New Uploads ($M$):**
   - For each reel published within Month $M$:
     $$\text{Views}_{M} = S2\text{ Views}$$
2. **Prior 6 Months Decay Window ($M-1$ down to $M-6$):**
   - Evaluated under the **6-Case Master Decay Specification** below.
3. **Total Monthly Metric:**
   $$\text{Total Monthly Views} = \sum \text{Views}_{M} + \sum \Delta_{\text{prior}}$$

---

### Master Decay & Missing Data Specification (Cases 1 to 6)

When comparing $S1$ (Baseline) and $S2$ (Post-Scrape) across the prior 6-month decay window:

#### Case 1: Partial Month Drop (The `@medicine_meets_yoga` Rule)
- **Condition:** Channel has reels present in both $S1$ and $S2$, but 1 or more older reels were dropped/missed in $S2$ due to an Apify pagination cutoff ($S1 > 0$, but $S2 = 0$).
- **Rule (Decay Growth Ratio):**
  1. Calculate the channel's organic growth rate ($g$) from all its **surviving reels** (reels present in both $S1$ and $S2$):
     $$g = \frac{\sum S2_{\text{surviving}} - \sum S1_{\text{surviving}}}{\sum S1_{\text{surviving}}}$$
  2. Impute the estimated views for each dropped reel:
     $$\Delta_{\text{dropped}} = S1 \times g$$
     $$S2_{\text{estimated}} = S1 \times (1 + g)$$
  3. The dropped reel receives its proportional organic decay growth instead of falsely being wiped out to 0.

#### Case 2: Total Channel Dropout (The `@isha.persian` Rule)
- **Condition:** The scraper failed completely for an entire channel in $S2$ (e.g., Instagram bot challenge / proxy block in < 20s), resulting in 0 reels scraped across all months ($S2 = 0$).
- **Rule (S1 History Average Normalization):**
  - Because $S2$ has 0 surviving reels, calculate the channel's monthly average using its available $S1$ history:
    $$\text{Credited Monthly Views} = \frac{\text{Total } S1 \text{ Prior Window Views}}{\text{Count of Active Months in } S1}$$
  - Accurately credits the channel with its typical monthly output (e.g., $\frac{1,069,428}{6} = 178,238\text{ views}$) rather than unfairly penalizing it with 0.0 views.

#### Case 3: Reel Deleted by Creator (Creator Action)
- **Condition:** A reel was present in $S1$, but the creator deleted or archived it on Instagram before $S2$.
- **Detection:** Surrounding reels published before and after this timestamp survive in $S2$, but this specific middle reel is absent.
- **Rule:**
  $$\Delta_{\text{deleted}} = 0.0$$
  - Zero growth is credited. Creators are never credited with decay growth on content they have permanently removed.

#### Case 4: Zero or Negative Growth on Surviving Reels ($g \le 0$)
- **Condition:** Surviving old reels gained 0 new views, or Instagram made a minor downward bot audit adjustment ($S2 \le S1$).
- **Rule:**
  $$g \le 0 \implies g = 0.0\%$$
  $$\Delta_{\text{dropped}} = 0.0$$
  - The Decay Protection Rule clamps growth at `0.0`. No negative views are deducted, and no fake growth is invented.

#### Case 5: Viral Spike / Outlier Handling (Growth Rate > 5%, 10%, 15%)
- **Condition:** One or more surviving reels experience an algorithmic viral explosion, causing the raw channel growth rate to spike (> 10%).
- **Rule (Two-Tier Viral Isolation):**
  1. **Viral Reel Itself:** Receives **100% full, uncapped credit** for its entire earned spike:
     $$\Delta_{\text{viral reel}} = S2_{\text{actual}} - S1_{\text{actual}}$$
  2. **Missing / Dropped Reels:** Do **not** inherit the viral multiplier. Instead, they use the **Median Reel Growth Rate** capped at a maximum of **10.0%**:
     $$g_{\text{impute}} = \min\Big(\text{Median}(g_1, g_2, \dots, g_n), \;\; 10.0\%\Big)$$
     $$\Delta_{\text{dropped}} = S1 \times g_{\text{impute}}$$
  - Prevents viral spikes on one post from inventing unearned views on missing posts.

#### Case 6: Newly Scraped Channel (No S1 Baseline — The `@transformwith_rd` Rule)
- **Condition:** A channel is added to the system and scraped for the very first time in $S2$ ($S1 = 0$).
- **The Problem:** Because $S1 = 0$, applying $\Delta = S2 - S1$ would treat all historical cumulative views as new growth in Month $M$, causing false inflation.
- **Rule (Dynamic Active Months Divisor):**
  1. Calculate the total cumulative views across the available scraped window in $S2$ (up to prior 6 months + target month):
     $$\text{Total Window Views} = \sum_{\text{available months}} S2\text{ Views}_m$$
  2. Dynamically determine the active months from the earliest scraped month to target month (inclusive):
     $$\text{Months Divisor} = \text{Earliest Scraped Month to Target Month}$$
  3. Divide total window views by the dynamic divisor:
     $$\text{Total Monthly Views} = \frac{\text{Total Window Views}}{\text{Months Divisor}}$$
  - Example: `@transformwith_rd` had 1,482,337 views over 7 months (March to Sept) $\to \frac{1,482,337}{7} = \mathbf{211,762.43\text{ views}}$.

---

### Quick Reference Matrix

| Case | Scenario | Surviving Reels Treatment | Dropped Reels ($S2=0$) Treatment |
| :---: | :--- | :---: | :---: |
| **Case 1** | Partial pagination drop | Actual growth ($S2 - S1$) | Imputed: $S1 \times g_{\text{channel}}$ |
| **Case 2** | Total channel crawl failure | None ($S2 = 0$) | Total Credit: $\frac{\text{Total } S1}{\text{Active Months in } S1}$ |
| **Case 3** | Reel deleted by creator | Actual growth ($S2 - S1$) | $\Delta = 0.0$ |
| **Case 4** | Zero / Negative growth | $\Delta = 0.0$ (clamped) | $\Delta = 0.0$ |
| **Case 5** | Viral spike on surviving reel | **100% uncapped spike views** | Imputed: $S1 \times \text{Median}(g)$, capped at 10% |
| **Case 6** | Newly added channel ($S1=0$) | Total Window Views | Total Credit: $\frac{\text{Total } S2}{\text{Active Months}}$ |

---

## 4. Scraper Constraints & Pagination Depth

### A. Results Limit
- **Default Limit:** Set to **4,000** posts per channel across:
  - `backend/services/apify/posts_runner.py`
  - `backend/services/scrape_service.py`
  - `frontend/src/pages/Scrape/index.tsx`
- **Why 4,000 is Mandatory:** Ultra high-volume channels (e.g., `@sadhguru.archives`) post hundreds of reels per month, reaching 2,100+ reels over a 6-month window. Setting the ceiling to 4,000 ensures no active channel has its catalog truncated, while the `onlyPostsNewerThan` date window keeps compute and costs bounded for lower volume channels.

### B. Date Range Reflection & Dynamic onlyPostsNewerThan
- When `date_from` is selected in a scrape, the backend automatically converts the date range into days (`onlyPostsNewerThan`) and forwards it dynamically to the Apify Instagram Actor.

### C. Skip Pinned Posts
- **Rule:** `skipPinnedPosts: True` is **strictly retained** in Apify's `run_input` across all posts scraping runs to prevent pinned posts from distorting chronologically bounded pagination.

---

## 5. Complete Allowed Mentions (`WISDOM_WARRIOR_ALLOWED_MENTIONS`)

Matching normalized handles (stripped `@`, case-insensitive):

1. `ishafoundation`
2. `adiyogi.official`
3. `sadhguru`
4. `sadhgurutamil`
5. `sadhgurutelugu`
6. `sadhguru.hindiofficial`
7. `sadhguru.malayalam`
8. `sadhguru_marathi_official`
9. `sadhgurubangla`
10. `sadhguru_kannada_official`

---

## 6. Complete Allowed Tagged Users (`WISDOM_WARRIOR_ALLOWED_TAGGED_USERS`)

Matching tagged users in reel metadata (stripped `@`, case-insensitive):

1. `ishafoundation`
2. `adiyogi.official`
3. `sadhguru`
4. `sadhgurutamil`
5. `sadhgurutelugu`
6. `sadhguru.hindiofficial`
7. `sadhguru.malayalam`
8. `sadhguru_marathi_official`
9. `sadhgurubangla`
10. `sadhguru_kannada_official`

---

## 7. Complete Allowed Hashtags (`WISDOM_WARRIOR_ALLOWED_HASHTAGS`)

Normalized match: lowercase, whitespace removed, leading `#` stripped.

### Core & Foundation:
- `#Sadhguru`
- `#Sadhgurujaggivasudev`
- `#Sadguru`
- `#Jaggi`
- `#Isha`
- `#Ishafoundation`
- `#Ishayoga`
- `#Ishayogacenter`
- `#Soundsofisha`
- `#Ishalife`
- `#Ishaashram`
- `#Ishaevents`
- `#Ishavolunteers`
- `#Ishakriya`
- `#Ashramlife`
- `#Lingaseva`
- `#Ishausa`
- `#Ishatamil`
- `#Ishalifeindia`
- `#Isha_foundation`
- `#Coimbatoreashram`
- `#Ishacrafts`

### Programs, Initiatives & Movements:
- `#Innerengineering`
- `#Innerengineeringonline`
- `#Iecompletion`
- `#Bhavaspandana`
- `#Shoonyameditation`
- `#Shoonya`
- `#Samyama`
- `#Sadhanapada`
- `#Shambhavimahamudra`
- `#Cauverycalling`
- `#Savesoil`
- `#Consciousplanet`
- `#Consciousliving`
- `#Consciousness`
- `#Conscious`
- `#Miracleofmind`
- `#Soilhealth`
- `#Climateaction`
- `#Sustainability`
- `#Savesoilmovement`
- `#Consciousplanetmovement`
- `#Innerengineeringretreat`
- `#Ishahealthsolutions`

### Consecrated Spaces, Deities & Sacred Events (Mandatory):
- `#Adiyogi`
- `#Adiyogishiva`
- `#Adhiyogi`
- `#Dhyanalinga`
- `#Dhyanalingatemple`
- `#Lingabhairavi`
- `#Bhairavi`
- `#Devi`
- `#Shiva`
- `#Shiv`
- `#Mahadev`
- `#Mahashivratri`
- `#Shivaratri`
- `#Gurupoornima`
- `#Gurupurnima`
- `#Rudraksha`
- `#Rudraksh`
- `#Kailash`
- `#Kailashwithsadhguru`
- `#Kailashwithsadhguru2026`
- `#Kailashyatra`
- `#Kailashmansarovar`
- `#Kashi`
- `#Sacredspaces`
- `#Lingabhairaviseva`
- `#Bhairaviyantra`
- `#Shivamantra`
- `#Shivashiva`
- `#Adiyogitemple`
- `#Adiyogi_statue`
- `#Adiyogistatue`
- `#Msrww26`
- `#Mahashivratri2026`
- `#Ishamahashivratri2026`
- `#Kalabhairava`
- `#Krishna`
- `#Shakti`
- `#Humansofisha`
- `#Sadhguruinlucknow`
- `#Ishahathayoga`
- `#Yogicharya`
- `#Ayurveda`
- `#Grace`
- `#Guru`
- `#Mysticsmusings`
- `#Sadhgurumargam`

### Practices & Classical Yoga:
- `#Yoga`
- `#Hathayoga`
- `#Classicalhathayoga`
- `#Kaalahathayoga`
- `#Suryakriya`
- `#Suryashakti`
- `#Angamardana`
- `#Bhutashuddhi`
- `#Upayoga`
- `#Yogasanas`
- `#Kriyayoga`
- `#Kriya`
- `#Asana`
- `#Mudra`
- `#Pranayama`
- `#Prana`
- `#Kundalini`
- `#Chakra`
- `#Meditation`
- `#Meditationpractice`
- `#Guidedmeditation`
- `#Yogapractice`
- `#Spiritualpractice`
- `#Dailysadhana`
- `#Sadhana`
- `#Energybody`
- `#Spirituality`
- `#Sadhguruquotes`
- `#Sadhguruwisdom`
- `#Sanatandharma`
- `#Omnamahshivaya`
- `#Yogi`
- `#Yogini`
- `#Yogis`
- `#Yogic`
- `#Yogicscience`
- `#Yogicdiet`
- `#Sattvicfood`
- `#Mantra`
- `#Satsang`
- `#Darshan`
- `#Samadhi`
- `#Mukti`
- `#Moksha`
- `#Vairagya`
- `#Bhakti`
- `#Karma`
- `#Shambho`
- `#Kalaripayattu`
- `#Dailyyoga`
- `#Yogaclasses`
- `#Travelingyogi`
- `#Dailymobility`
- `#Breathworkhealing`

### States of Being & Growth:
- `#Innerpeace`
- `#Bliss`
- `#Joyfulliving`
- `#Mindfulness`
- `#Selfawareness`
- `#Selfrealization`
- `#Innergrowth`
- `#Innertransformation`
- `#Spiritualawakening`
- `#Wellbeing`
- `#Awakening`
- `#Enlightenment`
- `#Transformation`
- `#Stillness`
- `#Silence`
- `#Devotion`
- `#Gratitude`
- `#Divineenergy`
- `#Presence`
- `#Awareness`
- `#Culture`
- `#Feminine`
- `#Spiritualjourney`
- `#Spiritualgrowth`
- `#Spiritualwisdom`
- `#Innerjourney`
- `#Innerwellbeing`
- `#Selfgrowth`
- `#Openingheart`
- `#Successmindset`

### Community, Events & Outreach:
- `#Ishagramotsavam`
- `#Ishagramotsavam2026`
- `#Gramotsavam`
- `#Sportingspiritofbharat`
- `#Ruralsports`
- `#Nepalflood`
- `#Nepalfloods`
- `#Nepalflashfloods`
- `#Nagapanchami`
- `#Sadhguruinmalaysia2026`

### Regional & Multi-language Handles:
- `#Sadhguru360`
- `#Sadhgurulatest`
- `#Sadhgurutamil`
- `#Sadhgurutelugu`
- `#Sadhguruhindi`
- `#Sadhgurukannada`
- `#Sadhgurumarathi`
- `#Sadhgurumalayalam`
- `#Sadhgurubangla`
- `#ஈஷா`

---

## 8. Complete Allowed Caption Keywords (`WISDOM_WARRIOR_ALLOWED_CAPTION_KEYWORDS`)

Substring match: case-insensitive, checked against full reel caption.

### Foundation & Core:
- `Isha`
- `Ishafoundation`
- `Isha Foundation`
- `Ishayoga`
- `Isha Yoga`
- `Ishayogacenter`
- `Isha Yoga Center`
- `Sounds of Isha`
- `Soundsofisha`
- `Isha Volunteers`
- `Isha Life`
- `Isha Ashram`
- `Isha Events`
- `Sacred Spaces`
- `Ashram Life`
- `Coimbatore Ashram`
- `Linga Seva`
- `Kala Bhairava`
- `Kalabhairava`
- `Humans of Isha`
- `Guru Purnima`
- `Isha Hatha Yoga`
- `Shakti`
- `Ayurveda`

### Sadhguru & Wisdom:
- `Sadhguru`
- `Sadguru`
- `Sadhgurujaggivasudev`
- `Sadhguru Jaggi Vasudev`
- `Jaggi`
- `Sadhguru Quotes`
- `Sadhguruquotes`
- `Sadhguru Wisdom`
- `Sadhguruwisdom`
- `Sadhguru Latest`
- `Sadhguru 360`

### Programs, Initiatives & Movements:
- `Inner Engineering`
- `Innerengineering`
- `Inner Engineering Online`
- `IE Completion`
- `Bhava Spandana`
- `Bhavaspandana`
- `Shoonya Meditation`
- `Shoonyameditation`
- `Shoonya`
- `Samyama`
- `Sadhanapada`
- `Shambhavi Mahamudra`
- `Isha Kriya`
- `Chith Shakti`
- `Cauvery Calling`
- `Cauverycalling`
- `Save Soil`
- `Savesoil`
- `Conscious Planet`
- `Consciousplanet`
- `Conscious Living`
- `Consciousliving`
- `Consciousness`
- `Conscious`
- `Miracle of Mind`
- `Miracleofmind`

### Consecrated Spaces, Deities & Events:
- `Adiyogi`
- `Adiyogi Shiva`
- `Adiyogishiva`
- `Dhyanalinga`
- `Linga Bhairavi`
- `Lingabhairavi`
- `Bhairavi`
- `Bhairavi Stuti`
- `Linga Bhairavi Stuti`
- `Bhairavi Utsav`
- `Bhairavi Yantra`
- `Devi`
- `Shiva`
- `Mahadev`
- `Mahashivratri`
- `Shivaratri`
- `Guru Poornima`
- `Rudraksha`
- `Kashi Yatra`
- `Kailash Manasarovar`
- `Kailash with Sadhguru`
- `Kailash Yatra`
- `Kailash Mansarovar`
- `Divine Energy`
- `Sanatan Dharma`
- `Om Namah Shivaya`
- `Naga Panchami`
- `Nepal Flood`
- `Nepal Floods`
- `Nepalflood`
- `Nepalfloods`

### Classical Hatha Yoga & Practices:
- `Yoga`
- `Hatha Yoga`
- `Hathayoga`
- `Classical Hatha Yoga`
- `Surya Kriya`
- `Surya Shakti`
- `Angamardana`
- `Bhuta Shuddhi`
- `Upa Yoga`
- `Yogasanas`
- `Kriya Yoga`
- `Kriyayoga`
- `Kriya`
- `Asana`
- `Mudra`
- `Pranayama`
- `Prana`
- `Kundalini`
- `Chakra`
- `Meditation`
- `Meditation Practice`
- `Guided Meditation`
- `Yoga Practice`
- `Spiritual Practice`
- `Daily Sadhana`
- `Sadhana`
- `Energy Body`
- `Spirituality`
- `Yogic Science`
- `Yogic Diet`
- `Sattvic Food`
- `Shambho`
- `Kalaripayattu`
- `Daily Yoga`
- `Mantra`
- `Satsang`
- `Darshan`
- `Samadhi`
- `Mukti`
- `Moksha`
- `Vairagya`
- `Bhakti`
- `Consecrated`

### States of Being & Growth:
- `Inner Peace`
- `Peace of Mind`
- `Inner Growth`
- `Inner Transformation`
- `Spiritual Awakening`
- `Self Realization`
- `Inner Wellbeing`
- `Higher Self`
- `Bliss`
- `Joyful Living`
- `Mindfulness`
- `Self Awareness`
- `Awakening`
- `Enlightenment`
- `Transformation`
- `Stillness`
- `Silence`
- `Devotion`
- `Gratitude`
- `Presence`
- `Awareness`
- `Culture`
- `Feminine`
- `Spiritual Journey`
- `Spiritual Growth`
- `Spiritual Wisdom`
- `Self Growth`
- `Opening Heart`

### Outreach & Events:
- `Ishagramotsavam`
- `Gramotsavam`
- `Sporting Spirit of Bharat`
- `Rural Sports`

### Native Regional Language Scripts:
- **Tamil:** `ஈஷா`, `சத்குரு`
- **Hindi / Sanskrit:** `ईशा`, `सद्गुरु`, `महादेव`, `शिव`, `देवी`
- **Telugu:** `ఇషా`, `సద్గురు`
- **Kannada:** `ಇಶಾ`, `ಸದ್ಗುರು`
- **Malayalam:** `ഇഷ`, `സദ്‍ഗുരു`

---

## 9. Code Implementation References

| Component | File Path | Role |
| :--- | :--- | :--- |
| **Filtered Monthly Views** | [`backend/repositories/analytics_repo.py`](file:///Users/sadhguruwisdomwarrior/.gemini/antigravity/scratch/WisdomWarriors/backend/repositories/analytics_repo.py) | `get_wisdom_warriors_monthly_views_filtered`: Dedicated gets all reels, IHI gets filtered reels. Enforces co-author splitting and post deduplication. |
| **Micro Units Calculator** | [`backend/services/monthly_calculation_service.py`](file:///Users/sadhguruwisdomwarrior/.gemini/antigravity/scratch/WisdomWarriors/backend/services/monthly_calculation_service.py) | `calculate_monthly_metrics`: Enforces Dedicated (all) vs IHI (filtered) across prior 6 months and target month, with dynamic active month normalization. |
| **Apify Posts Runner** | [`backend/services/apify/posts_runner.py`](file:///Users/sadhguruwisdomwarrior/.gemini/antigravity/scratch/WisdomWarriors/backend/services/apify/posts_runner.py) | Default 1,500 limit and dynamic date range conversion for Apify actor. |
| **Scrape Service** | [`backend/services/scrape_service.py`](file:///Users/sadhguruwisdomwarrior/.gemini/antigravity/scratch/WisdomWarriors/backend/services/scrape_service.py) | Handles background scrape tasks with 1,500 post depth. |
| **Scrape Frontend UI** | [`frontend/src/pages/Scrape/index.tsx`](file:///Users/sadhguruwisdomwarrior/.gemini/antigravity/scratch/WisdomWarriors/frontend/src/pages/Scrape/index.tsx) | Default 1,500 limit input in web form. |
| **Tagged Group Dictionary** | [`backend/repositories/post_repo.py`](file:///Users/sadhguruwisdomwarrior/.gemini/antigravity/scratch/WisdomWarriors/backend/repositories/post_repo.py) | Master dictionary terms for tag groups. |
