import json, os, csv, secrets
from pathlib import Path
from fastapi import FastAPI, Form, UploadFile, File, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from dotenv import load_dotenv
load_dotenv()
from .db import db
from .pipeline import run
from .ai import evaluate

app=FastAPI(title='SSC CGL AI Preparation OS V3')
ROOT=Path(__file__).resolve().parent; STATIC=ROOT/'static'; EXPORT=ROOT.parent/'exports'; EXPORT.mkdir(exist_ok=True)
security=HTTPBasic()

def auth(credentials: HTTPBasicCredentials=Depends(security)):
    password=os.getenv('APP_PASSWORD','').strip()
    if not password: return True
    ok=secrets.compare_digest(credentials.username, os.getenv('APP_USERNAME','student')) and secrets.compare_digest(credentials.password,password)
    if not ok: raise HTTPException(status_code=401,detail='Authentication required',headers={'WWW-Authenticate':'Basic'})
    return True

@app.get('/',response_class=HTMLResponse)
def home(_:bool=Depends(auth)): return (STATIC/'index.html').read_text(encoding='utf8')
@app.get('/health')
def health(): return {'ok':True,'service':'ssc-cgl-ai-v3'}
@app.get('/manifest.json')
def manifest(): return FileResponse(STATIC/'manifest.json',media_type='application/manifest+json')
@app.get('/sw.js')
def sw(): return FileResponse(STATIC/'sw.js',media_type='application/javascript')

@app.get('/api/subjects')
def subjects(_:bool=Depends(auth)):
 c=db(); r=[dict(x) for x in c.execute('SELECT * FROM subjects ORDER BY name').fetchall()]; c.close(); return r
@app.post('/api/subjects')
def add_subject(name:str=Form(...),_:bool=Depends(auth)):
 c=db(); c.execute('INSERT INTO subjects(name) VALUES(?) ON CONFLICT(name) DO NOTHING',(name.strip(),)); c.commit(); r=dict(c.execute('SELECT * FROM subjects WHERE name=?',(name.strip(),)).fetchone()); c.close(); return r
@app.get('/api/topics')
def topics(_:bool=Depends(auth)):
 c=db(); r=[dict(x) for x in c.execute('SELECT topics.*,subjects.name subject FROM topics JOIN subjects ON subjects.id=topics.subject_id ORDER BY subjects.name,topics.name').fetchall()]; c.close(); return r
@app.post('/api/topics')
def add_topic(subject_id:int=Form(...),name:str=Form(...),_:bool=Depends(auth)):
 c=db(); existing=c.execute('SELECT * FROM topics WHERE subject_id=? AND name=?',(subject_id,name.strip())).fetchone()
 if existing: c.close(); return dict(existing)
 c.execute('INSERT INTO topics(subject_id,name) VALUES(?,?)',(subject_id,name.strip())); c.commit(); r=c.execute('SELECT * FROM topics WHERE subject_id=? AND name=?',(subject_id,name.strip())).fetchone(); c.close(); return dict(r)

@app.post('/api/sources')
async def add_source(topic_id:int=Form(...),title:str=Form(''),content:str=Form(''),file:UploadFile|None=File(None),_:bool=Depends(auth)):
 if file and file.filename:
  raw=await file.read()
  if file.filename.lower().endswith('.pdf'):
   from pypdf import PdfReader; import io
   content='\n'.join((p.extract_text() or '') for p in PdfReader(io.BytesIO(raw)).pages)
  elif file.filename.lower().endswith('.docx'):
   from docx import Document; import io
   content='\n'.join(p.text for p in Document(io.BytesIO(raw)).paragraphs)
  else: content=raw.decode('utf8','ignore')
 if not content.strip(): return JSONResponse({'error':'Empty source'},400)
 title=(title.strip() or (file.filename if file else 'Untitled source'))
 c=db(); c.execute('INSERT INTO sources(topic_id,title,source_type,content) VALUES(?,?,?,?)',(topic_id,title,'file' if file else 'text',content)); c.commit(); sid=c.execute('SELECT id FROM sources WHERE topic_id=? AND title=? ORDER BY id DESC LIMIT 1',(topic_id,title)).fetchone()['id']; c.close(); return {'id':sid}

@app.post('/api/topics/{topic_id}/build')
def build(topic_id:int,question_count:int=60,_:bool=Depends(auth)):
 try: return run(topic_id,min(max(question_count,10),100))
 except Exception as e: return JSONResponse({'error':str(e)},500)
@app.get('/api/topics/{topic_id}/questions')
def questions(topic_id:int,limit:int=20,_:bool=Depends(auth)):
 c=db(); rows=c.execute('SELECT id,difficulty,qtype,prompt,options FROM questions WHERE topic_id=? ORDER BY RANDOM() LIMIT ?',(topic_id,min(max(limit,1),100))).fetchall(); c.close(); out=[]
 for r in rows:
  x=dict(r); x['options']=json.loads(x['options'] or '[]'); out.append(x)
 return out
@app.post('/api/tests')
def create_test(title:str=Form(...),topic_id:int=Form(...),question_ids:str=Form(...),_:bool=Depends(auth)):
 ids=[int(x) for x in question_ids.split(',') if x]; c=db(); c.execute('INSERT INTO tests(title,topic_id,total) VALUES(?,?,?)',(title,topic_id,len(ids))); tid=c.execute('SELECT id FROM tests WHERE title=? AND topic_id=? ORDER BY id DESC LIMIT 1',(title,topic_id)).fetchone()['id']
 for q in ids: c.execute('INSERT INTO answers(test_id,question_id) VALUES(?,?)',(tid,q))
 c.commit(); c.close(); return {'test_id':tid}
@app.post('/api/tests/{test_id}/submit')
def submit(test_id:int,answers_json:str=Form(...),_:bool=Depends(auth)):
 answers=json.loads(answers_json); c=db(); test=c.execute('SELECT * FROM tests WHERE id=?',(test_id,)).fetchone(); qs=c.execute('SELECT q.* FROM answers a JOIN questions q ON q.id=a.question_id WHERE a.test_id=?',(test_id,)).fetchall(); c.close()
 if not test: return JSONResponse({'error':'Test not found'},404)
 result=evaluate(test['title'],[dict(q) for q in qs],[answers.get(str(q['id']),'') for q in qs])
 c=db()
 for x in result['items']:
  c.execute('UPDATE answers SET user_answer=?,correct=?,error_type=?,error_detail=? WHERE test_id=? AND question_id=?',(answers.get(str(x['question_id']),''),int(x['correct']),x['error_type'],x['error_detail'],test_id,x['question_id']))
 for w in result['weaknesses']:
  c.execute('INSERT INTO weaknesses(topic_id,label,severity,occurrences) VALUES(?,?,?,1) ON CONFLICT(topic_id,label) DO UPDATE SET severity=excluded.severity,occurrences=occurrences+1,last_seen=CURRENT_TIMESTAMP',(test['topic_id'],w['label'],w['severity']))
 c.execute('UPDATE tests SET submitted_at=CURRENT_TIMESTAMP,score=? WHERE id=?',(result['percentage'],test_id))
 c.execute('UPDATE topics SET mastery=?,revision_priority=? WHERE id=?',(result['percentage'],max(1,11-result['percentage']/10),test['topic_id']))
 c.execute('INSERT INTO events(layer,event_type,topic_id,payload) VALUES(?,?,?,?)',('ADAPT','test_evaluated',test['topic_id'],json.dumps(result)))
 c.commit(); c.close(); return result

@app.get('/api/review/queue')
def review_queue(limit:int=20,_:bool=Depends(auth)):
 c=db(); rows=c.execute('''SELECT f.id,f.front,f.back,f.topic_id,t.name topic FROM flashcards f JOIN topics t ON t.id=f.topic_id LEFT JOIN reviews r ON r.flashcard_id=f.id WHERE r.id IS NULL OR r.reviewed_at < CURRENT_TIMESTAMP ORDER BY t.revision_priority DESC, f.id LIMIT ?''',(min(max(limit,1),100),)).fetchall(); c.close(); return [dict(x) for x in rows]

@app.post('/api/review/{flashcard_id}')
def review_flashcard(flashcard_id:int,rating:str=Form(...),_:bool=Depends(auth)):
 if rating not in {'again','hard','good','easy'}: return JSONResponse({'error':'rating must be again, hard, good or easy'},400)
 c=db(); c.execute('INSERT INTO reviews(flashcard_id,rating) VALUES(?,?)',(flashcard_id,rating)); c.commit(); c.close(); return {'ok':True}

@app.get('/api/dashboard')
def dashboard(_:bool=Depends(auth)):
 c=db(); topics=[dict(x) for x in c.execute('SELECT topics.*,subjects.name subject FROM topics JOIN subjects ON subjects.id=topics.subject_id ORDER BY revision_priority DESC,mastery ASC').fetchall()]; weaknesses=[dict(x) for x in c.execute('SELECT weaknesses.*,topics.name topic FROM weaknesses JOIN topics ON topics.id=weaknesses.topic_id ORDER BY severity DESC,occurrences DESC LIMIT 30').fetchall()]; cards=c.execute('SELECT COUNT(*) n FROM flashcards').fetchone()['n']; qs=c.execute('SELECT COUNT(*) n FROM questions').fetchone()['n']; c.close(); return {'topics':topics,'weaknesses':weaknesses,'totals':{'flashcards':cards,'questions':qs}}

@app.get('/api/topics/{topic_id}/export/anki')
def anki(topic_id:int,_:bool=Depends(auth)):
 c=db(); rows=c.execute('SELECT front,back FROM flashcards WHERE topic_id=?',(topic_id,)).fetchall(); c.close(); p=EXPORT/f'anki_{topic_id}.csv'
 with open(p,'w',newline='',encoding='utf8-sig') as f: csv.writer(f).writerows([['Front','Back']]+[[r['front'],r['back']] for r in rows])
 return FileResponse(p,filename=p.name,media_type='text/csv')
@app.get('/api/topics/{topic_id}/export/pdf')
def pdf(topic_id:int,_:bool=Depends(auth)):
 c=db(); p=c.execute("SELECT artifacts.content,topics.name topic,subjects.name subject FROM artifacts JOIN topics ON topics.id=artifacts.topic_id JOIN subjects ON subjects.id=topics.subject_id WHERE topic_id=? AND artifact_type='study_pack' ORDER BY artifacts.id DESC LIMIT 1",(topic_id,)).fetchone(); c.close()
 if not p: return JSONResponse({'error':'No study pack'},404)
 pack=json.loads(p['content']); out=EXPORT/f'notes_{topic_id}.pdf'; doc=SimpleDocTemplate(str(out),pagesize=A4,rightMargin=36,leftMargin=36,topMargin=36,bottomMargin=36); s=getSampleStyleSheet(); story=[Paragraph(f"{p['subject']} — {p['topic']}",s['Title'])]
 def add(v):
  if isinstance(v,dict):
   for k,x in v.items(): story.append(Paragraph(str(k).title(),s['Heading2'])); add(x)
  elif isinstance(v,list):
   for x in v: add(x)
  else: story.append(Paragraph(str(v).replace('&','&amp;'),s['BodyText'])); story.append(Spacer(1,5))
 add(pack.get('notes',[])); doc.build(story); return FileResponse(out,filename=out.name,media_type='application/pdf')
