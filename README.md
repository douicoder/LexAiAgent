<h1 align="center"><b>AGENTIC & AUTONOMOUS SYSTEMS</b></h1>

<p align="center"><i>Theme Submission for Hackathon 2026</i></p>

---

# Lex Agent

> its an ai powered legal aid for anyone(for now only includes some indian laws regarding land disputes)
---
## What is Lex Agent??

its a simple website where a user can explain there legal matter in plain english and agent help ordinary people understand their legal rights and explains it in plain english , for free...

**How it works(for the user):**
1. You explain your problem in english
2. The Agent classifies the legal matter(Case type, Legal Doamin, and severity)
3. Provides a simple summary
4. finds the law chunks from teh database
5. Provides a case Radiness Score and...
and gives a evidence check list ... to imporve the case rediness score

6. Provides a recommended action plan
7. Provides some ai genrated notice and letters. which might come in handy

**Scalable:** if a the admin wants to add more laws the person needs to put the law documents in the `backend/law_docs` and run `scripts/ingest_laws.py` (currently only laws regarding land disputes are present in teh database)

## How it works under the hood

### The 4-Phase Pipeline(i know it sounds cool)


```
Your Description
       │
       ▼
┌─────────────────────┐
│  Phase 1: Classify   │  What type of case? Is the input clear enough?
│  (2 parallel LLMs)  │  If vague → returns "Insufficient data to proceed"
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Phase 2: RAG        │  Search law acts for relevant sections
│  Vector + BM25       │  using semantic search + keyword matching
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Phase 3: Generate   │  Generate evidence checklist, legal notice,
│  (4 parallel LLMs)   │  supporting docs, and action plan
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Phase 4: Assemble   │  Parse results, score readiness, build response
└─────────┬───────────┘
          │
          ▼
    Complete Case Analysis

[This was ai genrated(the flow chanrt i mean)]
```

**Total Time:** ~60-90 sec

## Tech Stack


| Layer | Technology |
|-------|------------|
| **Frontend** | Flask, TailwindCSS, Vanilla JS |
| **Backend** | FastAPI, Python 3.11 |
| **LLM** | Google Gemini 2.0 Flash (via OpenRouter) |
| **Embeddings** | OpenAI text-embedding-3-small (via GitHub Models) |
| **Database** | Supabase (PostgreSQL + pgvector) |
| **PDF Generation** | ReportLab

## Limitations

- Rate limits on free apis sometimes proivide delays

- Sometimes the backend server takes a long time wake up(cause i am using the free tier) (in the deployment)

- sometimes the application breaks (i have fixed it a bunch of times and henvent seen anything break but it might)

## Future scope

- Multi languge support for indian languges

- voice transcibtion

- Conversational chat interface(like claude or other ai platforms)

- Case management and tracking(by adding auth and storiung rach report in the database if the user is logged in)

## Ai usage
i did use ai to help me make this project but i know everthign happening in the project and can explain it if needed in future..... i designed the project on my on and i am positive that it is not considered as ai slop as there was actual thiniking that i neede to do i thought of the designed and stuff and know why a certain piece of code was implemented


## License

This project is for educational and demonstration purposes.
