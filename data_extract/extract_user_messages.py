"""
Extrai todas as mensagens enviadas por usuarios para a agente FER (coe_copilotoRh)
e salva em um arquivo TXT, uma mensagem por linha.

Filtros:
- Apenas o agente FER (bot_conversationtranscriptid.schemaname == 'coe_copilotoRh')
- Apenas conversas reais (exclui isDesignMode == True e channelId == 'pva-studio')
- Apenas mensagens com role == 1 (usuario) e type == 'message'

Saida: user_messages_fer.txt
"""

import io
import json
import re
import sys

import pandas as pd

CSV_PATH = "conversationtranscripts.csv"
OUTPUT_PATH = "user_messages_fer.txt"
AGENT_COLUMN = "bot_conversationtranscriptid.schemaname"
TARGET_AGENT = "coe_copilotoRh"

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def is_real_conversation(activities: list) -> bool:
    for act in activities:
        if act.get("valueType") == "ConversationInfo":
            value = act.get("value", {}) or {}
            if value.get("isDesignMode") is True:
                return False
        if act.get("channelId") == "pva-studio":
            return False
    return True


def extract_user_messages(csv_path: str, output_path: str) -> dict:
    df = pd.read_csv(csv_path)
    df = df[df[AGENT_COLUMN] == TARGET_AGENT].copy()
    print(f"Linhas da FER no CSV: {len(df)}")

    df["conversation_date"] = pd.to_datetime(df["conversationstarttime"], errors="coerce")
    df = df.sort_values("conversation_date", na_position="last")

    total_messages = 0
    skipped_studio = 0
    skipped_parse_error = 0
    skipped_empty = 0

    with open(output_path, "w", encoding="utf-8") as out:
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

            for act in activities:
                from_data = act.get("from", {}) or {}
                if from_data.get("role") != 1:
                    continue
                if act.get("type") != "message":
                    continue

                text = act.get("text", "") or ""
                if not isinstance(text, str):
                    continue

                clean = re.sub(r"\s+", " ", text).strip()
                if not clean:
                    skipped_empty += 1
                    continue

                out.write(clean + "\n")
                total_messages += 1

    return {
        "total_mensagens_salvas": total_messages,
        "linhas_descartadas_studio_design": skipped_studio,
        "linhas_descartadas_parse_error": skipped_parse_error,
        "mensagens_descartadas_vazias": skipped_empty,
        "arquivo_saida": output_path,
    }


if __name__ == "__main__":
    stats = extract_user_messages(CSV_PATH, OUTPUT_PATH)
    print()
    print("=" * 60)
    print("EXTRACAO CONCLUIDA")
    print("=" * 60)
    for k, v in stats.items():
        print(f"  {k:<40} {v}")
    print("=" * 60)
