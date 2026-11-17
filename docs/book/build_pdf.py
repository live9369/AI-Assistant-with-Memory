"""Optional print edition; requires reportlab and a TrueType font covering Chinese."""
import argparse
from pathlib import Path
import re
from html import escape
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, Preformatted

ROOT=Path(__file__).resolve().parent


def inline(text):
    text=escape(text)
    text=re.sub(r'`([^`]+)`',r'<font color="#185d46">\1</font>',text)
    text=re.sub(r'\*\*([^*]+)\*\*',r'<b>\1</b>',text)
    return re.sub(r'\[([^\]]+)\]\((https?://[^)]+)\)',r'<link href="\2" color="#185d46">\1</link>',text)


class Book(SimpleDocTemplate):
    def afterFlowable(self,flowable):
        if hasattr(flowable,'book_title'):
            self.canv.bookmarkPage(flowable.book_anchor)
            self.canv.addOutlineEntry(flowable.book_title,flowable.book_anchor,level=0)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--font',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    pdfmetrics.registerFont(TTFont('BookCJK',str(args.font)))
    pdfmetrics.registerFontFamily('BookCJK',normal='BookCJK',bold='BookCJK',italic='BookCJK',boldItalic='BookCJK')
    styles={
        'body':ParagraphStyle('body',fontName='BookCJK',fontSize=10,leading=17,spaceAfter=10,wordWrap='CJK'),
        'title':ParagraphStyle('title',fontName='BookCJK',fontSize=25,leading=36,spaceAfter=22,wordWrap='CJK'),
        'h1':ParagraphStyle('h1',fontName='BookCJK',fontSize=19,leading=28,spaceAfter=18,wordWrap='CJK'),
        'h2':ParagraphStyle('h2',fontName='BookCJK',fontSize=14,leading=22,spaceBefore=10,spaceAfter=10,wordWrap='CJK'),
        'h3':ParagraphStyle('h3',fontName='BookCJK',fontSize=12,leading=20,spaceBefore=10,spaceAfter=8,wordWrap='CJK'),
        'cell':ParagraphStyle('cell',fontName='BookCJK',fontSize=8,leading=12,wordWrap='CJK'),
        'code':ParagraphStyle('code',fontName='BookCJK',fontSize=8,leading=12,backColor=colors.HexColor('#f0f5f2'),borderPadding=7,spaceAfter=12)}
    styles['compact_body']=ParagraphStyle('compact_body',parent=styles['body'],leading=16,spaceAfter=6)
    styles['compact_h3']=ParagraphStyle('compact_h3',parent=styles['h3'],spaceBefore=5,spaceAfter=4,leading=17)
    lines=(ROOT/'manuscript.md').read_text().splitlines();story=[];i=0;section=0;width=A4[0]-100
    while i<len(lines):
        line=lines[i]
        if not line.strip():i+=1;continue
        if line.startswith('```'):
            content=[];i+=1
            while i<len(lines) and not lines[i].startswith('```'):content.append(lines[i]);i+=1
            wrapped=[]
            for value in content:
                current=''
                for char in value:
                    if current and pdfmetrics.stringWidth(current+char,'BookCJK',8)>width-22:
                        wrapped.append(current);current='  '+char
                    else:current+=char
                wrapped.append(current)
            story.append(Preformatted('\n'.join(wrapped),styles['code']));i+=1;continue
        h=re.match(r'^(#{1,3})\s+(.+)$',line)
        if h:
            level=len(h[1]);text=h[2]
            if level==1 and section:
                story.append(PageBreak())
                if section==1:
                    story.append(Paragraph('目录',styles['h1']))
                    chapter_titles=[value[2:] for value in lines if value.startswith('# 第')]
                    toc_rows=[]
                    for index in range(16):
                        toc_rows.append([Paragraph(inline(chapter_titles[index]),styles['cell']),Paragraph(inline(chapter_titles[index+16]),styles['cell'])])
                    toc_table=Table(toc_rows,colWidths=[width/2,width/2],hAlign='LEFT')
                    toc_table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
                    story.extend([toc_table,Spacer(1,20),Paragraph('附录',styles['h2'])])
                    for value in lines:
                        if value.startswith('# 附录'):
                            story.extend([Paragraph(inline(value[2:]),styles['cell']),Spacer(1,4)])
                    story.append(PageBreak())
            style_key='title' if level==1 and section==0 else 'compact_h3' if level==3 and section==33 else 'h'+str(level)
            paragraph=Paragraph(inline(text),styles[style_key])
            if level==1:
                paragraph.book_title=text;paragraph.book_anchor='section-'+str(section);section+=1
            story.append(paragraph);i+=1;continue
        if line.startswith('|'):
            rows=[]
            while i<len(lines) and lines[i].startswith('|'):
                cells=[v.strip() for v in lines[i].strip('|').split('|')]
                if not all(re.fullmatch(r':?-+:?',v.replace(' ','')) for v in cells):rows.append(cells)
                i+=1
            count=len(rows[0]);ratios={3:[.22,.33,.45],4:[.15,.24,.31,.30]}.get(count,[1/count]*count)
            if rows[0][0]=='序号':ratios=[.07,.12,.48,.33]
            data=[[Paragraph(inline(c),styles['cell']) for c in row] for row in rows]
            table=Table(data,colWidths=[width*r for r in ratios],repeatRows=1,hAlign='LEFT')
            table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e8f0eb')),('GRID',(0,0),(-1,-1),.4,colors.HexColor('#c3d2c9')),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
            if rows[0][0]=='想回答的问题':
                table.setStyle(TableStyle([('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),3)]))
            story.extend([table,Spacer(1,12)]);continue
        paragraph=[line];i+=1
        while i<len(lines) and lines[i].strip() and not re.match(r'^(#|```|\||- |\d+\. )',lines[i]):paragraph.append(lines[i]);i+=1
        story.append(Paragraph(inline(' '.join(paragraph)),styles['compact_body' if section==33 else 'body']))
    def page_number(canvas,doc):
        canvas.saveState();canvas.setFont('BookCJK',8);canvas.setFillColor(colors.HexColor('#61736a'))
        canvas.drawString(50,28,'有记忆的 AI 助手  中文教材 V0.2');canvas.drawRightString(A4[0]-50,28,str(doc.page));canvas.restoreState()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    doc=Book(str(args.output),pagesize=A4,rightMargin=50,leftMargin=50,topMargin=48,bottomMargin=46,title='从零理解有记忆的 AI 助手',author='AI Assistant with Memory contributors')
    doc.build(story,onFirstPage=page_number,onLaterPages=page_number)
    print('Built',args.output)


if __name__=='__main__':main()
