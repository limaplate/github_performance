import pandas as pd

df_raw = pd.read_csv('repo_features.csv')

dh = df_raw[df_raw['stars'] > 10].copy()
dl = df_raw[df_raw['stars'] <= 10].copy()
dh['_o'] = dh['ki_type'].map({'native':0,'boosted':1,'non_ai':2})
dh = dh.sort_values('_o').drop_duplicates(
    subset=['stars','commits_median','age_months'], keep='first'
).drop(columns=['_o'])
df_dedup = pd.concat([dh, dl], ignore_index=True)

print('=== AUSWIRKUNG DER DEDUP AUF KI-REPO-ZAHLEN ===')
for label, df in [('VOR Dedup (roh)', df_raw), ('NACH Dedup', df_dedup)]:
    nat = (df['ki_type']=='native').sum()
    boo = (df['ki_type']=='boosted').sum()
    non = (df['ki_type']=='non_ai').sum()
    print(f'\n  [{label}]')
    print(f'    AI-Born (native):  {nat:,}')
    print(f'    AI-Boosted:        {boo:,}')
    print(f'    Non-AI:            {non:,}')
    print(f'    Gesamt:            {len(df):,}')

print('\n=== WER WURDE ENTFERNT? ===')
df_raw['_in_dedup'] = df_raw['repo'].isin(df_dedup['repo'])
removed = df_raw[~df_raw['_in_dedup']]
print(f'  Entfernte Repos gesamt: {len(removed):,}')
print(f'  davon native:  {(removed.ki_type=="native").sum():,}')
print(f'  davon boosted: {(removed.ki_type=="boosted").sum():,}')
print(f'  davon non_ai:  {(removed.ki_type=="non_ai").sum():,}')
print(f'  Stars-Median:  {removed.stars.median():.0f}')
print(f'  Stars-Max:     {removed.stars.max():,}')
print()
print('  Top 15 entfernte Repos:')
print(removed.nlargest(15,'stars')[['repo','ki_type','stars']].to_string())
