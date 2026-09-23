import os, json, requests
from openai import OpenAI
from dotenv import load_dotenv
load_dotenv()

BASE = """You are a layer inside a persistent SSC CGL preparation OS.
The student is not a beginner. Use supplied source material as primary authority.
Never invent facts. Do not silently add outside content.
If external clarification is necessary, explicitly label it.
Separate source knowledge from learner-performance data.
Return ONLY the requested JSON object."""

def ask(prompt, schema_name=None, schema=None):
    provider=os.getenv("AI_PROVIDER","ollama").lower()
    if provider=="ollama":
        r=requests.post(
          os.getenv("OLLAMA_BASE_URL","http://127.0.0.1:11434")+"/api/chat",
          json={"model":os.getenv("OLLAMA_MODEL"),
                "messages":[{"role":"system","content":BASE},
                            {"role":"user","content":prompt}],
                "stream":False,
                "format":"json"}, timeout=600)
        r.raise_for_status()
        return json.loads(r.json()["message"]["content"])

    client=OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    kwargs={"model":os.environ["OPENAI_MODEL"],
            "instructions":BASE,
            "input":prompt}
    if schema:
        kwargs["text"]={"format":{"type":"json_schema","name":schema_name,
                                  "strict":True,"schema":schema}}
    resp=client.responses.create(**kwargs)
    return json.loads(resp.output_text)

def build_extract(source, subject, topic):
    return ask(f"""LAYER: EXTRACT
SUBJECT: {subject}
TOPIC: {topic}
SOURCE:
{source}

Extract atomic, testable knowledge.
Return:
{{"concepts":[{{"label":"","kind":"rule|formula|fact|definition|exception|method|distinction",
"content":"","source_ref":""}}]}}""")

def build_teach(concepts, subject, topic):
    return ask(f"""LAYER: TEACH
SUBJECT: {subject}
TOPIC: {topic}
ATOMIC KNOWLEDGE:
{json.dumps(concepts,ensure_ascii=False)}

Return:
{{"notes":[], "question_map":[{{"difficulty":"easy|moderate|advanced",
"pattern":"","recognition":"","trap":""}}], "traps":[], "external_additions":[]}}""")

def build_cards(concepts, notes, topic):
    return ask(f"""LAYER: FLASHCARD
TOPIC: {topic}
CONCEPTS:
{json.dumps(concepts,ensure_ascii=False)}
NOTES:
{json.dumps(notes,ensure_ascii=False)}

Create 30-100 high-value recall cards. One focused fact/rule per card.
Return {{"cards":[{{"front":"","back":"","source_ref":"","concept_label":""}}]}}""")

def build_questions(concepts, qmap, topic, n):
    return ask(f"""LAYER: QUESTION
TOPIC: {topic}
KNOWLEDGE:
{json.dumps(concepts,ensure_ascii=False)}
QUESTION MAP:
{json.dumps(qmap,ensure_ascii=False)}

Create exactly {n} SSC-style questions when source supports it.
Mix supported difficulty and question types. Do not fabricate unsupported facts.
Return:
{{"questions":[{{"difficulty":"easy|moderate|advanced","qtype":"",
"prompt":"","options":[],"answer":"","explanation":"","source_ref":""}}]}}""")

def validate(pack):
    return ask(f"""LAYER: VALIDATE
Review the following generated study pack:
{json.dumps(pack,ensure_ascii=False)}

Find unsupported claims, ambiguous questions, wrong answers, duplicates,
overly trivial cards, and source-traceability problems.
Return:
{{"valid":true,"issues":[{{"type":"","item":"","severity":"high|medium|low","fix":""}}]}}""")

def evaluate(topic, questions, answers):
    return ask(f"""LAYER: EVALUATE
TOPIC: {topic}
QUESTIONS AND ANSWERS:
{json.dumps(list(zip(questions,answers)),ensure_ascii=False)}

Return:
{{"score":0,"total":0,"percentage":0,
"items":[{{"question_id":0,"correct":true,"error_type":"",
"error_detail":"","repair_skill":""}}],
"weaknesses":[{{"label":"","severity":1,"reason":""}}],
"repair_actions":[{{"action":"","priority":"high|medium|low"}}]}}
Error types: concept_gap, recall_gap, formula_rule_gap, application_error,
misread_question, calculation_error, careless_error, vocabulary_gap,
fact_gap, time_pressure, guessing, other.""")
