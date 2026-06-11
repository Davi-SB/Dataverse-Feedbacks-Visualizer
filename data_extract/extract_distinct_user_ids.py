"""
Lista os IDs distintos (aadObjectId) de usuarios de um agente a partir de uma
data inicial (CSV de conversation transcripts).

Altere as variaveis na secao CONFIGURACAO abaixo e execute:
  python extract_distinct_user_ids.py
"""

import io
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union

import pandas as pd

# =============================================================================
# CONFIGURACAO — altere aqui
# =============================================================================

# Agente (valor de bot_conversationtranscriptid.schemaname)
# Ex.: coe_copilotoRh (FER), cr61e_agenteVirtualOptMove, clone_coe_copilotoRh
TARGET_AGENT = "coe_copilotoRh"

# Data inicial (inclusiva). Formato: YYYY-MM-DD
START_DATE = "2026-05-27"

# Caminho do CSV de transcrições
SCRIPT_DIR = Path(__file__).resolve().parent
CSV_PATH = SCRIPT_DIR.parent / "conversationtranscripts.csv"

# Arquivo de saida (um aadObjectId por linha). None = imprime no terminal
OUTPUT_PATH: Optional[Path] = SCRIPT_DIR / "distinct_user_ids.txt"

# True = exclui conversas de teste (pva-studio / isDesignMode)
EXCLUDE_STUDIO = False

# True = so considera conversas em que o usuario enviou pelo menos uma mensagem
# False = considera qualquer conversa; IDs de qualquer atividade do usuario (role==1)
REQUIRE_USER_MESSAGE = True

# True = imprime cada ID no terminal alem de salvar em arquivo (se OUTPUT_PATH definido)
PRINT_TO_CONSOLE = True

# =============================================================================

AGENT_COLUMN = "bot_conversationtranscriptid.schemaname"

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def extract_distinct_user_ids(
    csv_path: Union[str, Path],
    agent: str,
    start_date: str,
    *,
    exclude_studio: bool = False,
    require_user_message: bool = True,
) -> Tuple[List[str], Dict]:
    """
    Retorna IDs distintos de usuarios (aadObjectId) em conversas com
    conversationstarttime >= start_date.

    require_user_message=True: so conversas com pelo menos uma mensagem do
    usuario (type=='message', role==1); IDs extraidos dessas mensagens.

    require_user_message=False: todas as conversas validas; IDs de qualquer
    atividade com role==1 (mensagem, invoke, evento, etc.).
    """
    filter_date = datetime.strptime(start_date, "%Y-%m-%d").date()

    df = pd.read_csv(csv_path)
    if AGENT_COLUMN not in df.columns:
        raise ValueError(f"Coluna ausente no CSV: {AGENT_COLUMN}")

    df = df[df[AGENT_COLUMN] == agent].copy()
    df["conversation_date"] = pd.to_datetime(
        df["conversationstarttime"], errors="coerce"
    ).dt.date
    df = df[df["conversation_date"] >= filter_date]

    user_ids: Set[str] = set()
    valid_conversations = 0
    skipped_parse = 0
    skipped_studio = 0
    skipped_no_user_message = 0

    for _, row in df.iterrows():
        try:
            activities = json.loads(row["content"]).get("activities", []) or []
        except (json.JSONDecodeError, TypeError):
            skipped_parse += 1
            continue

        if exclude_studio and _is_studio_or_design(activities):
            skipped_studio += 1
            continue

        if require_user_message:
            ids_in_conversation = _user_ids_from_messages(activities)
            if not ids_in_conversation:
                skipped_no_user_message += 1
                continue
        else:
            ids_in_conversation = _user_ids_from_any_activity(activities)

        valid_conversations += 1
        user_ids.update(ids_in_conversation)

    stats = {
        "agente": agent,
        "data_inicial": start_date,
        "require_user_message": require_user_message,
        "conversas_no_periodo": len(df),
        "conversas_consideradas": valid_conversations,
        "usuarios_distintos": len(user_ids),
        "linhas_descartadas_parse": skipped_parse,
        "linhas_descartadas_studio": skipped_studio if exclude_studio else 0,
        "linhas_descartadas_sem_mensagem_usuario": skipped_no_user_message,
    }
    return sorted(user_ids), stats


def _user_ids_from_any_activity(activities: list) -> Set[str]:
    """Retorna aadObjectId de usuarios presentes em qualquer atividade (role==1)."""
    ids: Set[str] = set()
    for activity in activities:
        from_data = activity.get("from", {}) or {}
        if from_data.get("role") != 1:
            continue
        user_id = from_data.get("aadObjectId")
        if user_id:
            ids.add(user_id)
    return ids


def _user_ids_from_messages(activities: list) -> Set[str]:
    """Retorna aadObjectId de usuarios que enviaram type=='message' (role==1)."""
    ids: Set[str] = set()
    for activity in activities:
        if activity.get("type") != "message":
            continue
        from_data = activity.get("from", {}) or {}
        if from_data.get("role") != 1:
            continue
        user_id = from_data.get("aadObjectId")
        if user_id:
            ids.add(user_id)
    return ids


def _is_studio_or_design(activities: list) -> bool:
    for act in activities:
        if act.get("channelId") == "pva-studio":
            return True
        if act.get("valueType") == "ConversationInfo":
            value = act.get("value", {}) or {}
            if value.get("isDesignMode") is True:
                return True
    return False


if __name__ == "__main__":
    datetime.strptime(START_DATE, "%Y-%m-%d")

    print("=" * 60)
    print("Extracao de IDs distintos de usuarios")
    print("=" * 60)
    print(f"  Agente:           {TARGET_AGENT}")
    print(f"  Data inicial:     {START_DATE}")
    print(f"  CSV:              {CSV_PATH}")
    print(f"  Excluir studio:           {EXCLUDE_STUDIO}")
    print(f"  Exigir msg. usuario:      {REQUIRE_USER_MESSAGE}")
    print(f"  Arquivo saida:            {OUTPUT_PATH or '(apenas console)'}")
    print("=" * 60)

    ids, stats = extract_distinct_user_ids(
        CSV_PATH,
        TARGET_AGENT,
        START_DATE,
        exclude_studio=EXCLUDE_STUDIO,
        require_user_message=REQUIRE_USER_MESSAGE,
    )

    if OUTPUT_PATH is not None:
        out_path = Path(OUTPUT_PATH)
        out_path.write_text("\n".join(ids) + ("\n" if ids else ""), encoding="utf-8")
        print(f"\nArquivo salvo: {out_path}")

    if PRINT_TO_CONSOLE or OUTPUT_PATH is None:
        print("\n--- IDs ---")
        for uid in ids:
            print(uid)

    print("\n" + "=" * 60)
    print("Resumo")
    print("=" * 60)
    print(f"  Conversas no periodo:      {stats['conversas_no_periodo']}")
    print(f"  Conversas consideradas:    {stats['conversas_consideradas']}")
    print(f"  Usuarios distintos:        {stats['usuarios_distintos']}")
    if stats["require_user_message"]:
        print(f"  Sem mensagem de usuario: {stats['linhas_descartadas_sem_mensagem_usuario']}")
    if EXCLUDE_STUDIO:
        print(f"  Descartadas (studio):     {stats['linhas_descartadas_studio']}")
    print(f"  Descartadas (parse):      {stats['linhas_descartadas_parse']}")
    print("=" * 60)
