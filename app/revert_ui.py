import sys
import re

file_path = r'c:\Users\Lenovo\Documents\ID INFO\Dionce Technology\bayer\New folder\django_application\sql_license_optimizer\templates\optimizer\dashboard.html'

with open(file_path, 'r', encoding='utf-8') as f:
    html = f.read()

def replace_exact(new, old):  # reversed signature!
    global html
    if old not in html:
        print(f"Warning: Could not find \n{old}\n")
    else:
        html = html.replace(old, new)


# --- REVERT TABS HEADER ---
replace_exact(
    'class="flex-shrink-0 flex flex-nowrap justify-between items-center px-6 py-2 border-b border-slate-100 bg-white gap-3 min-h-0"',
    'class="flex-shrink-0 flex flex-nowrap justify-between items-center px-8 py-0 border-b border-slate-200 bg-white gap-3 min-h-0 z-10"'
)
replace_exact(
    'class="flex flex-shrink-0 bg-slate-100/80 p-1 rounded-xl"',
    'class="flex flex-shrink-0 gap-6 -mb-[1px]"'
)
html = html.replace(
    'class="optimizer-tab-link py-4 text-sm font-medium transition-colors duration-200 whitespace-nowrap border-b-2"',
    'class="optimizer-tab-link px-4 py-1.5 rounded-lg text-xs font-semibold transition-all duration-200 whitespace-nowrap"'
)
replace_exact(
    '.optimizer-tab-link.tab-active {\n        background-color: #0f172a;\n        color: white;\n        box-shadow: 0 4px 6px -1px rgba(15, 23, 42, 0.1), 0 2px 4px -1px rgba(15, 23, 42, 0.06);\n    }',
    '.optimizer-tab-link.tab-active {\n        color: #2563eb;\n        border-bottom-color: #2563eb;\n    }'
)
replace_exact(
    '.optimizer-tab-link.tab-inactive {\n        background-color: transparent;\n        color: #475569;\n    }',
    '.optimizer-tab-link.tab-inactive {\n        color: #64748b;\n        border-bottom-color: transparent;\n    }'
)
replace_exact(
    '.optimizer-tab-link.tab-inactive:hover {\n        background-color: #e2e8f0;\n        color: #0f172a;\n    }',
    '.optimizer-tab-link.tab-inactive:hover {\n        color: #1e293b;\n        border-bottom-color: #cbd5e1;\n    }'
)

# --- REVERT RULE 1 PANEL GRADIENT & STYLES ---
replace_exact(
    'class="col-span-1 lg:col-span-1 bg-gradient-to-br from-slate-900 to-slate-800 rounded-2xl p-6 text-white shadow-lg relative overflow-hidden flex flex-col"',
    'class="col-span-1 lg:col-span-1 bg-white rounded-xl p-8 shadow-sm border border-slate-200 border-t-4 border-t-blue-600 relative overflow-hidden flex flex-col"'
)
replace_exact(
    '<h2 class="text-lg font-bold mb-2">BYOL to PAYG Candidates</h2>',
    '<h2 class="text-sm font-semibold text-slate-500 uppercase tracking-wider mb-3">BYOL to PAYG Candidates</h2>'
)
replace_exact(
    '<span class="text-5xl font-extrabold tracking-tight">{{ azure_payg_count }}</span>\n                            <span class="text-slate-300 font-medium">devices</span>',
    '<span class="text-5xl font-extrabold tracking-tight text-slate-800">{{ azure_payg_count }}</span>\n                            <span class="text-slate-500 font-medium">devices</span>'
)
replace_exact(
    '<p class="text-sm text-slate-300 leading-relaxed mb-6">',
    '<p class="text-sm text-slate-600 leading-relaxed mb-8">'
)
replace_exact(
    'class="inline-flex items-center gap-2 px-5 py-2.5 bg-white text-slate-900 rounded-xl text-sm font-bold shadow-sm hover:shadow-md transition-all hover:-translate-y-0.5 w-max"',
    'class="inline-flex items-center gap-2 px-5 py-2.5 bg-white border border-blue-200 text-blue-700 rounded-lg text-sm font-semibold shadow-sm hover:bg-blue-50 transition-colors w-max"'
)
replace_exact(
    '<svg class="w-4 h-4 text-teal-600"',
    '<svg class="w-4 h-4 text-blue-600"'
)

# --- REVERT RULE 2 PANEL GRADIENT & STYLES ---
replace_exact(
    'class="col-span-1 lg:col-span-1 bg-gradient-to-br from-amber-600 to-orange-700 rounded-2xl p-6 text-white shadow-lg relative overflow-hidden flex flex-col"',
    'class="col-span-1 lg:col-span-1 bg-white rounded-xl p-8 shadow-sm border border-slate-200 border-t-4 border-t-amber-500 relative overflow-hidden flex flex-col"'
)
replace_exact(
    '<h2 class="text-lg font-bold mb-2">Retired but Reporting</h2>',
    '<h2 class="text-sm font-semibold text-slate-500 uppercase tracking-wider mb-3">Retired but Reporting</h2>'
)
replace_exact(
    '<span class="text-5xl font-extrabold tracking-tight">{{ retired_count }}</span>\n                            <span class="text-orange-100 font-medium">devices</span>',
    '<span class="text-5xl font-extrabold tracking-tight text-slate-800">{{ retired_count }}</span>\n                            <span class="text-slate-500 font-medium">devices</span>'
)
replace_exact(
    '<p class="text-sm text-orange-100 leading-relaxed mb-6">',
    '<p class="text-sm text-slate-600 leading-relaxed mb-8">'
)
replace_exact(
    'class="inline-flex items-center gap-2 px-5 py-2.5 bg-white text-orange-900 rounded-xl text-sm font-bold shadow-sm hover:shadow-md transition-all hover:-translate-y-0.5 w-max"',
    'class="inline-flex items-center gap-2 px-5 py-2.5 bg-white border border-amber-200 text-amber-700 rounded-lg text-sm font-semibold shadow-sm hover:bg-amber-50 transition-colors w-max"'
)
replace_exact(
    '<svg class="w-4 h-4 text-orange-600"',
    '<svg class="w-4 h-4 text-amber-600"'
)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(html)

print("Revert complete")
