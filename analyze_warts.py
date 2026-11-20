#!/usr/bin/env python3
"""Summarise scraped wart posts/comments: which remedies people mention, and whether
they report them working or failing. Also tags mentions of suspected causes.

Usage:
  python analyze_warts.py                 # analyse every data/*/corpus.csv
  python analyze_warts.py data/2026..._warts/corpus.csv

Writes:
  data/wart_analysis/remedy_summary.csv  one row per remedy: mentions, worked, failed, mixed, success %
  data/wart_analysis/cause_summary.csv   one row per suspected cause: mentions
  data/wart_analysis/tagged_items.csv    every relevant post/comment with its remedies, outcome and causes

IMPORTANT: this is crude keyword matching on self-reported anecdotes. Treat the
percentages as "what Reddit says", not as real cure rates. Read the tagged items
to check, and compare against published trial evidence.
"""
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "data" / "wart_analysis"

REMEDIES = {
    "duct tape": r"duct[\s-]?tape|gaffer tape",
    "salicylic acid": r"salicylic|compound w|bazuka|occlusal|duofilm|verrugon|scholl.*(wart|verruca)",
    "freezing (OTC)": r"wartner|freeze ?(spray|kit|away)|dr\.? scholl.*freez|otc freez",
    "cryotherapy (clinic)": r"cryo(therapy)?|liquid nitrogen|froze it off|got (it|them) frozen|dermatologist froze",
    "apple cider vinegar": r"apple cider vinegar|\bacv\b",
    "tea tree oil": r"tea tree",
    "garlic": r"garlic",
    "banana peel": r"banana peel",
    "cantharidin": r"cantharidin|beetle juice|cantharone",
    "imiquimod": r"imiquimod|aldara",
    "bleomycin": r"bleomycin",
    "candida / immunotherapy injection": r"candida (antigen|injection)|immunotherapy injection|candin",
    "laser": r"\blaser",
    "excision / surgery / curettage": r"excis|surgically removed|curettage|cut (it|them) out|scraped (it|them) off",
    "zinc": r"\bzinc\b",
    "HPV vaccine": r"(hpv|gardasil) (vaccine|shot|jab)|gardasil",
    "cimetidine": r"cimetidine|tagamet",
    "silver nitrate": r"silver nitrate",
    "formaldehyde / glutaraldehyde": r"formaldehyde|formalin|glutaraldehyde|veracur|glutarol",
    "filing / pumice": r"pumice|emery board|filing (it|them) down|file (it|them) down",
    "microneedling / needling": r"needling|falknor",
    "hypnosis / suggestion": r"hypno|placebo|wart charm|rubbed (it|them) with",
    "left alone / waited": r"left (it|them) alone|went away on (its|their) own|disappeared on (its|their) own|just waited|did nothing",
}

CAUSES = {
    "HPV": r"\bhpv\b|papilloma",
    "swimming pools / communal showers": r"pool|swimming|communal shower|gym shower|locker room|changing room",
    "barefoot walking": r"barefoot",
    "picking / biting / shaving spread": r"pick(ed|ing)|bit(e|ing) (my )?nails|nail biting|shav(e|ing)",
    "weak / low immune system": r"immune|immunocompromis|immunosuppress",
    "cuts / broken skin": r"\bcut\b|broken skin|scratch",
    "sharing towels / shoes / socks": r"shar(ed|ing) (towel|shoes|socks)",
    "stress": r"\bstress",
    "eczema / dry skin": r"eczema|dry skin",
    "children / school": r"\bkids?\b|children|school",
    "family / partner spread": r"(my|his|her) (son|daughter|kid|partner|husband|wife|sister|brother|mum|mom|dad) (has|had|got)",
}

WORKED = r"\b(it|they|that|this) (worked|cleared|went away|fell off|disappeared)|finally gone|completely gone|\bgone\b now|(was|were|is|are|been) gone|gone (in|after|within)|got rid of|cured|wart[- ]free|cleared (it|them|up)|fell off|disappeared|went away|success(ful)?|did the trick|worked (for me|wonders|great|well)"
FAILED = r"didn'?t work|did not work|doesn'?t work|nothing worked|no (change|luck|difference|improvement)|came back|grew back|returned|still there|made (it|them) worse|waste of (money|time)|useless|failed|didn'?t help|tried everything|spread"

R_REM = {k: re.compile(v, re.I) for k, v in REMEDIES.items()}
R_CAUSE = {k: re.compile(v, re.I) for k, v in CAUSES.items()}
R_WORK, R_FAIL = re.compile(WORKED, re.I), re.compile(FAILED, re.I)
R_TOPIC = re.compile(r"wart|verruca|verruka|hpv", re.I)


def sentences(text):
    return re.split(r"(?<=[.!?\n])\s+", text)


def remedy_outcome(text, remedy_re):
    """Outcome for one remedy, judged from sentences that mention it (plus the next one)."""
    sents = sentences(text)
    worked = failed = False
    for i, s in enumerate(sents):
        if remedy_re.search(s):
            window = " ".join(sents[i:i + 2])
            worked |= bool(R_WORK.search(window))
            failed |= bool(R_FAIL.search(window))
    if worked and failed:
        return "mixed"
    return "worked" if worked else "failed" if failed else "unclear"


def main():
    files = [Path(a) for a in sys.argv[1:]] or sorted((HERE / "data").glob("*/corpus.csv"))
    if not files:
        sys.exit("No corpus.csv files found. Run scrape.py first.")
    rows, seen = [], set()
    for f in files:
        with open(f, newline="") as fh:
            for r in csv.DictReader(fh):
                if r["id"] in seen:
                    continue
                seen.add(r["id"])
                rows.append(r)

    stats = defaultdict(lambda: defaultdict(int))
    cause_counts = defaultdict(int)
    tagged = []
    for r in rows:
        text = f"{r.get('title', '')}\n{r.get('text', '')}"
        if not R_TOPIC.search(text) and r["kind"] == "post":
            continue
        remedies = {name: remedy_outcome(text, rx) for name, rx in R_REM.items() if rx.search(text)}
        causes = [name for name, rx in R_CAUSE.items() if rx.search(text)]
        for name, outcome in remedies.items():
            stats[name]["mentions"] += 1
            stats[name][outcome] += 1
        for c in causes:
            cause_counts[c] += 1
        if remedies or causes:
            tagged.append({
                "kind": r["kind"], "subreddit": r["subreddit"], "url": r["url"],
                "created_utc": r["created_utc"], "score": r["score"],
                "remedies": "; ".join(f"{k}={v}" for k, v in remedies.items()),
                "causes": "; ".join(causes), "text": text.strip()[:2000],
            })

    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "remedy_summary.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["remedy", "mentions", "worked", "failed", "mixed", "unclear", "success_% (of worked+failed)"])
        table = []
        for name, s in stats.items():
            decided = s["worked"] + s["failed"]
            pct = round(100 * s["worked"] / decided) if decided else ""
            table.append([name, s["mentions"], s["worked"], s["failed"], s["mixed"], s["unclear"], pct])
        table.sort(key=lambda x: -x[1])
        w.writerows(table)
    with open(OUT / "cause_summary.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["suspected cause", "mentions"])
        w.writerows(sorted(cause_counts.items(), key=lambda x: -x[1]))
    with open(OUT / "tagged_items.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["kind", "subreddit", "url", "created_utc", "score", "remedies", "causes", "text"])
        w.writeheader()
        w.writerows(tagged)

    print(f"Analysed {len(rows)} items from {len(files)} file(s); {len(tagged)} mention a remedy or cause.\n")
    print(f"{'remedy':36} {'mentions':>8} {'worked':>7} {'failed':>7} {'mixed':>6} {'success%':>9}")
    for name, m, wk, fl, mx, _, pct in table:
        print(f"{name:36} {m:>8} {wk:>7} {fl:>7} {mx:>6} {str(pct):>9}")
    print("\nSuspected causes mentioned:")
    for c, n in sorted(cause_counts.items(), key=lambda x: -x[1]):
        print(f"  {c:36} {n}")
    print(f"\nFull results in {OUT}/")
    print("Reminder: keyword-matched anecdotes, not clinical cure rates. Spot-check tagged_items.csv.")


if __name__ == "__main__":
    main()
