import json
from .db import db
from .ai import build_extract, build_teach, build_cards, build_questions, validate

def run(topic_id, question_count=60):
    c=db()
    t=c.execute("""SELECT topics.*,subjects.name subject FROM topics
                   JOIN subjects ON subjects.id=topics.subject_id WHERE topics.id=?""",(topic_id,)).fetchone()
    src=c.execute("SELECT content FROM sources WHERE topic_id=? ORDER BY id",(topic_id,)).fetchall()
    c.close()
    if not t or not src: raise ValueError("Topic or source missing")
    source="\n\n--- SOURCE ---\n".join(x["content"] for x in src)

    concepts=build_extract(source,t["subject"],t["name"])["concepts"]
    teaching=build_teach(concepts,t["subject"],t["name"])
    cards=build_cards(concepts,teaching["notes"],t["name"])["cards"]
    qs=build_questions(concepts,teaching["question_map"],t["name"],question_count)["questions"]

    pack={"notes":teaching["notes"],"question_map":teaching["question_map"],
          "traps":teaching["traps"],"external_additions":teaching["external_additions"],
          "flashcards":cards,"questions":qs}
    validation=validate(pack)
    pack["validation"]=validation

    c=db()
    c.execute("DELETE FROM concepts WHERE topic_id=?",(topic_id,))
    for x in concepts:
        c.execute("""INSERT INTO concepts(topic_id,label,kind,content,source_ref)
                     VALUES(?,?,?,?,?) ON CONFLICT(topic_id,label) DO NOTHING""",(topic_id,x["label"],x["kind"],x["content"],x.get("source_ref","")))
    c.execute("DELETE FROM flashcards WHERE topic_id=?",(topic_id,))
    for x in cards:
        cid=c.execute("SELECT id FROM concepts WHERE topic_id=? AND label=?",
                      (topic_id,x.get("concept_label",""))).fetchone()
        c.execute("""INSERT INTO flashcards(topic_id,concept_id,front,back,source_ref)
                     VALUES(?,?,?,?,?)""",(topic_id,cid["id"] if cid else None,
                     x["front"],x["back"],x.get("source_ref","")))
    c.execute("DELETE FROM questions WHERE topic_id=?",(topic_id,))
    for x in qs:
        c.execute("""INSERT INTO questions(topic_id,difficulty,qtype,prompt,options,answer,explanation,source_ref)
                     VALUES(?,?,?,?,?,?,?,?)""",(topic_id,x["difficulty"],x["qtype"],x["prompt"],
                     json.dumps(x.get("options",[]),ensure_ascii=False),x["answer"],
                     x.get("explanation",""),x.get("source_ref","")))
    c.execute("""INSERT INTO artifacts(topic_id,layer,artifact_type,content)
                 VALUES(?,?,?,?)""",(topic_id,"PIPELINE","study_pack",json.dumps(pack,ensure_ascii=False)))
    c.execute("""UPDATE topics SET status='studied',coverage=100,
                 revision_priority=5,last_studied=CURRENT_TIMESTAMP WHERE id=?""",(topic_id,))
    c.execute("""INSERT INTO events(layer,event_type,topic_id,payload)
                 VALUES(?,?,?,?)""",("PIPELINE","study_pack_built",topic_id,
                 json.dumps({"cards":len(cards),"questions":len(qs),"validation":validation})))
    c.commit(); c.close()
    return {"cards":len(cards),"questions":len(qs),"validation":validation}
