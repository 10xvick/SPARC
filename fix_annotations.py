import os
import re

def process_dir(directory):
    for root, dirs, files in os.walk(directory):
        if 'venv' in root or '__pycache__' in root:
            continue
        for file in files:
            if file.endswith('.py'):
                path = os.path.join(root, file)
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                if 'from __future__ import annotations' not in content:
                    # Find where to insert it. After module docstring.
                    lines = content.split('\n')
                    insert_idx = 0
                    if lines[0].startswith('"""') or lines[0].startswith("'''"):
                        for i in range(1, len(lines)):
                            if lines[i].endswith('"""') or lines[i].endswith("'''"):
                                insert_idx = i + 1
                                break
                    elif len(lines) > 0 and (lines[0].startswith('#') or lines[0].strip() == ''):
                        # skip comments and empty lines
                        for i in range(len(lines)):
                            if not lines[i].startswith('#') and lines[i].strip() != '':
                                insert_idx = i
                                break
                    
                    lines.insert(insert_idx, 'from __future__ import annotations')
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write('\n'.join(lines))
                    print(f"Updated {path}")

process_dir('/Users/vishalsingh/projects/SPARC/Meridian/dashboard/backend/app')
print("Done")
