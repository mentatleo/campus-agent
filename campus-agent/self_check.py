import re, json

with open('frontend/index.html', 'r', encoding='utf-8') as f:
    c = f.read()

print('=== 1. FILE STRUCTURE ===')
print(f'Size: {len(c)} bytes')
for tag in ['<html','<head>','</head>','<body>','</body>','</html>']:
    print(f'  {tag}: {tag in c}')

print()
print('=== 2. KEY ELEMENTS ===')
checks = [
    ('Vue CDN', 'vue.global' in c or 'unpkg.com/vue' in c),
    ('ECharts CDN', 'echarts' in c),
    ('Marked CDN', 'marked' in c),
    ('#app div', '<div id="app">' in c),
    ('login-overlay', 'login-overlay' in c),
    ('nav-sidebar', 'nav-sidebar' in c),
    ('dashboard view', "currentView === 'dashboard'" in c),
    ('chat view', "currentView === 'chat'" in c),
    ('createApp', 'createApp' in c),
    ("mount(#app)", "mount('#app')" in c),
]
for k, v in checks:
    status = 'OK' if v else 'MISSING'
    print(f'  [{status}] {k}')

print()
print('=== 3. JS SYNTAX (script block) ===')
m = re.search(r'<script>([\s\S]*?)</script>', c)
if m:
    js = m.group(1)
    pairs = [
        ('Braces {}', '{', '}'),
        ('Parens ()', '(', ')'),
        ('Brackets []', '[', ']'),
        ('Backticks `', '`', '`'),
    ]
    for name, o, ch in pairs:
        cnt_o = js.count(o)
        cnt_c = js.count(ch)
        ok = cnt_o == cnt_c
        status = 'OK' if ok else 'MISMATCH'
        print(f'  [{status}] {name}: {cnt_o} vs {cnt_c}')
    
    print()
    print('=== 4. COMMON BUG PATTERNS ===')
    print(f'  Uses ref(): {"ref(" in js}')
    print(f'  Uses reactive(): {"reactive(" in js}')
    print(f'  Has onMounted: {"onMounted(" in js}')
    print(f'  Has return {{}}: {"return {" in js}')
    
    # Check for common runtime errors
    errors_to_check = [
        ('undefined variable', r'\bundefined\b'),
    ]

print()
print('=== 5. CSS CHECKS ===')
css_m = re.search(r'<style>([\s\S]*?)</style>', c)
if css_m:
    css = css_m.group(1)
    print(f'  CSS size: {len(css)} chars')
    critical = [
        'height: 100vh',
        'overflow',
        'display: flex',
        '.login-overlay',
        '#app',
        'position:',
        '{',
        '}',
    ]
    for prop in critical:
        found = prop in css
        status = 'OK' if found else 'MISSING'
        print(f'  [{status}] CSS has "{prop}"')

print()
print('=== 6. HTML TEMPLATE NESTING ===')
app_pos = c.find('<div id="app">')
login_pos = c.find('login-overlay')
print(f'  #app at byte: {app_pos}')
print(f'  login-overlay at byte: {login_pos}')
if app_pos > 0 and login_pos > 0:
    inside = login_pos > app_pos
    status = 'YES' if inside else 'NO - BUG!'
    print(f'  Login inside #app: [{status}]')
else:
    print(f'  WARNING: Cannot determine nesting')

after_app = c[app_pos:] if app_pos > 0 else ''
div_opens = after_app.count('<div')
div_closes = after_app.count('</div>')
diff = div_opens - div_closes
status = 'OK' if diff == 0 else f'MISMATCH by {diff}'
print(f'  Div tags after #app: {div_opens} opens / {div_closes} closes [{status}]')

print()
print('=== 7. SPECIFIC KNOWN ISSUES ===')
# Check for the old hardcoded USER_ID
if "USER_ID" in c and "'DEMO_USER'" in c:
    idx = c.find("'DEMO_USER'")
    ctx = c[max(0,idx-30):idx+30]
    print(f'  [BUG] Hardcoded student ID still present near: ...{ctx}...')
else:
    print(f'  [OK] No hardcoded student ID')

# Check for duplicate mount
mount_count = c.count("mount('#app')")
print(f'  mount("#app") called: {mount_count} time(s) {"[OK]" if mount_count==1 else "[WARN]"}')

# Check all view names used in template are defined in nav items
views_defined = set(re.findall(r"currentView === '(\w+)'", c))
nav_items = set(re.findall(r":class.*view:\s*'(\w+)'", c))
print(f'  Views in template: {views_defined or "none found"}')
print(f'  Nav items: {nav_items or "none found"}')

# Check for window.onerror
print(f'  Global error handler: {"window.onerror" in c}')
