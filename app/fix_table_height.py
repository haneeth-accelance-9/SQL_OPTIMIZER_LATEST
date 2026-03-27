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

# Let the Data Table containers naturally expand to fit the 6 rows exactly.
html = html.replace(
    'class="flex-1 min-h-[200px] bg-white rounded-xl border border-slate-200 shadow-sm flex flex-col overflow-hidden mt-6"',
    'class="bg-white rounded-xl border border-slate-200 shadow-sm flex flex-col mt-6"'
)
html = html.replace(
    'class="flex-1 overflow-hidden p-0 relative"',
    'class="overflow-x-auto p-0 relative"'
)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(html)

print("Adjustments complete")
