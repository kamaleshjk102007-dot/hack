from pathlib import Path
text = Path('hud/templates/hud.html').read_text(encoding='utf-8', errors='replace')
start = text.find('function EDITH()')
end = text.find('try {', start)
segment = text[start:end]
paren = brace = brack = 0
in_s = None
escaped = False
for ch in segment:
    if in_s:
        if escaped:
            escaped = False
        elif ch == '\\':
            escaped = True
        elif ch == in_s:
            in_s = None
        continue
    if ch in ('"', "'"):
        in_s = ch
        continue
    if ch == '(':
        paren += 1
    elif ch == ')':
        paren -= 1
    elif ch == '{':
        brace += 1
    elif ch == '}':
        brace -= 1
    elif ch == '[':
        brack += 1
    elif ch == ']':
        brack -= 1
print('paren', paren)
print('brace', brace)
print('brack', brack)
print('start index', start, 'end index', end)
print('last 200 chars:', repr(segment[-200:]))
