"""Vomit episode frequency analysis pre/post G6PD diagnosis."""
import pandas as pd
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

df = pd.read_csv(BASE / "data" / "processed" / "unified_elimination.csv")
print("Cols:", list(df.columns))
print("Types:\n", df["type"].value_counts().to_string())
print()

vomit = df[df["type"] == "vomit"].copy()
dcol = [c for c in df.columns if "date" in c.lower() or "time" in c.lower()]
print("Date cols:", dcol)
vomit["date"] = pd.to_datetime(vomit[dcol[0]])
print(f"Total vomit episodes: {len(vomit)}")

pre = vomit[vomit["date"] < "2018-10-01"]
post = vomit[vomit["date"] >= "2019-01-01"]
pre_days = (pd.Timestamp("2018-10-01") - vomit["date"].min()).days
post_days = (vomit["date"].max() - pd.Timestamp("2019-01-01")).days
print(f"Pre (before 10/2018): {len(pre)} episodes over {pre_days} days")
print(f"Post (after 01/2019): {len(post)} episodes over {post_days} days")
print(f"Annualized: Pre={len(pre)/pre_days*365:.1f}/yr  Post={len(post)/post_days*365:.1f}/yr")

vomit["year"] = vomit["date"].dt.year
print("\nEpisodes by year:")
print(vomit.groupby("year").size().to_string())

# Also check bowel episodes
bowel = df[df["type"] == "bowel"].copy()
bowel["date"] = pd.to_datetime(bowel[dcol[0]])
if "bloody" in " ".join(df.columns).lower() or "blood" in " ".join(str(x) for x in df.iloc[:5].values.flatten()).lower():
    print("\nBloody bowel flags found")
    bcols = [c for c in df.columns if "blood" in c.lower()]
    print(f"  Blood columns: {bcols}")

# Dialysis sessions for intra-dialytic vomit
sess = pd.read_csv(BASE / "data" / "processed" / "dialysis_sessions.csv")
print(f"\nDialysis sessions: {sess.shape}")
vcols = [c for c in sess.columns if "vomit" in c.lower()]
print(f"Vomit columns in sessions: {vcols}")
if vcols:
    dcol2 = [c for c in sess.columns if "date" in c.lower()]
    sess["date"] = pd.to_datetime(sess[dcol2[0]])
    for vc in vcols:
        pre_s = sess[sess["date"] < "2018-10-01"][vc].dropna()
        post_s = sess[sess["date"] >= "2019-01-01"][vc].dropna()
        if len(pre_s) > 5 and len(post_s) > 5:
            print(f"  {vc}:")
            print(f"    Pre:  {pre_s.mean()*100:.1f}% (n={len(pre_s)})")
            print(f"    Post: {post_s.mean()*100:.1f}% (n={len(post_s)})")
