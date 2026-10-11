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

## 3. Monthly Views Calculation Formula (6-Month Decay Window + Target Month)

For any target calculation month $M$ (e.g., August 2026):
- **Snapshot 1 ($S1$):** Baseline scrape run at the beginning of Month $M$ (e.g., Run 89 or Run 97).
- **Snapshot 2 ($S2$):** Post-month scrape run at the beginning of Month $M+1$ (e.g., Run 111 or Run 112).

### Calculation Steps:
1. **Prior 6 Months Decay Window ($M-1$ down to $M-6$):**
   - For each reel published between $(M-6)$ and $(M-1)$:
     $$\Delta_{\text{prior}} = \max\left(0.0, S2\text{ Views} - S1\text{ Views}\right)$$
   - *Decay protection:* If $S2 < S1$ (due to pagination cutoff or view re-indexing), $\Delta$ defaults to `0.0` (never negative).
2. **Target Month New Uploads ($M$):**
   - For each reel published within Month $M$:
     $$\text{Views}_{M} = S2\text{ Views}$$
3. **Total Monthly Metric:**
   $$\text{Total Monthly Views} = \sum \text{Views}_{M} + \sum \Delta_{\text{prior}}$$

### Special Handling: Newly Scraped Channels (No Snapshot 1 Baseline)
When a channel is scraped for the first time in $S2$ and has **NO baseline in $S1$**:
- **The Problem:** Because $S1 = 0$, applying $\Delta = S2 - S1$ would treat all historical cumulative views as new growth in Month $M$, causing false inflation.
- **The Rule (Normalization with Dynamic Active Months Divisor):**
  1. Calculate the total cumulative views across the available scraped window in $S2$ (up to prior 6 months + target month):
     $$\text{Total Window Views} = \sum_{\text{available months}} S2\text{ Views}_m$$
  2. Dynamically determine the number of active months based on available data from the start date (it is not always 7; it could be 6, 5, etc., depending on the earliest month of scraped data up to the target month):
     $$\text{Months Divisor} = \text{Earliest Scraped Month to Target Month (inclusive)}$$
  3. Divide the total by the dynamic months divisor:
     $$\text{Total Monthly Views} = \frac{\text{Total Window Views}}{\text{Months Divisor}}$$
  4. This monthly average is credited as the channel's total views for the month, accurately normalizing lifetime views based on the channel's actual scraped lifespan.

---

## 4. Scraper Constraints & Pagination Depth

### A. Results Limit
- **Default Limit:** Set to **4,000** posts per channel across:
  - `backend/services/apify/posts_runner.py`
  - `backend/services/scrape_service.py`
  - `frontend/src/pages/Scrape/index.tsx`
- **Why 4,000 is Mandatory:** Ultra high-volume channels (e.g., `@sadhguru.archives`) post hundreds of reels per month, reaching 2,100+ reels over a 6-month window. Setting the ceiling to 4,000 ensures no active channel has its catalog truncated, while the `onlyPostsNewerThan` date window keeps compute and costs bounded for lower volume channels.

### B. Date Range Reflection
- When `date_from` is selected in a scrape, the backend automatically converts the date range into days (`onlyPostsNewerThan`) and forwards it to the Apify Instagram Actor.

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
