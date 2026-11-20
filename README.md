# Reddit research scraper

A read-only scraper that uses Reddit's official API through PRAW. It's for personal, non-commercial research.

## 1. Get API access (one-off)
1. Log into Reddit and open <https://www.reddit.com/prefs/apps>. If you can't create an app there, use the developer access request form. It's linked from that page and from r/redditdev's "Responsible Builder Policy" post.
2. Describe your use as: personal, non-commercial medical research; read-only; low volume; data stays on my own computer; not redistributed or used to train AI.
3. Once approved, click **create app**, choose type **script**, and set the redirect URI to `http://localhost:8080` (it isn't used).
4. The **client ID** is the string under the app name, and the **secret** is labelled "secret".

## 2. Set up
```bash
cd reddit_scraper
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # then edit .env with your ID, secret and username
```

## 3. Use: wart research
```bash
# Run every wart search in topics/warts.json (about 16 queries x 8 subreddits, up to 50 posts each)
python scrape.py topic

# Then summarise remedies, success/failure reports and suspected causes
python analyze_warts.py
```
`analyze_warts.py` writes three files to `data/wart_analysis/`:
- `remedy_summary.csv`: for each remedy (duct tape, salicylic acid, freezing, cryotherapy, cantharidin, ACV, etc.), the number of mentions and how many reports said it worked, failed or were mixed, plus a success %.
- `cause_summary.csv`: suspected causes people mention (pools, barefoot walking, picking, low immunity, etc.).
- `tagged_items.csv`: every relevant post or comment with its tags, so you can read and check them.

To change the subreddits or searches, edit `topics/warts.json`. To add remedies or causes, edit the `REMEDIES` / `CAUSES` lists at the top of `analyze_warts.py`.

Other ways to use the scraper:
```bash
python scrape.py search --subreddits Warts,AskDocs --query "duct tape" --sort top --limit 30
python scrape.py thread --url https://www.reddit.com/r/Warts/comments/abc123/title/
python scrape.py topic --time year            # only the last year
```
Each scrape writes `data/<timestamp>_<mode>/` with `posts.jsonl`, `comments.jsonl` and `corpus.csv`.

Useful options:
- `--max-more N` expands more "load more comments" links (`-1` = all, which is slow).
- `--keep-authors` stores usernames. They're left out by default.
- `--allow-duplicates` re-saves items you've already scraped. By default, IDs in `data/seen_ids.txt` are skipped.

### Reading the numbers
These are **self-reported anecdotes found by keyword matching**, not cure rates. People post more when something fails, or when something works dramatically. Many comments don't say how long the person treated for, and the keyword matching will sometimes tag things wrongly. Spot-check `tagged_items.csv`, and compare with trial evidence. For example, Cochrane reviews of topical treatments for warts find salicylic acid and cryotherapy only modestly better than placebo, and many warts clear on their own within 1–2 years.

## Good practice
- Keep `data/` private. Health posts are sensitive, so paraphrase rather than quote identifiable details.
- Reddit's Data API terms allow personal, non-commercial use. They don't allow selling the data or using it to train AI models.
- Reddit search returns at most a few hundred results per query, so run several narrower queries for more coverage. Search syntax supports `AND`, `OR`, quotes, `title:` and `selftext:`.
