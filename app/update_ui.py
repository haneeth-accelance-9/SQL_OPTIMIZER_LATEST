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


# --- Safely Replace Classes that don't span across template blocks ---

# --- WRAPPER ---
replace_exact(
    'class="h-full flex flex-col mx-4 my-4 rounded-2xl overflow-hidden shadow-sm bg-white border border-slate-200"',
    'class="h-full flex flex-col mx-4 lg:mx-8 my-6 rounded-xl overflow-hidden shadow-lg bg-slate-50 border border-slate-200"'
)

# --- HEADER ---
replace_exact(
    'class="flex-shrink-0 flex justify-between items-center px-6 py-4 border-b border-slate-200 bg-slate-50/50"',
    'class="flex-shrink-0 flex justify-between items-center px-8 py-6 border-b border-slate-200 bg-white"'
)
replace_exact(
    'class="text-2xl font-extrabold text-slate-900 tracking-wide uppercase border-l-4 border-teal-500 pl-4"',
    'class="text-2xl font-bold text-slate-800 tracking-tight"'
)
replace_exact(
    'class="text-sm text-slate-500 mt-0.5"',
    'class="text-sm text-slate-500 mt-1"'
)
replace_exact(
    'class="px-4 py-2 text-slate-600 bg-white border border-slate-200 text-sm font-semibold rounded-lg shadow-sm hover:bg-slate-50 transition-colors"',
    'class="px-4 py-2 text-slate-700 bg-white border border-slate-300 text-sm font-medium rounded-lg shadow-sm hover:bg-slate-50 transition-colors"'
)
replace_exact(
    'class="px-4 py-2 text-white text-sm font-semibold rounded-lg shadow-sm hover:opacity-90 transition-opacity flex items-center gap-2"\n                style="background: linear-gradient(135deg, #0f172a 0%, #334155 100%);"',
    'class="px-4 py-2 text-white bg-blue-600 hover:bg-blue-700 text-sm font-medium rounded-lg shadow-sm transition-colors flex items-center gap-2"'
)

# --- TABS HEADER & KPIs ---
replace_exact(
    'class="flex-shrink-0 flex flex-nowrap justify-between items-center px-6 py-2 border-b border-slate-100 bg-white gap-3 min-h-0"',
    'class="flex-shrink-0 flex flex-nowrap justify-between items-center px-8 py-0 border-b border-slate-200 bg-white gap-3 min-h-0 z-10"'
)
replace_exact(
    'class="flex flex-shrink-0 bg-slate-100/80 p-1 rounded-xl"',
    'class="flex flex-shrink-0 gap-6 -mb-[1px]"'
)
html = html.replace(
    'class="optimizer-tab-link px-4 py-1.5 rounded-lg text-xs font-semibold transition-all duration-200 whitespace-nowrap"',
    'class="optimizer-tab-link py-4 text-sm font-medium transition-colors duration-200 whitespace-nowrap border-b-2"'
)
replace_exact(
    'class="flex flex-shrink-0 items-center gap-2"',
    'class="flex flex-shrink-0 items-center gap-6 py-3"'
)
replace_exact(
    'class="flex items-center gap-2 pr-3 border-r border-slate-200"',
    'class="flex items-center gap-3"'
)
replace_exact(
    'class="p-1.5 bg-blue-50 rounded-md text-blue-600"',
    'class="p-2 bg-blue-50 rounded-lg text-blue-600"'
)
replace_exact(
    '<p class="text-[10px] font-semibold text-slate-500 uppercase tracking-wide leading-tight">Total Demand</p>',
    '<p class="text-[11px] font-semibold text-slate-500 uppercase tracking-wider leading-tight">Total Demand</p>'
)
replace_exact(
    '<p class="text-sm font-bold text-slate-900 leading-none">{{ total_demand_quantity }} <span class="text-[10px] text-slate-400 font-normal">Licenses</span></p>',
    '<p class="text-base font-bold text-slate-800 leading-none mt-1">{{ total_demand_quantity }} <span class="text-[11px] text-slate-500 font-normal">Licenses</span></p>'
)

# Second KPI container structure replacement to handle vertical divider
html = html.replace(
    '<div class="flex items-center gap-2">\n                <div class="p-1.5 bg-teal-50 rounded-md text-teal-600">',
    '<div class="w-px h-8 bg-slate-200"></div>\n            <div class="flex items-center gap-3">\n                <div class="p-2 bg-emerald-50 rounded-lg text-emerald-600">'
)

replace_exact(
    '<p class="text-[10px] font-semibold text-slate-500 uppercase tracking-wide leading-tight">Opportunities</p>',
    '<p class="text-[11px] font-semibold text-slate-500 uppercase tracking-wider leading-tight">PAYG Candidates</p>'
)
replace_exact(
    '<p class="text-sm font-bold text-slate-900 leading-none">{{ azure_payg_count }} <span class="text-[10px] text-slate-400 font-normal">PAYG</span></p>',
    '<p class="text-base font-bold text-slate-800 leading-none mt-1">{{ azure_payg_count }} <span class="text-[11px] text-slate-500 font-normal">Devices</span></p>'
)

# --- PANEL BACKGROUNDS ---
replace_exact(
    'class="flex-1 min-h-0 relative bg-slate-50/30"',
    'class="flex-1 min-h-0 relative bg-transparent"'
)

# --- RULE 1 PANEL ---
replace_exact(
    'id="panel-rule1" class="tab-content-panel absolute inset-0 flex flex-col p-6 overflow-y-auto"',
    'id="panel-rule1" class="tab-content-panel absolute inset-0 flex flex-col p-6 lg:p-8 overflow-y-auto"'
)
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

# --- RULE 2 PANEL ---
replace_exact(
    'id="panel-rule2" class="tab-content-panel absolute inset-0 flex flex-col p-6 overflow-y-auto"',
    'id="panel-rule2" class="tab-content-panel absolute inset-0 flex flex-col p-6 lg:p-8 overflow-y-auto"'
)
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

# --- CHARTS GENERIC ---
html = html.replace('chart-card bg-white rounded-lg p-3 border border-slate-200 shadow-sm flex flex-col min-h-[260px] overflow-hidden', 'chart-card bg-white rounded-xl p-5 border border-slate-200 shadow-sm flex flex-col min-h-[280px] overflow-hidden')
html = html.replace('class="text-xs font-bold text-[#1f2937] mb-2 flex-shrink-0"', 'class="text-sm font-semibold text-slate-700 mb-4 flex-shrink-0"')

# --- DATA TABLES GENERIC ---
html = html.replace('bg-white rounded-lg border border-slate-200 shadow-sm flex flex-col overflow-hidden mt-3', 'bg-white rounded-xl border border-slate-200 shadow-sm flex flex-col overflow-hidden mt-6')
html = html.replace('class="px-6 py-4 border-b border-slate-100 bg-slate-50 flex justify-between items-center flex-wrap gap-2"', 'class="px-6 py-5 border-b border-slate-200 bg-white flex justify-between items-center flex-wrap gap-4"')
html = html.replace('class="text-sm font-bold text-slate-800">Raw Candidate Data', 'class="text-base font-bold text-slate-800">Raw Candidate Data')
html = html.replace('class="px-3 py-1 bg-slate-200/50 text-slate-600 rounded-lg text-xs font-bold"', 'class="px-3 py-1.5 bg-slate-100 text-slate-700 rounded-md text-xs font-semibold"')

replace_exact(
    'class="px-3 py-2 border-b border-slate-200 bg-slate-50 flex justify-between items-center flex-wrap gap-1"',
    'class="px-6 py-5 border-b border-slate-200 bg-white flex justify-between items-center flex-wrap gap-4"'
)
replace_exact(
    'class="text-xs font-bold text-[#1f2937]">Raw Retired Device Data',
    'class="text-base font-bold text-slate-800">Raw Retired Device Data'
)

html = html.replace('class="optimizer-pagination-link px-2.5 py-1.5 rounded border border-slate-200 text-xs font-semibold', 'class="optimizer-pagination-link px-3 py-1.5 rounded-md border border-slate-200 text-xs font-semibold')
html = html.replace('class="px-6 py-3 text-xs font-bold text-slate-500 uppercase tracking-wider whitespace-nowrap bg-slate-50"', 'class="px-6 py-3.5 text-xs font-semibold text-slate-500 uppercase tracking-wider whitespace-nowrap bg-slate-50"')

html = html.replace('hover:bg-teal-50/30', 'hover:bg-slate-50')
html = html.replace('hover:bg-amber-50/40', 'hover:bg-slate-50')


# --- COMBINED KPI SECTION ---
replace_exact(
    'class="bg-gradient-to-br from-blue-900 to-indigo-900 text-white p-6 rounded-2xl shadow-md relative overflow-hidden"',
    'class="bg-blue-600 text-white p-6 rounded-xl shadow-sm relative overflow-hidden"'
)
replace_exact(
    'class="text-xs font-bold text-indigo-200 uppercase tracking-widest mb-1 relative z-10">Total\n                            License Demand',
    'class="text-xs font-semibold text-blue-100 uppercase tracking-wider mb-2 relative z-10">Total License Demand'
)

# Clean replacement for the Combined KPIs
html = html.replace(
    '<div class="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm relative overflow-hidden">\n                        <div class="absolute top-0 right-0 w-1.5 h-full bg-teal-500"></div>\n                        <h3 class="text-xs font-bold text-slate-400 uppercase tracking-widest mb-1">PAYG Candidates</h3>\n                        <p class="text-4xl font-extrabold text-teal-600">{{ azure_payg_count }}</p>\n                    </div>',
    '<div class="bg-white p-6 rounded-xl border border-slate-200 shadow-sm border-l-4 border-l-emerald-500">\n                        <h3 class="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">PAYG Candidates</h3>\n                        <p class="text-4xl font-extrabold text-slate-800">{{ azure_payg_count }}</p>\n                    </div>'
)
html = html.replace(
    '<div class="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm relative overflow-hidden">\n                        <div class="absolute top-0 right-0 w-1.5 h-full bg-amber-500"></div>\n                        <h3 class="text-xs font-bold text-slate-400 uppercase tracking-widest mb-1">Retired Risks</h3>\n                        <p class="text-4xl font-extrabold text-amber-600">{{ retired_count }}</p>\n                    </div>',
    '<div class="bg-white p-6 rounded-xl border border-slate-200 shadow-sm border-l-4 border-l-amber-500">\n                        <h3 class="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Retired Risks</h3>\n                        <p class="text-4xl font-extrabold text-slate-800">{{ retired_count }}</p>\n                    </div>'
)

html = html.replace(
    '<div class="bg-slate-50 p-6 rounded-2xl border border-slate-200 border-dashed shadow-sm">\n                        <h3 class="text-xs font-bold text-slate-400 uppercase tracking-widest mb-1">Est. Cost Analysis\n                        </h3>\n                        <p class="text-3xl font-extrabold text-slate-300">TBD</p>\n                        <p class="text-xs text-slate-400 font-medium mt-2">Requires price configuration mapping</p>\n                    </div>',
    '<div class="bg-slate-50 p-6 rounded-xl border border-slate-200 shadow-sm">\n                        <h3 class="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Est. Cost Analysis</h3>\n                        <p class="text-3xl font-extrabold text-slate-900">TBD</p>\n                        <p class="text-xs text-slate-500 font-medium mt-2">Requires price configuration mapping</p>\n                    </div>'
)

# --- DASHBOARD PANEL ---
replace_exact(
    'id="panel-dashboard" class="tab-content-panel absolute inset-0 flex flex-col p-6 overflow-y-auto"\n            data-tab="dashboard" style="padding-bottom: 2rem;"',
    'id="panel-dashboard" class="tab-content-panel absolute inset-0 flex flex-col p-6 lg:p-8 overflow-y-auto"\n            data-tab="dashboard" style="padding-bottom: 3rem;"'
)
replace_exact(
    '<h2 class="text-lg font-bold text-slate-800 mb-3 border-b border-slate-200 pb-2">Executive Summary</h2>',
    '<h2 class="text-xl font-bold text-slate-800 mb-6 pb-2">Executive Summary</h2>'
)
html = html.replace(
    'class="bg-white p-4 rounded-xl border border-slate-200 shadow-sm"',
    'class="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex flex-col justify-center"'
)
html = html.replace('class="bg-white p-4 rounded-xl border border-emerald-100 shadow-sm"', 'class="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex flex-col justify-center"')
html = html.replace('class="bg-white p-4 rounded-xl border border-teal-100 shadow-sm"', 'class="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex flex-col justify-center"')
html = html.replace('class="bg-white p-4 rounded-xl border border-amber-100 shadow-sm"', 'class="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex flex-col justify-center"')

html = html.replace('class="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1"', 'class="text-[11px] font-semibold text-slate-500 uppercase tracking-wider mb-2"')
html = html.replace('class="text-[10px] font-bold text-emerald-700 uppercase tracking-wider mb-1"', 'class="text-[11px] font-semibold text-emerald-700 uppercase tracking-wider mb-2"')
html = html.replace('class="text-[10px] font-bold text-teal-700 uppercase tracking-wider mb-1"', 'class="text-[11px] font-semibold text-teal-700 uppercase tracking-wider mb-2"')
html = html.replace('class="text-[10px] font-bold text-amber-700 uppercase tracking-wider mb-1"', 'class="text-[11px] font-semibold text-amber-700 uppercase tracking-wider mb-2"')

html = html.replace('text-2xl font-extrabold', 'text-2xl font-bold')

# AI panel
replace_exact(
    'id="dashboard-ai-recommendations" class="dashboard-ai-content bg-slate-50 border border-slate-200 rounded-xl p-5 text-sm text-slate-700 prose prose-slate max-w-none prose-headings:text-slate-900 prose-p:my-2 prose-ul:my-2 prose-li:my-0.5"',
    'id="dashboard-ai-recommendations" class="dashboard-ai-content bg-white border border-slate-200 rounded-xl p-6 text-sm text-slate-700 prose prose-slate max-w-none prose-headings:text-slate-900 prose-p:my-2 prose-ul:my-2 prose-li:my-0.5 shadow-sm"'
)

# Rule Tables inside Dashboard
html = html.replace('class="text-sm font-bold text-slate-800 px-4 py-3 bg-slate-50 border-b border-slate-200"', 'class="text-sm font-semibold text-slate-800 px-5 py-4 bg-white border-b border-slate-200"')

# Bottom cards
html = html.replace('bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden', 'bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden')
html = html.replace('class="px-5 py-3 bg-blue-50 border-b border-blue-100"', 'class="px-6 py-4 bg-white border-b border-slate-100"')
html = html.replace('class="px-5 py-3 bg-emerald-50 border-b border-emerald-100"', 'class="px-6 py-4 bg-white border-b border-slate-100"')
html = html.replace('class="px-5 py-3 bg-violet-50 border-b border-violet-100"', 'class="px-6 py-4 bg-white border-b border-slate-100"')
html = html.replace('class="p-5 space-y-3 text-sm"', 'class="p-6 space-y-4 text-sm"')

# --- STYLE REPLACEMENTS ---
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

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(html)

print("Update complete")
