"""Inspect flowsheet cell layouts for parser development."""
import pandas as pd
import os

# 2017 format
df = pd.read_excel(
    os.path.expanduser('~/Developer/WellnessScore/Flowsheets.xlsx'),
    sheet_name='July 1-2017', header=None
)
print("2017 rows 42-56:")
for r in range(42, min(56, len(df))):
    vals = [str(v)[:22] if pd.notna(v) else '.' for v in df.iloc[r, :12]]
    print(f"  R{r:02d}: {'|'.join(vals)}")

# 2024 format
df2 = pd.read_excel(
    os.path.expanduser('~/Developer/data/2024FlowSheets.xlsx'),
    sheet_name='01-02-2024', header=None
)
print("\n2024 (01-02-2024) rows 28-55:")
for r in range(28, min(56, len(df2))):
    vals = [str(v)[:22] if pd.notna(v) else '.' for v in df2.iloc[r, :12]]
    print(f"  R{r:02d}: {'|'.join(vals)}")

# CSV
dfcsv = pd.read_csv(os.path.expanduser('~/Documents/FlowsheetHomeCSV.csv'), header=None, nrows=5)
print("\nCSV first 5 rows:")
print(dfcsv.to_string())

# 2023 format check
df3 = pd.read_excel(
    os.path.expanduser('~/Documents/2023FlowSheets-ex.xlsx'),
    sheet_name='03-19-2023', header=None
)
print("\n2023 (03-19-2023) rows 2-6, 9-16, 42-52:")
for r in [2,3,5,9,10,11,12,13,14,15,16,42,43,44,47,48,49,50,51,52]:
    if r < len(df3):
        vals = [str(v)[:22] if pd.notna(v) else '.' for v in df3.iloc[r, :12]]
        print(f"  R{r:02d}: {'|'.join(vals)}")
