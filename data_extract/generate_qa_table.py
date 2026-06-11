"""
Gera tabela Excel com pares Pergunta/Resposta extraídos de conversationtranscripts.csv.

Cada linha da tabela representa UMA pergunta do usuário e a respectiva resposta do agente,
com informações de feedback associado.

Parâmetros configuráveis (altere nas variáveis abaixo):
- TARGET_AGENT: nome do agente a filtrar
- START_DATE: data mínima das conversas a considerar (formato "AAAA-MM-DD")
"""

import io
import json
import os
import sys
from datetime import datetime

import pandas as pd

# ============================================================================
# PARÂMETROS CONFIGURÁVEIS
# ============================================================================

TARGET_AGENT = "Assistente Virtual OptMove"
START_DATE = "2026-01-01"

# ============================================================================
# CAMINHOS
# ============================================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)

CSV_PATH = os.path.join(PROJECT_DIR, "conversationtranscripts_hml.csv")
USERS_CSV_PATH = os.path.join(PROJECT_DIR, "usuarios.csv")
OUTPUT_DIR = os.path.join(PROJECT_DIR, "excel generator", "generatedTables")

AGENT_COLUMN = "_bot_conversationtranscriptid_value@OData.Community.Display.V1.FormattedValue"

# ============================================================================
# FUNÇÕES AUXILIARES
# ============================================================================

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def load_user_map(users_path: str) -> dict:
    """Carrega mapa aadObjectId -> displayName a partir do arquivo de usuários."""
    df_users = pd.read_csv(users_path, sep=";", encoding="latin-1")
    return dict(zip(df_users["id"], df_users["displayName"]))


def is_real_conversation(activities: list) -> bool:
    """Descarta conversas de design/studio."""
    for act in activities:
        if act.get("valueType") == "ConversationInfo":
            value = act.get("value", {}) or {}
            if value.get("isDesignMode") is True:
                return False
        if act.get("channelId") == "pva-studio":
            return False
    return True


def format_activity_timestamp(ts) -> str:
    """Converte timestamp Unix (segundos) para string legível."""
    try:
        dt = datetime.fromtimestamp(int(ts), tz=None)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError, OSError):
        return str(ts) if ts else ""


def extract_feedback_text(action_value: dict) -> str:
    """Extrai o texto descritivo do feedback a partir do campo 'feedback' (JSON string)."""
    try:
        feedback_str = action_value.get("feedback", "{}")
        if isinstance(feedback_str, str):
            feedback_data = json.loads(feedback_str)
            return feedback_data.get("feedbackText", "")
        return ""
    except (json.JSONDecodeError, AttributeError):
        return ""


def build_global_feedback_map(df: pd.DataFrame) -> dict:
    """
    Varre TODAS as linhas filtradas para construir mapa global de feedbacks.
    Retorna: {bot_msg_id: [{"reaction": ..., "text": ...}, ...]}

    Captura feedbacks do tipo invoke com actionName='feedback'.
    Usa replyToId para associar ao ID da mensagem do bot.
    Quando replyToId não é encontrado, aplica heurística temporal
    (busca a mensagem de bot mais próxima antes do feedback na mesma linha).
    """
    global_feedbacks = {}
    all_bot_ids = set()

    for _, row in df.iterrows():
        try:
            data = json.loads(row["content"])
        except (json.JSONDecodeError, TypeError):
            continue

        activities = data.get("activities", []) or []
        activities.sort(key=lambda x: x.get("timestamp", 0))

        for act in activities:
            act_id = act.get("id")
            if not act_id:
                continue
            role = act.get("from", {}).get("role")
            if role == 0:
                if act.get("type") == "message":
                    all_bot_ids.add(act_id)
                elif (act.get("type") == "trace" and
                      act.get("valueType") == "VariableAssignment" and
                      act.get("value", {}).get("name") == "GeneratedAnswer"):
                    all_bot_ids.add(act_id)

    for _, row in df.iterrows():
        try:
            data = json.loads(row["content"])
        except (json.JSONDecodeError, TypeError):
            continue

        activities = data.get("activities", []) or []
        activities.sort(key=lambda x: x.get("timestamp", 0))

        for i, act in enumerate(activities):
            if not (act.get("type") == "invoke" and
                    act.get("name") == "message/submitAction"):
                continue
            value = act.get("value", {})
            if value.get("actionName") != "feedback":
                continue

            action_value = value.get("actionValue", {})
            reaction = action_value.get("reaction", "")
            text = extract_feedback_text(action_value)
            feedback_entry = {"reaction": reaction, "text": text}

            reply_to = act.get("replyToId")
            target_id = None

            if reply_to and reply_to in all_bot_ids:
                target_id = reply_to
            else:
                for j in range(i - 1, -1, -1):
                    cand = activities[j]
                    cand_role = cand.get("from", {}).get("role")
                    cand_id = cand.get("id")
                    if cand_role != 0 or not cand_id:
                        continue
                    is_bot_msg = cand.get("type") == "message"
                    is_gen_answer = (
                        cand.get("type") == "trace" and
                        cand.get("valueType") == "VariableAssignment" and
                        cand.get("value", {}).get("name") == "GeneratedAnswer"
                    )
                    if is_bot_msg or is_gen_answer:
                        target_id = cand_id
                        break

            if target_id:
                if target_id not in global_feedbacks:
                    global_feedbacks[target_id] = []
                global_feedbacks[target_id].append(feedback_entry)

    return global_feedbacks


def find_bot_response_with_ids(activities: list, start_idx: int) -> tuple:
    """
    A partir de start_idx, procura a próxima resposta do bot (role=0).
    Retorna (texto_da_resposta, set_de_ids_bot) onde set_de_ids_bot contém
    TODOS os IDs de mensagens/traces do bot entre a pergunta e a próxima pergunta.
    """
    bot_ids = set()
    best_text = None

    for j in range(start_idx, len(activities)):
        act = activities[j]
        role = act.get("from", {}).get("role")

        if role == 1 and act.get("type") == "message":
            break

        if role == 0:
            act_id = act.get("id")

            if (act.get("type") == "trace" and
                    act.get("valueType") == "VariableAssignment" and
                    act.get("value", {}).get("name") == "GeneratedAnswer"):
                if act_id:
                    bot_ids.add(act_id)
                text = act.get("value", {}).get("newValue", "").strip()
                if text and best_text is None:
                    best_text = text

            elif act.get("type") == "message":
                if act_id:
                    bot_ids.add(act_id)
                text = act.get("text", "").strip()
                if text and best_text is None:
                    best_text = text

    return best_text, bot_ids


def process_row(row, user_map: dict, global_feedback_map: dict) -> list:
    """
    Processa uma linha do CSV e retorna lista de dicts (uma por par pergunta/resposta).
    """
    try:
        data = json.loads(row["content"])
    except (json.JSONDecodeError, TypeError):
        return []

    activities = data.get("activities", []) or []
    if not is_real_conversation(activities):
        return []

    activities.sort(key=lambda x: x.get("timestamp", 0))

    session_id = row.get("conversationtranscriptid", "")
    results = []

    for i, act in enumerate(activities):
        if act.get("type") != "message":
            continue
        if act.get("from", {}).get("role") != 1:
            continue

        question_text = (act.get("text", "") or "").strip()
        if not question_text:
            continue

        aad_id = act.get("from", {}).get("aadObjectId", "")
        user_name = user_map.get(aad_id, "-")
        question_time = format_activity_timestamp(act.get("timestamp"))

        bot_response, bot_ids = find_bot_response_with_ids(activities, i + 1)

        feedback_reaction = "-"
        feedback_text = "-"
        for bid in bot_ids:
            if bid in global_feedback_map:
                feedbacks = global_feedback_map[bid]
                if feedbacks:
                    feedback_reaction = feedbacks[0].get("reaction", "") or "-"
                    feedback_text = feedbacks[0].get("text", "") or "-"
                    break

        results.append({
            "ID Sessão": session_id,
            "Data/Hora Pergunta": question_time,
            "Usuário": user_name,
            "Pergunta": question_text,
            "Resposta": bot_response or "",
            "Feedback": feedback_reaction,
            "Descritivo Feedback": feedback_text,
        })

    return results


def generate_output_filename(agent: str, start_date: str) -> str:
    """Gera nome de arquivo único com informações de agente, data início e data de geração."""
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_agent = agent.replace(" ", "_")
    safe_date = start_date.replace("-", "")
    return f"QA_{safe_agent}_desde{safe_date}_gerado{now}.xlsx"


# ============================================================================
# EXECUÇÃO PRINCIPAL
# ============================================================================

def main():
    print(f"Agente selecionado: {TARGET_AGENT}")
    print(f"Data início: {START_DATE}")
    print(f"CSV: {CSV_PATH}")
    print(f"Usuários: {USERS_CSV_PATH}")
    print()

    user_map = load_user_map(USERS_CSV_PATH)
    print(f"Usuários carregados: {len(user_map)}")

    df = pd.read_csv(CSV_PATH)
    print(f"Total de linhas no CSV: {len(df)}")

    df = df[df[AGENT_COLUMN] == TARGET_AGENT].copy()
    print(f"Linhas do agente '{TARGET_AGENT}': {len(df)}")

    df["conversation_date"] = pd.to_datetime(
        df["conversationstarttime"], errors="coerce", utc=True
    )
    start_dt = pd.Timestamp(START_DATE, tz="UTC")
    df = df[df["conversation_date"] >= start_dt].copy()
    print(f"Linhas após filtro de data (>= {START_DATE}): {len(df)}")

    print("\nConstruindo mapa global de feedbacks...")
    global_feedback_map = build_global_feedback_map(df)
    total_feedbacks = sum(len(v) for v in global_feedback_map.values())
    print(f"Feedbacks mapeados: {total_feedbacks}")
    print()

    print("Extraindo pares Pergunta/Resposta...")
    all_rows = []
    for _, row in df.iterrows():
        qa_pairs = process_row(row, user_map, global_feedback_map)
        all_rows.extend(qa_pairs)

    print(f"Total de pares Pergunta/Resposta extraídos: {len(all_rows)}")

    if not all_rows:
        print("Nenhum dado encontrado com os filtros aplicados.")
        return

    df_output = pd.DataFrame(all_rows)

    feedbacks_found = df_output[df_output["Feedback"] != "-"]
    print(f"Pares com feedback: {len(feedbacks_found)}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filename = generate_output_filename(TARGET_AGENT, START_DATE)
    output_path = os.path.join(OUTPUT_DIR, filename)

    df_output.to_excel(output_path, index=False, engine="openpyxl")
    print(f"\nArquivo salvo em: {output_path}")
    print(f"Total de linhas na tabela: {len(df_output)}")


if __name__ == "__main__":
    main()
