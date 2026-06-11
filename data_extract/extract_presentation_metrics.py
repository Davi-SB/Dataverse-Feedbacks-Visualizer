"""
Extracao de metricas de volume da agente FER (coe_copilotoRh) para apresentacao.

Filtros aplicados:
- Apenas o agente FER (bot_conversationtranscriptid.schemaname == 'coe_copilotoRh')
- Apenas conversas reais (exclui isDesignMode == True e channelId == 'pva-studio')
- Apenas ultimos 30 dias (a partir da data mais recente do CSV)

Metricas extraidas:
  Bloco 1 - Alcance:
    1.1 Usuarios unicos
    1.2 Frequencia de uso por usuario (histograma)
    1.3 Distribuicao por dia da semana

  Bloco 2 - Conteudo:
    2.1 Top topicos acionados
    2.2 Top perguntas dos usuarios
    2.3 Fontes de conhecimento mais citadas
"""

import io
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import timedelta

import pandas as pd

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

CSV_PATH = "conversationtranscripts.csv"
AGENT_COLUMN = "bot_conversationtranscriptid.schemaname"
TARGET_AGENT = "coe_copilotoRh"
TOPIC_PREFIX = "coe_copilotoRh.topic."
DAYS_WINDOW = 30

DAY_NAMES_PT = {
    0: "Segunda-feira",
    1: "Terca-feira",
    2: "Quarta-feira",
    3: "Quinta-feira",
    4: "Sexta-feira",
    5: "Sabado",
    6: "Domingo",
}

GREETING_PATTERNS = {
    "ola", "oi", "olaa", "oie", "bom dia", "boa tarde", "boa noite",
    "tudo bem", "td bem", "tudo bom", "td bom", "obrigado", "obrigada",
    "valeu", "vlw", "ok", "blz", "beleza", "tchau", "ate mais",
    "sim", "nao", "n", "s", "eai", "eaii", "fer", "teste",
    "?", ".", "..", "...",
}

STOPWORDS = {
    "a", "e", "o", "as", "os", "um", "uma", "uns", "umas",
    "de", "do", "da", "dos", "das", "no", "na", "nos", "nas",
    "em", "por", "para", "pra", "pro", "com", "sem", "sob", "sobre",
    "se", "ser", "sou", "eh", "e", "que", "qual", "quais", "quem",
    "como", "onde", "quando", "porque", "por", "qq", "ja", "mais",
    "meu", "minha", "meus", "minhas", "seu", "sua", "seus", "suas",
    "nosso", "nossa", "este", "esta", "esse", "essa", "isso", "isto",
    "aquele", "aquela", "aquilo", "ele", "ela", "eles", "elas",
    "eu", "tu", "voce", "vc", "nos", "vos", "lhe", "lhes",
    "tem", "ter", "tinha", "teve", "tive", "tive", "havera",
    "fazer", "faco", "faz", "fiz", "feito", "feita",
    "ir", "vou", "vai", "ia", "foi", "fui",
    "estar", "esta", "estou", "estava", "estamos", "estive",
    "ai", "la", "aqui", "agora", "hoje", "ontem", "amanha",
    "bem", "mal", "muito", "pouco", "tudo", "todo", "toda",
    "ola", "oi", "obrigado", "obrigada", "favor", "ajuda",
    "preciso", "queria", "gostaria", "saber", "duvida",
    "nao", "sim", "ok", "tambem", "ate", "entao", "assim",
}


def normalize(text: str) -> str:
    """Remove acentos e converte para minusculas."""
    if not isinstance(text, str):
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    no_accents = "".join(c for c in nfkd if not unicodedata.combining(c))
    return no_accents.lower().strip()


def is_greeting_only(text: str) -> bool:
    """Verifica se a mensagem e apenas uma saudacao curta sem conteudo real."""
    norm = normalize(text)
    if not norm or len(norm) < 3:
        return True
    cleaned = re.sub(r"[^\w\s]", "", norm).strip()
    if not cleaned:
        return True
    if cleaned in GREETING_PATTERNS:
        return True
    if len(cleaned.split()) <= 2 and cleaned in GREETING_PATTERNS:
        return True
    return False


def extract_keywords(text: str) -> list:
    """Extrai palavras significativas (>=4 chars, nao stopwords) de um texto."""
    norm = normalize(text)
    norm = re.sub(r"[^\w\s]", " ", norm)
    words = norm.split()
    return [w for w in words if len(w) >= 4 and w not in STOPWORDS]


def get_oldest_transcript_in_file(csv_path: str):
    """Retorna a conversa mais antiga do CSV inteiro (por conversationstarttime)."""
    df = pd.read_csv(csv_path, usecols=["conversationstarttime", AGENT_COLUMN])
    dates = pd.to_datetime(df["conversationstarttime"], errors="coerce").dropna()
    if dates.empty:
        return None
    idx_min = dates.idxmin()
    oldest = dates.min()
    agent = df.loc[idx_min, AGENT_COLUMN]
    return {
        "data_hora": oldest.strftime("%Y-%m-%d %H:%M:%S"),
        "data": str(oldest.date()),
        "agente": None if pd.isna(agent) else str(agent),
    }


def is_real_conversation(activities: list) -> bool:
    """Retorna True se a conversa NAO for um teste do studio."""
    for act in activities:
        if act.get("valueType") == "ConversationInfo":
            value = act.get("value", {}) or {}
            if value.get("isDesignMode") is True:
                return False
        if act.get("channelId") == "pva-studio":
            return False
    return True


def collect_metrics(csv_path: str) -> dict:
    df = pd.read_csv(csv_path)

    df = df[df[AGENT_COLUMN] == TARGET_AGENT].copy()
    print(f"Linhas do agente FER ({TARGET_AGENT}): {len(df)}")

    df["conversation_date"] = pd.to_datetime(
        df["conversationstarttime"], errors="coerce"
    )
    df = df.dropna(subset=["conversation_date"])

    max_date = df["conversation_date"].max()
    min_date = max_date - timedelta(days=DAYS_WINDOW)
    df = df[df["conversation_date"] > min_date]

    print(f"Janela analisada: {min_date.date()} ate {max_date.date()}")
    print(f"Linhas no periodo: {len(df)}")

    sessions_per_user = defaultdict(int)
    sessions_by_weekday = defaultdict(int)
    topic_counter = Counter()
    question_counter_norm = Counter()
    question_label_by_norm = {}
    keyword_counter = Counter()
    knowledge_source_counter = Counter()

    unique_users = set()
    valid_sessions = 0
    engaged_sessions = 0
    skipped_studio = 0
    skipped_parse_error = 0

    for _, row in df.iterrows():
        try:
            data = json.loads(row["content"])
        except (json.JSONDecodeError, TypeError):
            skipped_parse_error += 1
            continue

        activities = data.get("activities", []) or []

        if not is_real_conversation(activities):
            skipped_studio += 1
            continue

        valid_sessions += 1

        conv_date = row["conversation_date"]
        weekday = conv_date.weekday()
        sessions_by_weekday[weekday] += 1

        users_in_session = set()
        had_user_message = False

        for act in activities:
            from_data = act.get("from", {}) or {}
            role = from_data.get("role")
            user_id = from_data.get("aadObjectId")
            value_type = act.get("valueType")
            act_type = act.get("type")
            value = act.get("value", {}) or {}

            if role == 1 and act_type == "message" and user_id:
                users_in_session.add(user_id)
                had_user_message = True

                text = act.get("text", "") or ""
                if text and not is_greeting_only(text):
                    clean_text = re.sub(r"\s+", " ", text.strip())
                    if len(clean_text) <= 200:
                        norm_key = normalize(clean_text)
                        question_counter_norm[norm_key] += 1
                        if norm_key not in question_label_by_norm:
                            question_label_by_norm[norm_key] = clean_text
                    for kw in extract_keywords(text):
                        keyword_counter[kw] += 1

            if value_type == "DynamicPlanStepTriggered":
                topic_id = value.get("taskDialogId")
                if topic_id:
                    clean_topic = topic_id.replace(TOPIC_PREFIX, "")
                    topic_counter[clean_topic] += 1

            if value_type == "KnowledgeTraceData":
                for src in value.get("citedKnowledgeSources", []) or []:
                    knowledge_source_counter[src] += 1

        if had_user_message:
            engaged_sessions += 1

        for uid in users_in_session:
            sessions_per_user[uid] += 1
            unique_users.add(uid)

    freq_buckets = {"1 sessao": 0, "2 sessoes": 0, "3-5 sessoes": 0,
                    "6-10 sessoes": 0, "11-20 sessoes": 0, "21+ sessoes": 0}
    for count in sessions_per_user.values():
        if count == 1:
            freq_buckets["1 sessao"] += 1
        elif count == 2:
            freq_buckets["2 sessoes"] += 1
        elif count <= 5:
            freq_buckets["3-5 sessoes"] += 1
        elif count <= 10:
            freq_buckets["6-10 sessoes"] += 1
        elif count <= 20:
            freq_buckets["11-20 sessoes"] += 1
        else:
            freq_buckets["21+ sessoes"] += 1

    weekday_dist = {DAY_NAMES_PT[w]: sessions_by_weekday.get(w, 0) for w in range(7)}

    recurring_users = sum(1 for c in sessions_per_user.values() if c >= 2)
    pct_recurring = (recurring_users / len(unique_users) * 100) if unique_users else 0

    oldest_in_file = get_oldest_transcript_in_file(csv_path)

    return {
        "arquivo_transcricoes": {
            "mensagem_mais_antiga": oldest_in_file,
        },
        "periodo": {
            "data_inicial": str(min_date.date()),
            "data_final": str(max_date.date()),
            "dias": DAYS_WINDOW,
        },
        "diagnostico": {
            "linhas_agente_fer_total_csv": int((pd.read_csv(csv_path, usecols=[AGENT_COLUMN])[AGENT_COLUMN] == TARGET_AGENT).sum()),
            "linhas_no_periodo": len(df),
            "sessoes_validas": valid_sessions,
            "sessoes_engajadas_calc": engaged_sessions,
            "linhas_descartadas_studio_design": skipped_studio,
            "linhas_descartadas_parse_error": skipped_parse_error,
        },
        "alcance": {
            "usuarios_unicos": len(unique_users),
            "media_sessoes_por_usuario": round(
                sum(sessions_per_user.values()) / len(unique_users), 2
            ) if unique_users else 0,
            "usuarios_recorrentes": recurring_users,
            "pct_recorrentes": round(pct_recurring, 1),
            "frequencia_de_uso": freq_buckets,
            "distribuicao_por_dia_da_semana": weekday_dist,
        },
        "conteudo": {
            "ranking_completo_topicos": topic_counter.most_common(),
            "top_perguntas": [
                (question_label_by_norm[k], v)
                for k, v in question_counter_norm.most_common(20)
            ],
            "top_palavras_chave": keyword_counter.most_common(25),
            "top_fontes_conhecimento": knowledge_source_counter.most_common(10),
            "total_topicos_distintos": len(topic_counter),
            "total_acionamentos_topicos": sum(topic_counter.values()),
        },
    }


def print_report(metrics: dict):
    sep = "=" * 75
    sub = "-" * 75

    print()
    print(sep)
    print("RELATORIO DE METRICAS - AGENTE FER")
    print(sep)

    p = metrics["periodo"]
    print(f"Periodo analisado: {p['data_inicial']} ate {p['data_final']} ({p['dias']} dias)")

    oldest = metrics.get("arquivo_transcricoes", {}).get("mensagem_mais_antiga")
    if oldest:
        agente = oldest.get("agente") or "desconhecido"
        print(
            f"Conversa mais antiga no arquivo: {oldest['data_hora']} "
            f"(agente: {agente})"
        )
    else:
        print("Conversa mais antiga no arquivo: nao encontrada")
    print()

    d = metrics["diagnostico"]
    print(sub)
    print("DIAGNOSTICO DA EXTRACAO")
    print(sub)
    print(f"  Linhas FER no CSV inteiro:                {d['linhas_agente_fer_total_csv']}")
    print(f"  Linhas FER dentro dos {p['dias']} dias:           {d['linhas_no_periodo']}")
    print(f"  Sessoes validas (excluindo testes):       {d['sessoes_validas']}")
    print(f"  Sessoes engajadas (calculo proprio):      {d['sessoes_engajadas_calc']}")
    print(f"  Descartadas (design mode / pva-studio):   {d['linhas_descartadas_studio_design']}")
    print(f"  Descartadas (erro de parse):              {d['linhas_descartadas_parse_error']}")

    print()
    print(sep)
    print("BLOCO 1 - ALCANCE E ADOCAO")
    print(sep)

    a = metrics["alcance"]
    print(f"\n[1.1] Usuarios unicos: {a['usuarios_unicos']}")
    print(f"      Media de sessoes por usuario: {a['media_sessoes_por_usuario']}")
    print(f"      Usuarios recorrentes (>=2 sessoes): {a['usuarios_recorrentes']} ({a['pct_recorrentes']}%)")

    print(f"\n[1.2] Frequencia de uso por usuario:")
    total_users = a["usuarios_unicos"]
    for bucket, count in a["frequencia_de_uso"].items():
        pct = (count / total_users * 100) if total_users else 0
        bar = "#" * int(pct / 2)
        print(f"      {bucket:<18} {count:>5} usuarios ({pct:>5.1f}%) {bar}")

    print(f"\n[1.3] Distribuicao de sessoes por dia da semana:")
    max_count = max(a["distribuicao_por_dia_da_semana"].values()) if a["distribuicao_por_dia_da_semana"] else 1
    for day, count in a["distribuicao_por_dia_da_semana"].items():
        bar = "#" * int((count / max_count) * 40) if max_count else ""
        print(f"      {day:<16} {count:>5} sessoes  {bar}")

    print()
    print(sep)
    print("BLOCO 2 - CONTEUDO E TEMAS")
    print(sep)

    c = metrics["conteudo"]
    total_acion = c["total_acionamentos_topicos"]
    print(f"\n[2.1] Ranking COMPLETO dos topicos acionados ({c['total_topicos_distintos']} distintos / {total_acion} acionamentos):")
    print(f"      {'#':>2}  {'Topico':<45} {'Qtd':>6} {'%':>7}")
    print(f"      {'-'*2}  {'-'*45} {'-'*6} {'-'*7}")
    for i, (topic, count) in enumerate(c["ranking_completo_topicos"], 1):
        pct = (count / total_acion * 100) if total_acion else 0
        print(f"      {i:>2}. {topic:<45} {count:>6} {pct:>6.1f}%")

    print(f"\n[2.2] Top 20 perguntas mais frequentes:")
    for i, (q, count) in enumerate(c["top_perguntas"], 1):
        q_short = q if len(q) <= 70 else q[:67] + "..."
        print(f"      {i:>2}. ({count}x) {q_short}")

    print(f"\n[2.2b] Top 25 palavras-chave (apos remover stopwords):")
    for i, (word, count) in enumerate(c["top_palavras_chave"], 1):
        print(f"      {i:>2}. {word:<25} {count:>5}")

    print(f"\n[2.3] Top 10 fontes de conhecimento citadas:")
    for i, (src, count) in enumerate(c["top_fontes_conhecimento"], 1):
        src_short = src if len(src) <= 60 else src[:57] + "..."
        print(f"      {i:>2}. ({count}x) {src_short}")

    print()
    print(sep)


if __name__ == "__main__":
    metrics = collect_metrics(CSV_PATH)
    print_report(metrics)

    output_path = "metrics_fer.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)
    print(f"\nMetricas tambem salvas em: {output_path}")
