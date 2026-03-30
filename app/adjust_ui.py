import sys
import re

file_path = r'c:\Users\Lenovo\Documents\ID INFO\Dionce Technology\bayer\New folder\django_application\sql_license_optimizer\templates\optimizer\dashboard.html'

with open(file_path, 'r', encoding='utf-8') as f:
    html = f.read()

def replace_exact(old, new):
    global html
    if old not in html:
        print(f"Warning: Could not find \n{old}\n")
    else:
        html = html.replace(old, new)


# 1. Reduce the card sizes of BYOL to PAYG Candidates and Retired but Reporting
# Change grid from 3 columns to 4 columns to make the Insight card smaller
replace_exact(
    'class="grid grid-cols-1 lg:grid-cols-3 gap-6 flex-shrink-0 mb-6"',
    'class="grid grid-cols-1 lg:grid-cols-4 gap-6 flex-shrink-0 mb-6"'
)
# Make charts span 3 columns instead of 2 (Rule 1 & Rule 2)
replace_exact(
    'class="col-span-1 lg:col-span-2 grid grid-cols-1 md:grid-cols-2 gap-4"',
    'class="col-span-1 lg:col-span-3 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"'
)

# 2. Adjust raw data preview in rule 1 and rule 2: no scrolling inside
# Change overflow-auto to overflow-hidden so the fixed 6 rows just fit perfectly
replace_exact(
    'class="flex-1 overflow-auto p-0 relative"',
    'class="flex-1 overflow-hidden p-0 relative"'
)

# 3. Fix charts formatting and proportion to their designated spaces
# The user said they are not in right proportion. So I revert the specific chart container flex classes I added, or fix the heights.
# Reverting: 'chart-card bg-white rounded-xl p-5 border border-slate-200 shadow-sm flex flex-col min-h-[280px] overflow-hidden'
# I will change them back to the original layout classes where Plotly worked well.
html = html.replace(
    'chart-card bg-white rounded-xl p-5 border border-slate-200 shadow-sm flex flex-col min-h-[280px] overflow-hidden',
    'chart-card bg-white rounded-xl p-4 border border-slate-200 shadow-sm min-h-[260px] overflow-hidden'
)
# For the chart-container, the flex-1 might be breaking the plotly div
html = html.replace(
    'class="chart-container flex-1 min-h-[200px] w-full"',
    'class="chart-container min-h-[200px] w-full"'
)

# Also fix the dashboard charts section which might still use the flex layout if it didn't match the exact string exactly.
html = html.replace(
    'class="chart-card bg-white rounded-lg border border-slate-200 p-3 shadow-sm min-h-[260px] overflow-hidden"',
    'class="chart-card bg-white rounded-lg border border-slate-200 p-3 shadow-sm min-h-[260px] overflow-hidden"'
)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(html)

print("Adjustments complete")
