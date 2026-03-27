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


# 1. ADD 'overflow-hidden' back to chart cards so Plotly doesn't overflow them.
html = html.replace(
    'class="chart-card bg-white rounded-xl p-6 border border-slate-200 shadow-sm min-h-[450px]"',
    'class="chart-card bg-white rounded-xl p-6 border border-slate-200 shadow-sm min-h-[450px] overflow-hidden"'
)

html = html.replace(
    'class="chart-card bg-white rounded-xl p-6 border border-slate-200 shadow-sm min-h-[450px] md:col-span-2"',
    'class="chart-card bg-white rounded-xl p-6 border border-slate-200 shadow-sm min-h-[450px] md:col-span-2 overflow-hidden"'
)

html = html.replace(
    'class="chart-card bg-white rounded-xl p-5 border border-slate-200 shadow-sm min-h-[450px]"',
    'class="chart-card bg-white rounded-xl p-5 border border-slate-200 shadow-sm min-h-[450px] overflow-hidden"'
)


# 2. Fix the white blank space in Rule 1
# Rule 1 has 5 charts. We'll change the grid from cols-3 to cols-6.
replace_exact(
    '<div class="col-span-1 lg:col-span-3 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">',
    '<div class="col-span-1 lg:col-span-3 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-6 gap-4">'
)
# And make the charts inside span correctly.
# "CPU Core Distribution", "Hosting Zone Breakdown", "PAYG by Hosting Zone" -> col-span-2
html = html.replace(
    '<div class="chart-card bg-white rounded-xl p-6 border border-slate-200 shadow-sm min-h-[450px] overflow-hidden">\n                        <h3 class="text-sm font-semibold text-slate-700 mb-4 flex-shrink-0">CPU Core Distribution</h3>',
    '<div class="chart-card bg-white rounded-xl p-6 border border-slate-200 shadow-sm min-h-[450px] overflow-hidden lg:col-span-2">\n                        <h3 class="text-sm font-semibold text-slate-700 mb-4 flex-shrink-0">CPU Core Distribution</h3>'
)
html = html.replace(
    '<div class="chart-card bg-white rounded-xl p-6 border border-slate-200 shadow-sm min-h-[450px] overflow-hidden">\n                        <h3 class="text-sm font-semibold text-slate-700 mb-4 flex-shrink-0">Hosting Zone Breakdown</h3>',
    '<div class="chart-card bg-white rounded-xl p-6 border border-slate-200 shadow-sm min-h-[450px] overflow-hidden lg:col-span-2">\n                        <h3 class="text-sm font-semibold text-slate-700 mb-4 flex-shrink-0">Hosting Zone Breakdown</h3>'
)
html = html.replace(
    '<div class="chart-card bg-white rounded-xl p-6 border border-slate-200 shadow-sm min-h-[450px] overflow-hidden">\n                        <h3 class="text-sm font-semibold text-slate-700 mb-4 flex-shrink-0">PAYG by Hosting Zone</h3>',
    '<div class="chart-card bg-white rounded-xl p-6 border border-slate-200 shadow-sm min-h-[450px] overflow-hidden lg:col-span-2">\n                        <h3 class="text-sm font-semibold text-slate-700 mb-4 flex-shrink-0">PAYG by Hosting Zone</h3>'
)
# "Cost: BYOL vs PAYG", "CPU Core Histogram" -> col-span-3
html = html.replace(
    '<div class="chart-card bg-white rounded-xl p-6 border border-slate-200 shadow-sm min-h-[450px] overflow-hidden">\n                        <h3 class="text-sm font-semibold text-slate-700 mb-4 flex-shrink-0">Cost: BYOL vs PAYG</h3>',
    '<div class="chart-card bg-white rounded-xl p-6 border border-slate-200 shadow-sm min-h-[450px] overflow-hidden lg:col-span-3">\n                        <h3 class="text-sm font-semibold text-slate-700 mb-4 flex-shrink-0">Cost: BYOL vs PAYG</h3>'
)
html = html.replace(
    '<div class="chart-card bg-white rounded-xl p-6 border border-slate-200 shadow-sm min-h-[450px] overflow-hidden">\n                        <h3 class="text-sm font-semibold text-slate-700 mb-4 flex-shrink-0">CPU Core Histogram</h3>',
    '<div class="chart-card bg-white rounded-xl p-6 border border-slate-200 shadow-sm min-h-[450px] overflow-hidden lg:col-span-3">\n                        <h3 class="text-sm font-semibold text-slate-700 mb-4 flex-shrink-0">CPU Core Histogram</h3>'
)


# 3. Fix the white blank space in Combined Tab
# Make Top 10 by Cost span 2 cols to fill the last row.
html = html.replace(
    '<div class="chart-card bg-white rounded-xl p-6 border border-slate-200 shadow-sm min-h-[450px] overflow-hidden">\n                        <h3 class="text-sm font-semibold text-slate-700 mb-4 flex-shrink-0">Top 10 by Cost</h3>',
    '<div class="chart-card bg-white rounded-xl p-6 border border-slate-200 shadow-sm min-h-[450px] overflow-hidden md:col-span-2">\n                        <h3 class="text-sm font-semibold text-slate-700 mb-4 flex-shrink-0">Top 10 by Cost</h3>'
)

# 4. Add window resize trigger to fix Plotly redrawing clipping issues when switching tabs
replace_exact(
    """            validTabs.forEach(function (id) {
                var linkEl = document.getElementById('tablink-' + id);
                var panelEl = document.getElementById('panel-' + id);
                if (id === tabId) {
                    if (linkEl) { linkEl.classList.add('tab-active'); linkEl.classList.remove('tab-inactive'); }
                    if (panelEl) panelEl.classList.add('active-panel');
                    if (history.replaceState) history.replaceState(null, null, '#' + id);
                    else window.location.hash = '#' + id;
                } else {
                    if (linkEl) { linkEl.classList.remove('tab-active'); linkEl.classList.add('tab-inactive'); }
                    if (panelEl) panelEl.classList.remove('active-panel');
                }
            });""",
    """            validTabs.forEach(function (id) {
                var linkEl = document.getElementById('tablink-' + id);
                var panelEl = document.getElementById('panel-' + id);
                if (id === tabId) {
                    if (linkEl) { linkEl.classList.add('tab-active'); linkEl.classList.remove('tab-inactive'); }
                    if (panelEl) panelEl.classList.add('active-panel');
                    if (history.replaceState) history.replaceState(null, null, '#' + id);
                    else window.location.hash = '#' + id;
                } else {
                    if (linkEl) { linkEl.classList.remove('tab-active'); linkEl.classList.add('tab-inactive'); }
                    if (panelEl) panelEl.classList.remove('active-panel');
                }
            });
            // Force Plotly resize after tab switch so charts aren't clipped
            setTimeout(function() { window.dispatchEvent(new Event('resize')); }, 50);"""
)

# Ensure PER_PAGE is exactly 6 everywhere. The DB context pagination logic has 6.
replace_exact('var PER_PAGE = 7;', 'var PER_PAGE = 6;')

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(html)

print("Adjustments complete")
