"""Build a self-contained HTML reading edition from this book's Markdown subset.

Standard library only; does not import the application or start any instance.
"""
from pathlib import Path
import html
import re

ROOT = Path(__file__).resolve().parent


def slug(text):
    return re.sub(r'[^\w\s-]', '', text.lower()).replace(' ', '-')


def inline(text):
    text = html.escape(text)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    def link(match):
        label, target = match.groups()
        if re.match(r'(?:javascript|data|vbscript):', target, re.I):
            return label
        return '<a href="' + target.replace('"', '&quot;') + '">' + label + '</a>'
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', link, text)
    return re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)


def render(text):
    lines = text.splitlines(); result = []; toc = []; i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1; continue
        if line.startswith('```'):
            language = line[3:]; body = []; i += 1
            while i < len(lines) and not lines[i].startswith('```'):
                body.append(lines[i]); i += 1
            result.append('<pre data-language="'+html.escape(language)+'"><code>'+html.escape('\n'.join(body))+'</code></pre>'); i += 1; continue
        heading = re.match(r'^(#{1,6})\s+(.+)$', line)
        if heading:
            level = len(heading[1]); title = heading[2]; anchor = slug(title)
            result.append(f'<h{level} id="{anchor}">'+inline(title)+f'</h{level}>')
            if level == 1: toc.append((anchor,title))
            i += 1; continue
        if line.startswith('|'):
            rows = []
            while i < len(lines) and lines[i].startswith('|'):
                cells = [cell.strip() for cell in lines[i].strip('|').split('|')]
                if not all(re.fullmatch(r':?-+:?', cell.replace(' ','')) for cell in cells):rows.append(cells)
                i += 1
            header = '<tr>'+''.join('<th>'+inline(c)+'</th>' for c in rows[0])+'</tr>'
            body = ''.join('<tr>'+''.join('<td>'+inline(c)+'</td>' for c in row)+'</tr>' for row in rows[1:])
            result.append('<div class="table-wrap"><table><thead>'+header+'</thead><tbody>'+body+'</tbody></table></div>');continue
        listing = re.match(r'^(?:- |\d+\. )(.+)$',line)
        if listing:
            items=[]
            while i<len(lines):
                item=re.match(r'^(?:- |\d+\. )(.+)$',lines[i])
                if not item:break
                items.append('<li>'+inline(item[1])+'</li>');i+=1
            result.append('<ul>'+''.join(items)+'</ul>');continue
        body=[line];i+=1
        while i<len(lines) and lines[i].strip() and not re.match(r'^(#|```|\||- |\d+\. )',lines[i]):
            body.append(lines[i]);i+=1
        result.append('<p>'+inline(' '.join(body))+'</p>')
    return '\n'.join(result),toc


def main():
    body,toc=render((ROOT/'manuscript.md').read_text(encoding='utf-8'))
    navigation=''.join('<li><a href="#'+anchor+'">'+html.escape(title)+'</a></li>' for anchor,title in toc)
    style='''body{margin:0;color:#24342f;background:#f3f6f4;font:17px/1.9 "PingFang SC","Microsoft YaHei",sans-serif}aside{position:fixed;inset:0 auto 0 0;width:260px;overflow:auto;padding:24px;box-sizing:border-box;background:#e8efeb;font-size:14px}aside ul{padding-left:16px}main{max-width:860px;margin:0 auto 0 290px;padding:48px 48px 100px;background:white}h1{margin:3em 0 1em;line-height:1.5;font-size:30px;color:#1b5142;scroll-margin-top:24px}h1:first-child{margin-top:0;font-size:38px}h2{font-size:23px;line-height:1.6}h3{font-size:19px;margin-top:2em}a{color:#12614d}p{margin:1em 0}code{font:0.9em/1.7 Menlo,Consolas,monospace;background:#edf3ef;padding:2px 4px;border-radius:4px}pre{padding:18px;background:#edf3ef;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere}pre code{padding:0;background:none}.table-wrap{overflow:auto}table{border-collapse:collapse;width:100%;font-size:15px;margin:24px 0}th,td{text-align:left;vertical-align:top;border:1px solid #cddad2;padding:9px 12px}th{background:#edf3ef}li{margin:8px 0}@media(max-width:1000px){aside{position:static;width:auto;max-height:280px}main{margin:0;padding:28px 24px;max-width:none}}@media print{@page{size:A4;margin:19mm}body{background:white;font-size:11pt}aside{display:none}main{max-width:none;margin:0;padding:0}h1{break-before:page;font-size:23pt}h1:first-child{break-before:auto}h2,h3{break-after:avoid}pre{font-size:9pt}tr{break-inside:avoid}a{color:inherit;text-decoration:none}table{font-size:9pt}}'''
    page='<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>从零理解有记忆的 AI 助手</title><style>'+style+'</style></head><body><aside><strong>阅读目录</strong><ul>'+navigation+'</ul></aside><main>'+body+'</main></body></html>'
    (ROOT/'reading-edition.html').write_text(page,encoding='utf-8')
    print('Built reading-edition.html:',len(toc),'top-level sections')


if __name__=='__main__':main()
