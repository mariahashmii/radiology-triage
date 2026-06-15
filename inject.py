import glob
import os

for f in glob.glob('static/*.html'):
    with open(f, 'r', encoding='utf-8') as file:
        content = file.read()
    if '</body>' in content:
        content = content.replace('</body>', '<script src="/static/main.js"></script></body>')
    else:
        content += '<script src="/static/main.js"></script>'
    with open(f, 'w', encoding='utf-8') as file:
        file.write(content)
print("JS injected.")
