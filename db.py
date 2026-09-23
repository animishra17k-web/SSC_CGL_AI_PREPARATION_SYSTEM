import os, re, sqlite3
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL','').strip()

class Row(dict):
    def __getattr__(self, k):
        try: return self[k]
        except KeyError: raise AttributeError(k)

class Result:
    def __init__(self, result=None, last_id=None): self.result=result; self.last_id=last_id
    def fetchone(self):
        if self.result is None: return None
        r=self.result.mappings().first()
        return Row(r) if r else None
    def fetchall(self):
        if self.result is None: return []
        return [Row(x) for x in self.result.mappings().all()]
    @property
    def lastrowid(self): return self.last_id

class DBConn:
    def __init__(self, conn, engine): self.conn=conn; self.engine=engine
    def execute(self, sql, params=()):
        from sqlalchemy import text
        # Existing app SQL uses positional ? parameters. Convert them to named params.
        if '?' in sql:
            parts=sql.split('?'); names=[]; rebuilt=parts[0]
            for i,part in enumerate(parts[1:]):
                name=f'p{i}'; names.append(name); rebuilt += ':'+name+part
            sql=rebuilt
            params={names[i]:v for i,v in enumerate(params)}
        elif isinstance(params, tuple):
            params={}
        res=self.conn.execute(text(sql), params)
        return Result(res)
    def commit(self): self.conn.commit()
    def rollback(self): self.conn.rollback()
    def close(self): self.conn.close()

def _engine():
    from sqlalchemy import create_engine
    if DATABASE_URL:
        url=DATABASE_URL
        # Supabase commonly provides postgres:// or postgresql:// URLs.
        if url.startswith('postgres://'): url='postgresql+psycopg://'+url[len('postgres://'):]
        elif url.startswith('postgresql://'): url='postgresql+psycopg://'+url[len('postgresql://'):]
        return create_engine(url, pool_pre_ping=True, pool_recycle=300)
    path=Path(os.getenv('DATABASE_PATH','data/ssc_cgl.db'))
    path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine('sqlite:///'+str(path), connect_args={'check_same_thread':False})

ENGINE=_engine()

def db():
    return DBConn(ENGINE.connect(), ENGINE)

def init():
    from sqlalchemy import text
    ddl_sqlite = [
    "CREATE TABLE IF NOT EXISTS subjects(id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL)",
    "CREATE TABLE IF NOT EXISTS topics(id INTEGER PRIMARY KEY, subject_id INTEGER NOT NULL, name TEXT NOT NULL, status TEXT DEFAULT 'unstarted', coverage REAL DEFAULT 0, mastery REAL DEFAULT 0, revision_priority REAL DEFAULT 0, last_studied TEXT, next_review TEXT, FOREIGN KEY(subject_id) REFERENCES subjects(id))",
    "CREATE TABLE IF NOT EXISTS sources(id INTEGER PRIMARY KEY, topic_id INTEGER NOT NULL, title TEXT NOT NULL, source_type TEXT, content TEXT NOT NULL, metadata TEXT, FOREIGN KEY(topic_id) REFERENCES topics(id))",
    "CREATE TABLE IF NOT EXISTS artifacts(id INTEGER PRIMARY KEY, topic_id INTEGER NOT NULL, layer TEXT NOT NULL, artifact_type TEXT NOT NULL, content TEXT NOT NULL, version INTEGER DEFAULT 1, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(topic_id) REFERENCES topics(id))",
    "CREATE TABLE IF NOT EXISTS concepts(id INTEGER PRIMARY KEY, topic_id INTEGER NOT NULL, label TEXT NOT NULL, kind TEXT NOT NULL, content TEXT NOT NULL, source_ref TEXT, UNIQUE(topic_id,label), FOREIGN KEY(topic_id) REFERENCES topics(id))",
    "CREATE TABLE IF NOT EXISTS flashcards(id INTEGER PRIMARY KEY, topic_id INTEGER NOT NULL, concept_id INTEGER, front TEXT NOT NULL, back TEXT NOT NULL, source_ref TEXT, FOREIGN KEY(topic_id) REFERENCES topics(id))",
    "CREATE TABLE IF NOT EXISTS reviews(id INTEGER PRIMARY KEY, flashcard_id INTEGER NOT NULL, rating TEXT NOT NULL, reviewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(flashcard_id) REFERENCES flashcards(id))",
    "CREATE TABLE IF NOT EXISTS questions(id INTEGER PRIMARY KEY, topic_id INTEGER NOT NULL, difficulty TEXT NOT NULL, qtype TEXT NOT NULL, prompt TEXT NOT NULL, options TEXT, answer TEXT NOT NULL, explanation TEXT, source_ref TEXT, FOREIGN KEY(topic_id) REFERENCES topics(id))",
    "CREATE TABLE IF NOT EXISTS tests(id INTEGER PRIMARY KEY, title TEXT NOT NULL, topic_id INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, submitted_at TIMESTAMP, score REAL, total INTEGER, FOREIGN KEY(topic_id) REFERENCES topics(id))",
    "CREATE TABLE IF NOT EXISTS answers(id INTEGER PRIMARY KEY, test_id INTEGER NOT NULL, question_id INTEGER NOT NULL, user_answer TEXT, correct INTEGER, error_type TEXT, error_detail TEXT, FOREIGN KEY(test_id) REFERENCES tests(id), FOREIGN KEY(question_id) REFERENCES questions(id))",
    "CREATE TABLE IF NOT EXISTS weaknesses(id INTEGER PRIMARY KEY, topic_id INTEGER NOT NULL, label TEXT NOT NULL, severity REAL DEFAULT 0, occurrences INTEGER DEFAULT 1, last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP, UNIQUE(topic_id,label), FOREIGN KEY(topic_id) REFERENCES topics(id))",
    "CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, layer TEXT NOT NULL, event_type TEXT NOT NULL, topic_id INTEGER, payload TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
    "CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    ]
    c=db()
    # PostgreSQL supports SERIAL only; use identity columns by translating INTEGER PRIMARY KEY.
    for stmt in ddl_sqlite:
        s=stmt
        if DATABASE_URL:
            s=re.sub(r'INTEGER PRIMARY KEY', 'BIGSERIAL PRIMARY KEY', s, flags=re.I)
            s=s.replace('TIMESTAMP DEFAULT CURRENT_TIMESTAMP','TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
        c.execute(s)
    c.commit(); c.close()

init()
