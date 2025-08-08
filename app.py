# 북클라이밍 - 독서의 정상에 도전하라  – 2025‑05‑08
import streamlit as st, requests, re, json, base64, time, mimetypes, uuid, datetime, random
from bs4 import BeautifulSoup
from openai import OpenAI

# ───── API 키 ─────
OPENAI_API_KEY      = st.secrets["OPENAI_API_KEY"]
NAVER_CLIENT_ID     = st.secrets["NAVER_CLIENT_ID"]
NAVER_CLIENT_SECRET = st.secrets["NAVER_CLIENT_SECRET"]
NAVER_OCR_SECRET    = st.secrets.get("NAVER_OCR_SECRET","")
client = OpenAI(api_key=OPENAI_API_KEY)

# ───── 공통 유틸 ─────
def clean_html(t): return re.sub(r"<.*?>","",t or "")
def strip_fence(t): return re.sub(r"^```(json)?|```$", "", t.strip(), flags=re.M)
def gpt(msg,t=0.5,mx=800): return client.chat.completions.create(
        model="gpt-4.1",messages=msg,temperature=t,max_tokens=mx
    ).choices[0].message.content.strip()
def to_data_url(url):
    while True:
        try:
            r=requests.get(url,timeout=5); r.raise_for_status()
            mime=r.headers.get("Content-Type") or mimetypes.guess_type(url)[0] or "image/jpeg"
            return f"data:{mime};base64,{base64.b64encode(r.content).decode()}"
        except Exception as e:
            st.warning(f"표지 다운로드 재시도… ({e})"); time.sleep(2)

# ───── GPT 퀴즈 ─────
def make_quiz(raw:str)->list:
    m=re.search(r"\[.*]", strip_fence(raw), re.S)
    if not m: return []
    try: arr=json.loads(m.group())
    except json.JSONDecodeError: return []
    quiz=[]
    for it in arr:
        if isinstance(it,str):
            try: it=json.loads(it)
            except: continue
        # 'answer' 또는 'correct_answer' 허용
        if "answer" in it and "correct_answer" not in it:
            it["correct_answer"]=it.pop("answer")
        if not {"question","options","correct_answer"}.issubset(it.keys()): continue
        opts=it["options"][:]
        if len(opts)!=4: continue
        # 정답이 숫자 → 인덱스, 문자열 → 매칭
        if isinstance(it["correct_answer"],int):
            correct_txt=opts[it["correct_answer"]-1]
        else:
            correct_txt=str(it["correct_answer"]).strip()
        random.shuffle(opts)
        quiz.append({"question":it["question"],
                     "options":opts,
                     "correct_answer":opts.index(correct_txt)+1})
    return quiz if len(quiz)==5 else []

# ───── NAVER Books & OCR ─────
def nv_search(q):
    hdr={"X-Naver-Client-Id":NAVER_CLIENT_ID,"X-Naver-Client-Secret":NAVER_CLIENT_SECRET}
    return requests.get("https://openapi.naver.com/v1/search/book.json",
                        headers=hdr,params={"query":q,"display":10}).json().get("items",[])
def crawl_syn(title):
    hdr={"User-Agent":"Mozilla/5.0"}
    soup=BeautifulSoup(requests.get(f"https://book.naver.com/search/search.nhn?query={title}",hdr).text,"html.parser")
    f=soup.select_one("ul.list_type1 li a")
    if not f: return ""
    intro=BeautifulSoup(requests.get("https://book.naver.com"+f["href"],hdr).text,"html.parser").find("div","book_intro")
    return intro.get_text("\n").strip() if intro else ""
def synopsis(title,b): d=clean_html(b.get("description","")); c=crawl_syn(title); return d+"\n\n"+c if c else d
def elem_syn(title,s): return gpt([{"role":"user","content":f"책 '{title}' 줄거리를 초등학생 수준에 맞춰서 반드시 끝까지 작성해줘. 반드시 전체 다 출력하여야 한다. 중간에 문장이 끊어져서는는 안된다. 할루시네이션이 일어나서는 안된다. 꼭 정확한 근거를 가지고 줄거리를 작성하여라.\n\n원본:\n{s}"}],0.4,2000)
def nv_ocr(img):
    url=st.secrets.get("NAVER_CLOVA_OCR_URL")
    if not url or not NAVER_OCR_SECRET: return "(OCR 설정 필요)"
    payload={"version":"V2","requestId":str(uuid.uuid4()),
             "timestamp":int(datetime.datetime.utcnow().timestamp()*1000),
             "images":[{"name":"img","format":"jpg","data":base64.b64encode(img).decode()}]}
    res=requests.post(url,headers={"X-OCR-SECRET":NAVER_OCR_SECRET,"Content-Type":"application/json"},
                      json=payload,timeout=30).json()
    try:
        return " ".join(f["inferText"] for f in res["images"][0]["fields"])  # 줄바꿈 → 공백
    except: return "(OCR 파싱 오류)"

# ───── PAGE 1 : 책 검색 ─────
def page_book():
    st.header("📚 책 검색& 표지를 보며 예측하기")
    if st.sidebar.button("페이지 초기화"): st.session_state.clear(); st.rerun()

    q=st.text_input("책 제목·키워드")
    if st.button("검색") and q.strip():
        st.session_state.search=nv_search(q.strip())

    if bs:=st.session_state.get("search"):
        _, sel=st.selectbox("책 선택",
                            [(f"{clean_html(b['title'])} | {clean_html(b['author'])}",b) for b in bs],
                            format_func=lambda x:x[0])
        if st.button("선택"):
            st.session_state.selected_book=sel
            title=clean_html(sel["title"])
            st.session_state.synopsis=elem_syn(title,synopsis(title,sel))
            st.success("책 선택 완료!")

    if bk:=st.session_state.get("selected_book"):
        title=clean_html(bk["title"]); cover=bk["image"]; syn=st.session_state.synopsis
        st.subheader("📖 줄거리"); st.write(syn)
        lc,rc=st.columns(2)
        with lc: st.image(cover,caption=title,use_container_width=True)
        with rc:
            st.markdown("### 🖼️ 표지 챗봇 (독서 전 활동)")
            if "chat" not in st.session_state:
                st.session_state.chat=[
                    {"role":"system","content":"너는 초등 대상 책 표지에 대해 대화를 주고 받는 챗봇입니다. 사용자에게 책 표지와 관련된 질문을 던져서 책의 내용을 예측하고 책에 대해 흥미를 가질 수 있도록 질문해주세요"},
                    {"role":"user","content":[{"type":"text","text":"표지입니다."},
                                              {"type":"image_url","image_url":{"url":to_data_url(cover)}}]},
                    {"role":"assistant","content":"책 표지에서 어떤 것을 볼 수 있나요?"}]
            for m in st.session_state.chat:
                if m["role"]=="assistant": st.chat_message("assistant").write(m["content"])
                elif m["role"]=="user" and isinstance(m["content"],str):
                    st.chat_message("user").write(m["content"])
            if u:=st.chat_input("답/질문 입력…"):
                st.session_state.chat.append({"role":"user","content":u})
                rsp=gpt(st.session_state.chat,0.7,400)
                st.session_state.chat.append({"role":"assistant","content":rsp}); st.rerun()
            if st.button("➡️ 독서 퀴즈"): st.session_state.current_page="독서 퀴즈"; st.rerun()

# ───── PAGE 2 : 퀴즈 ─────
def page_quiz():
    st.header("📝 독서 퀴즈")
    if "selected_book" not in st.session_state: st.error("책을 먼저 선택!"); return
    if st.sidebar.button("퀴즈 초기화"): st.session_state.pop("quiz",None); st.session_state.pop("answers",None); st.rerun()

    title=clean_html(st.session_state.selected_book["title"])
    syn=st.session_state.synopsis
    st.markdown(f"**책 제목:** {title}")

    if "quiz" not in st.session_state and st.button("퀴즈 생성"):
        raw=gpt([{"role":"user","content":
             f"책 '{title}' 반드시 앞서 작성한 줄거리를 바탕으로 5개 4지선다 퀴즈를 JSON 배열로만 출력. "
             "각 항목에 'question', 'options'(4개), 'correct_answer'(1~4) 키를 사용하고, "
             "문항마다 정답 번호가 고르게 분포되도록 옵션을 섞어줘."+
             "\n\n줄거리:\n"+syn}],0.4,700)
        q=make_quiz(raw)
        if q: st.session_state.quiz=q
        else: st.error("형식 오류, 다시 생성"); st.code(raw)

    if q:=st.session_state.get("quiz"):
        if "answers" not in st.session_state: st.session_state.answers={}
        for i,qa in enumerate(q):
            st.markdown(f"**문제 {i+1}.** {qa['question']}")
            pick=st.radio("",qa["options"],index=None,key=f"ans{i}")
            if pick is not None:
                st.session_state.answers[i]=qa["options"].index(pick)+1
            elif i in st.session_state.answers:
                del st.session_state.answers[i]

        if st.button("채점"):
            miss=[i+1 for i in range(5) if i not in st.session_state.answers]
            if miss: st.error(f"{miss}번 문제 선택 안함"); return

            correct=[st.session_state.answers[i]==q[i]["correct_answer"] for i in range(5)]
            score=sum(correct)*20
            st.subheader("📊 채점 결과")
            for i,ok in enumerate(correct,1):
                st.write(f"문제 {i}: {'⭕' if ok else '❌'} (정답: {q[i-1]['options'][q[i-1]['correct_answer']-1]})")
            st.write(f"**총점: {score} / 100**")

            explain=gpt([{"role":"user","content":
                "다음 JSON으로 각 문항 해설과 총평을 한국어로 작성 해설과 총평은 학생이 무슨 답을 선택하였는지 확인하여 정확하게 채점을 하여야 한다.:\n"+
                json.dumps({"quiz":q,"student_answers":st.session_state.answers},ensure_ascii=False)}],0.3,800)
            st.write(explain)

        if st.button("➡️ 독서 토론"): st.session_state.current_page="독서 토론"; st.rerun()

# ───── PAGE 3 : 토론 ─────
def page_discussion():
    st.header("💬 독서 토론")
    if "selected_book" not in st.session_state: st.error("책 먼저 선택!"); return
    if st.sidebar.button("토론 초기화"):
        for k in ("debate_started","debate_round","debate_chat","debate_topic",
                  "debate_eval","user_side","bot_side","topics"): st.session_state.pop(k,None); st.rerun()

    title=clean_html(st.session_state.selected_book["title"])
    syn=st.session_state.synopsis
    st.markdown(f"**책 제목:** {title}")

    if st.button("토론 주제 추천"):
        txt=gpt([{"role":"user","content":
            f"책 '{title}' 책 줄거리와 내용을 바탕으로 초등학생 수준에 맞는 주제와 용어로 찬성과 반대가 갈리는 독서 토론 주제 2개를 추천, '~해야한다.' 로 끝나는 문장으로 출력.\n\n줄거리:\n{syn}"}],0.4,300)
        st.session_state.topics=[re.sub('^[0-9]+[). ]+','',l.strip()) for l in txt.splitlines() if l.strip()]

    if tp:=st.session_state.get("topics"):
        st.subheader("추천 주제"); [st.write("• "+t) for t in tp]

    if "debate_started" not in st.session_state:
        topic=st.text_input("토론 주제", value=(tp or [""])[0])
        side=st.radio("당신은?",("찬성","반대"))
        if st.button("토론 시작"):
            st.session_state.update({
                "debate_started":True,"debate_round":1,"debate_topic":topic,
                "user_side":side,"bot_side":"반대" if side=="찬성" else "찬성",
                "debate_chat":[{"role":"system","content":
                    f"초등 대상 토론 챗봇. 주제 '{topic}'. "
                    "1찬성입론 2반대입론 3찬성반론 4반대반론 5찬성최후 6반대최후. 책 내용과 관련지어 토론이 진행되어야 한다."
                    f"사용자 {side}, 챗봇 {('반대' if side=='찬성' else '찬성')}."}]
            }); st.rerun()

    if st.session_state.get("debate_started"):
        lbl={1:"찬성측 입론",2:"반대측 입론",3:"찬성측 반론",4:"반대측 반론",5:"찬성측 최후 변론",6:"반대측 최후 변론"}
        for m in st.session_state.debate_chat:
            if m["role"]=="assistant": st.chat_message("assistant").write(str(m["content"]))
            elif m["role"]=="user":   st.chat_message("user").write(str(m["content"]))

        rd=st.session_state.debate_round
        if rd<=6:
            st.markdown(f"### 현재: {lbl[rd]}")
            user_turn=((rd%2==1 and st.session_state.user_side=="찬성") or
                       (rd%2==0 and st.session_state.user_side=="반대"))
            if user_turn:
                txt=st.chat_input("내 발언")
                if txt:
                    st.session_state.debate_chat.append({"role":"user","content":f"[{lbl[rd]}] {txt}"})
                    st.session_state.debate_round+=1; st.rerun()
            else:
                convo=st.session_state.debate_chat+[{"role":"user","content":f"[{lbl[rd]}]"}]
                bot=gpt(convo,0.6,400)
                st.session_state.debate_chat.append({"role":"assistant","content":bot})
                st.session_state.debate_round+=1; st.rerun()
        else:
            if "debate_eval" not in st.session_state:
                st.session_state.debate_chat.append({"role":"user","content":
                    "토론 종료. 어느 측이 설득력 있었는지(100점)와 이유·피드백. 학생들에게 조금 더 부드러운 어조로 친절하게 피드백과 조언을 해주어라."})
                res=gpt(st.session_state.debate_chat,0.4,600)
                st.session_state.debate_chat.append({"role":"assistant","content":res})
                st.session_state.debate_eval=True; st.rerun()
            else:
                st.subheader("토론 평가")
                st.chat_message("assistant").write(st.session_state.debate_chat[-1]["content"])
                if st.button("➡️ 감상문 피드백"): st.session_state.current_page="독서 감상문 피드백"; st.rerun()

# ───── PAGE 4 : 감상문 피드백 ─────
def page_feedback():
    st.header("✍️ 독서 감상문 피드백")
    if st.sidebar.button("피드백 초기화"): st.session_state.pop("essay",""); st.session_state.pop("ocr_file",""); st.rerun()

    if st.session_state.get("selected_book"):
        title=clean_html(st.session_state.selected_book["title"]); syn=st.session_state.synopsis
        st.markdown(f"**책:** {title}")
    else: title="제목 없음"; syn="줄거리 없음"

    up=st.file_uploader("손글씨 사진 업로드",type=["png","jpg","jpeg"])
    if up and st.session_state.get("ocr_file")!=up.name:
        st.session_state.essay=nv_ocr(up.read())
        st.session_state.ocr_file=up.name
        st.rerun()

    essay=st.text_area("감상문 입력 또는 OCR 결과", value=st.session_state.get("essay",""), key="essay", height=240)

    if st.button("피드백 받기"):
        if not essay.strip(): st.error("감상문을 입력하거나 업로드하세요"); return
        prm=("학생 감상문에 대한 칭찬·개선점·수정 예시.\n\n"
             f"책 제목:\n{title}\n\n줄거리:\n{syn}\n\n감상문:\n{essay}")
        fb=gpt([{"role":"user","content":prm}],0.4,800)
        st.subheader("피드백 결과"); st.write(fb)

# ───── MAIN ─────
def main():
    if "current_page" not in st.session_state: st.session_state.current_page="책 검색"
    st.set_page_config("북클라이밍","📚",layout="wide")
    st.markdown("""
    <style>
      body{background:#f0f2f6;} .block-container{background:#fff;border-radius:8px;padding:20px;}
      .stButton>button{background:#4CAF50;color:#fff;border:none;border-radius:5px;padding:8px 16px;margin:5px;}
      .css-1d391kg{background:#f8f9fa;}
    </style>""",unsafe_allow_html=True)
    st.title("북클라이밍: 독서의 정상에 도전하라")

    pages={"책 검색":page_book,"독서 퀴즈":page_quiz,"독서 토론":page_discussion,"독서 감상문 피드백":page_feedback}
    sel=st.sidebar.radio("메뉴",list(pages.keys()),index=list(pages).index(st.session_state.current_page))
    st.session_state.current_page=sel
    if st.sidebar.button("전체 초기화"): st.session_state.clear(); st.rerun()

    pages[sel]()

if __name__=="__main__":
    main()



