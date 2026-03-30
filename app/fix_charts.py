import sys

file_path = r'c:\Users\Lenovo\Documents\ID INFO\Dionce Technology\bayer\New folder\django_application\sql_license_optimizer\templates\optimizer\dashboard.html'

with open(file_path, 'r', encoding='utf-8') as f:
    html = f.read()

def replace_exact(old, new):
    global html
    if old not in html:
        print(f"Warning: Could not find \n{old}\n")
    else:
        html = html.replace(old, new)

# 1. Update JS Pagination Limit
replace_exact('var PER_PAGE = 7;', 'var PER_PAGE = 6;')

# 2. Fix the chart containers to give them adequate height for Plotly and remove overflow-hidden clipping
# Increase the outer card height
html = html.replace(
    'chart-card bg-white rounded-xl p-4 border border-slate-200 shadow-sm min-h-[260px] overflow-hidden',
    'chart-card bg-white rounded-xl p-6 border border-slate-200 shadow-sm min-h-[450px]'
)

# And the inner containers
html = html.replace(
    'class="chart-container min-h-[200px] w-full"',
    'class="chart-container min-h-[380px] w-full"'
)
html = html.replace(
    'style="min-height:200px;"',
    'style="min-height:380px;"'
)
html = html.replace(
    'style="max-height:200px;"',
    'style="max-height:380px;"'
)

# Fix dashboard summary charts which might have a different string
html = html.replace(
    'class="chart-card bg-white rounded-lg border border-slate-200 p-3 shadow-sm min-h-[260px] overflow-hidden"',
    'class="chart-card bg-white rounded-xl p-5 border border-slate-200 shadow-sm min-h-[450px]"'
)

# Fix Optimization vs Risk from Combined tab
html = html.replace(
    'class="chart-card bg-white rounded-xl p-6 border border-slate-200 shadow-sm col-span-1 min-h-[300px] overflow-hidden"',
    'class="chart-card bg-white rounded-xl p-6 border border-slate-200 shadow-sm col-span-1 min-h-[450px]"'
)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(html)

print("Adjustments complete")
