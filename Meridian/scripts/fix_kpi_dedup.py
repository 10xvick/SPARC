"""Fix broken dedup logic in all KPI scripts.

The old pattern:
    mask = (existing_df['SAPID'].isin(...)) & (existing_df['CurrentDate'] == current_date_str)
    existing_df = existing_df[~mask]
    combined_df = pd.concat([existing_df, new_df], ignore_index=True)

fails when the CurrentDate in source data != today (current_date_str), causing
duplicate rows to accumulate on every run.

The fix:
    combined_df = pd.concat([existing_df, new_df], ignore_index=True)
    combined_df = combined_df.drop_duplicates(subset=['CurrentDate', 'SAPID'], keep='last')
"""
import re
import glob

files = glob.glob('/Users/dbsrinivasrao/Desktop/TeamSight/src/kpp_k*.py')

# Remove the mask block (single-line or split across two lines)
mask_pattern = re.compile(
    r'[ \t]*mask\s*=\s*\(existing_df\[.SAPID.\]\.isin\(new_df\[.SAPID.\]\.values\)\)'
    r'.*?'
    r'existing_df\s*=\s*existing_df\[~mask\]\s*\n',
    re.DOTALL
)

# Inject drop_duplicates after the concat line (only if not already present)
concat_pattern = re.compile(
    r'([ \t]*combined_df\s*=\s*pd\.concat\(\[existing_df,\s*new_df\],\s*ignore_index=True\)\s*\n)'
    r'(?![ \t]*combined_df\s*=\s*combined_df\.drop_duplicates)'
)


def add_dedup(m):
    indent = re.match(r'([ \t]*)', m.group(1)).group(1)
    return (
        m.group(1)
        + f"{indent}combined_df = combined_df.drop_duplicates(subset=['CurrentDate', 'SAPID'], keep='last')\n"
    )


fixed = 0
for fpath in sorted(files):
    with open(fpath, 'r') as fh:
        src = fh.read()

    if "existing_df['CurrentDate'] == current_date_str" not in src:
        continue

    new_src = mask_pattern.sub('', src)
    new_src = concat_pattern.sub(add_dedup, new_src)

    if new_src != src:
        with open(fpath, 'w') as fh:
            fh.write(new_src)
        print(f"  Fixed: {fpath.split('/')[-1]}")
        fixed += 1
    else:
        print(f"  UNCHANGED (check manually): {fpath.split('/')[-1]}")

print(f"\nTotal fixed: {fixed}")
