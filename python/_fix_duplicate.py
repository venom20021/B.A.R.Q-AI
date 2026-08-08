"""Remove duplicate FollowUpPanel function at the bottom of the file."""
import sys

tsx_path = sys.argv[1] if len(sys.argv) > 1 else '../src/renderer/src/pages/JobsPage.tsx'

with open(tsx_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Find the FIRST occurrence (new one we inserted)
first_idx = content.find('function FollowUpPanel(): JSX.Element')
# Find the LAST occurrence (old duplicate)
last_idx = content.rfind('function FollowUpPanel(): JSX.Element')

if first_idx == last_idx:
    print('NO_DUPLICATE')
    sys.exit(0)

print(f'FIRST: {first_idx}, LAST: {last_idx}')

# Find the end of the old FollowUpPanel - look for the next function or section
after_last = last_idx + len('function FollowUpPanel(): JSX.Element')
rest = content[after_last:]

# Find end by looking for the next section divider or EOF
end_markers = ['\n// ═══════════════════', '\n// 5.', '\nexport']
end_idx = len(content)
for m in end_markers:
    pos = rest.find(m)
    if pos >= 0 and pos < end_idx:
        end_idx = pos

# Remove the old definition (from last_idx to end_idx)
new_content = content[:last_idx] + rest[end_idx:]
# Ensure we don't leave empty lines or orphaned section headers
new_content = new_content.rstrip() + '\n'

with open(tsx_path, 'w', encoding='utf-8') as f:
    f.write(new_content)

# Verify
with open(tsx_path, 'r', encoding='utf-8') as f:
    c = f.read()
import re  # noqa: E402
count = len(re.findall(r'function FollowUpPanel', c))
print(f'FOLLOWUP_COUNT_AFTER: {count}')
print('DUPLICATE_REMOVED' if count == 1 else 'STILL_HAS_DUPLICATE')
