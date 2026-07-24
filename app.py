import streamlit as st
import pandas as pd
import json
import re
import markdown as markdown_lib
from datetime import datetime
from io import BytesIO
from xhtml2pdf import pisa

debug = True

# Configuração da página
st.set_page_config(page_title="Visualizador de Transcrições", layout="wide", page_icon="💬")


# ============================================================================
# FUNÇÕES DE CACHE E OTIMIZAÇÃO
# ============================================================================

@st.cache_data(show_spinner=False)
def load_csv_data(csv_path):
    """Carrega o CSV uma única vez e cacheia."""
    if debug: print("Carregando CSV...")
    return pd.read_csv(csv_path)


@st.cache_data(show_spinner=False)
def parse_all_json_content(df_content_series):
    """
    Parseia todos os JSONs do CSV uma única vez.
    Retorna um dicionário {índice: dados_parseados}.
    """
    if debug: print("Parseando todos os JSONs do CSV...")
    parsed_data = {}
    for idx, content in enumerate(df_content_series):
        try:
            if pd.notna(content):
                parsed_data[idx] = json.loads(content)
            else:
                parsed_data[idx] = None
        except json.JSONDecodeError:
            parsed_data[idx] = None
    return parsed_data


@st.cache_data(show_spinner=False)
def build_global_id_map(df_content_series):
    """
    Constrói um mapa global de TODOS os IDs de mensagens do CSV inteiro.
    Retorna: {message_id: {'rows': [lista de índices], 'type': tipo, 'text': texto}}
    
    Isso permite buscar mensagens que estão em OUTRAS linhas do CSV.
    """
    if debug: print("Construindo mapa global de IDs...")
    global_id_map = {}
    
    for idx, content in enumerate(df_content_series):
        try:
            if pd.isna(content):
                continue
            data = json.loads(content)
            activities = data.get('activities', [])
            
            for activity in activities:
                activity_id = activity.get('id')
                if not activity_id:
                    continue
                
                if activity_id not in global_id_map:
                    global_id_map[activity_id] = {
                        'rows': [],
                        'type': activity.get('type'),
                        'text': activity.get('text', '')[:200] if activity.get('text') else '',
                        'from_role': activity.get('from', {}).get('role')
                    }
                global_id_map[activity_id]['rows'].append(idx)
        except Exception:
            continue
    
    return global_id_map


def is_design_mode_conversation(activities):
    """
    Indica se a conversa é uma sessão de teste do Copilot Studio (modo design)
    e não uma interação real de usuário.

    São consideradas de teste as conversas com isDesignMode=True em
    ConversationInfo ou originadas do canal 'pva-studio'.
    """
    for activity in activities:
        if activity.get('valueType') == 'ConversationInfo':
            value = activity.get('value') or {}
            if value.get('isDesignMode') is True:
                return True
        if activity.get('channelId') == 'pva-studio':
            return True
    return False


@st.cache_data(show_spinner=False)
def compute_design_mode_flags(df_content_series):
    """
    Marca, para cada linha do CSV, se ela é uma conversa de teste (modo design).
    Retorna uma tupla de booleanos alinhada às linhas do CSV.
    """
    if debug: print("Identificando conversas em modo design...")
    flags = []

    for content in df_content_series:
        try:
            if pd.isna(content):
                flags.append(False)
                continue
            data = json.loads(content)
            flags.append(is_design_mode_conversation(data.get('activities', [])))
        except Exception:
            flags.append(False)

    return tuple(flags)


@st.cache_data(show_spinner=False)
def compute_feedback_column(df_content_series, _all_feedbacks_map):
    """
    Calcula a coluna 'feedback' para todas as linhas de uma vez (cacheado).
    Retorna uma lista de valores ('POSITIVO', 'NEGATIVO', ou '').
    """
    if debug: print("Calculando coluna de feedback...")
    feedback_values = []
    
    for content in df_content_series:
        try:
            if pd.isna(content):
                feedback_values.append('')
                continue
                
            data = json.loads(content)
            activities = data.get('activities', [])
            
            # Coletar IDs de mensagens desta linha
            message_ids = set()
            for activity in activities:
                msg_id = activity.get('id')
                if not msg_id:
                    continue
                if activity.get('type') == 'message':
                    message_ids.add(msg_id)
                elif (activity.get('type') == 'trace' and
                      activity.get('valueType') == 'VariableAssignment' and
                      activity.get('value', {}).get('name') == 'GeneratedAnswer'):
                    message_ids.add(msg_id)
            
            # Verificar feedbacks
            has_positive = False
            has_negative = False
            has_any = False
            for msg_id in message_ids:
                feedbacks = _all_feedbacks_map.get(msg_id, [])
                for feedback in feedbacks:
                    has_any = True
                    reaction = feedback.get('reaction', '')
                    if reaction == 'like':
                        has_positive = True
                    elif reaction == 'dislike':
                        has_negative = True
            
            if has_negative:
                feedback_values.append('NEGATIVO')
            elif has_positive:
                feedback_values.append('POSITIVO')
            elif has_any:
                # Reação desconhecida: ainda assim é um feedback e não pode ser
                # descartado pelo filtro "apenas conversas com feedback".
                feedback_values.append('OUTRO')
            else:
                feedback_values.append('')
        except Exception:
            feedback_values.append('')
    
    return feedback_values


@st.cache_data(show_spinner=False)
def compute_feedback_count_column(df_content_series, _all_feedbacks_map):
    """
    Calcula a coluna 'feedback_count' para todas as linhas de uma vez (cacheado).
    Retorna uma lista com a contagem total de feedbacks por linha.
    """
    if debug: print("Calculando coluna de contagem de feedbacks...")
    feedback_counts = []
    
    for content in df_content_series:
        try:
            if pd.isna(content):
                feedback_counts.append(0)
                continue
                
            data = json.loads(content)
            activities = data.get('activities', [])
            
            # Coletar IDs de mensagens desta linha
            message_ids = set()
            for activity in activities:
                msg_id = activity.get('id')
                if not msg_id:
                    continue
                if activity.get('type') == 'message':
                    message_ids.add(msg_id)
                elif (activity.get('type') == 'trace' and
                      activity.get('valueType') == 'VariableAssignment' and
                      activity.get('value', {}).get('name') == 'GeneratedAnswer'):
                    message_ids.add(msg_id)
            
            # Contar todos os feedbacks
            total_count = 0
            for msg_id in message_ids:
                feedbacks = _all_feedbacks_map.get(msg_id, [])
                total_count += len(feedbacks)
            
            feedback_counts.append(total_count)
        except Exception:
            feedback_counts.append(0)
    
    return feedback_counts


@st.cache_data(show_spinner=False)
def compute_statistics(row_indices, _parsed_json_cache, _all_feedbacks_map, cache_token):
    """
    Conta os feedbacks das conversas indicadas por row_indices.
    Retorna: (total_positive, total_negative, total_other)

    FONTE ÚNICA DE VERDADE: percorre exatamente as mesmas mensagens que são
    renderizadas na tela e no PDF (via extract_chat_content), garantindo que
    a contagem da barra lateral e a do PDF nunca divirjam.

    Antes, a barra lateral contava feedbacks a partir de um CONJUNTO de IDs de
    mensagem, enquanto o PDF somava as caixas efetivamente renderizadas. Como
    os dois caminhos percorriam DataFrames com escopos diferentes, os números
    podiam não bater.

    cache_token identifica o arquivo/ambiente para invalidar o cache ao trocar
    de CSV (os demais parâmetros com '_' não entram na chave de cache).
    """
    if debug: print(f"Calculando estatísticas de feedback ({len(row_indices)} conversas)...")
    total_positive = 0
    total_negative = 0
    total_other = 0

    for row_idx in row_indices:
        messages = extract_chat_content(_parsed_json_cache.get(row_idx), _all_feedbacks_map)
        for msg in messages:
            for feedback in msg.get('feedbacks', []):
                reaction = feedback.get('reaction', '')
                if reaction == 'like':
                    total_positive += 1
                elif reaction == 'dislike':
                    total_negative += 1
                else:
                    total_other += 1

    return total_positive, total_negative, total_other

# CSS customizado para mensagens e feedbacks
st.markdown("""
<style>
    .message-user {
        background-color: #FFFFFF;
        border-left: 4px solid #666666;
        padding: 15px;
        margin: 10px 0;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    .message-bot {
        background-color: #E3F2FD;
        border-left: 4px solid #2196F3;
        padding: 15px;
        margin: 10px 0;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    .message-feedback-positive {
        background-color: #C8E6C9;
        border-left: 4px solid #4CAF50;
        padding: 15px;
        margin: 10px 0 10px 30px;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    .message-feedback-negative {
        background-color: #FFCDD2;
        border-left: 4px solid #F44336;
        padding: 15px;
        margin: 10px 0 10px 30px;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    .header {
        font-weight: bold;
        margin-bottom: 8px;
        display: flex;
        justify-content: space-between;
        color: #333;
    }
    
    .header span {
        font-weight: normal;
        font-size: 0.85em;
        color: #666;
    }
    
    .text {
        color: #000;
        line-height: 1.5;
    }
    
    .feedback-counter {
        color: #666;
        font-size: 0.85em;
        margin-bottom: 4px;
    }
    
    .row-number {
        background-color: #FFF3E0;
        border: 2px solid #FF9800;
        padding: 10px;
        border-radius: 8px;
        margin-bottom: 15px;
        text-align: center;
        font-weight: bold;
        color: #E65100;
    }
</style>
""", unsafe_allow_html=True)


# CSS específico para a exportação em PDF (motor xhtml2pdf/reportlab).
# Não suporta flexbox/box-shadow, por isso usa float para alinhar o horário.
PDF_CSS = """
<style>
    @page {
        size: A4;
        margin: 1.6cm;
    }
    body {
        font-family: Helvetica, Arial, sans-serif;
        font-size: 10pt;
        color: #000;
    }
    h1 {
        font-size: 18pt;
        color: #333;
    }
    .conversation-section {
        margin-bottom: 16px;
    }
    .page-break {
        page-break-after: always;
    }
    .row-number {
        background-color: #FFF3E0;
        border: 2px solid #FF9800;
        padding: 8px;
        margin-bottom: 10px;
        text-align: center;
        font-weight: bold;
        font-size: 13pt;
        color: #E65100;
    }
    .conversation-meta {
        font-size: 9pt;
        color: #555;
        margin-bottom: 10px;
    }
    .message-user, .message-bot, .message-feedback-positive, .message-feedback-negative {
        padding: 10px;
        margin: 6px 0;
        border-radius: 6px;
    }
    .message-user {
        background-color: #FFFFFF;
        border: 1px solid #CCCCCC;
        border-left: 4px solid #666666;
    }
    .message-bot {
        background-color: #E3F2FD;
        border-left: 4px solid #2196F3;
    }
    .message-feedback-positive {
        background-color: #C8E6C9;
        border-left: 4px solid #4CAF50;
        margin-left: 20px;
    }
    .message-feedback-negative {
        background-color: #FFCDD2;
        border-left: 4px solid #F44336;
        margin-left: 20px;
    }
    .msg-header {
        font-weight: bold;
        color: #333;
        margin-bottom: 10px;
    }
    table.msg-header-table {
        width: 100%;
        border-collapse: collapse;
    }
    table.msg-header-table td {
        padding: 6px 0;
        border: none;
        vertical-align: middle;
    }
    .msg-header-left {
        text-align: left;
    }
    .msg-header-right {
        text-align: right;
        font-weight: normal;
        font-size: 8pt;
        color: #666;
        white-space: nowrap;
    }
    .msg-text {
        color: #000;
        line-height: 1.4;
        word-wrap: break-word;
        overflow-wrap: break-word;
        word-break: break-all;
    }
    .msg-text p {
        margin: 0 0 6px 0;
        word-wrap: break-word;
        overflow-wrap: break-word;
        word-break: break-all;
    }
    .msg-text p:last-child {
        margin-bottom: 0;
    }
    .msg-text a {
        color: #1565C0;
    }
    .msg-text ul, .msg-text ol {
        margin: 4px 0;
        padding-left: 18px;
    }
    .no-messages {
        color: #999;
        font-style: italic;
        padding: 10px;
    }
    .badge {
        font-size: 7pt;
        padding: 1px 5px;
        border-radius: 3px;
        color: white;
        margin-left: 6px;
    }
</style>
"""


@st.cache_data(show_spinner=False)
def load_all_feedbacks(df_content_series, _global_id_map, design_flags):
    """
    Carrega TODOS os feedbacks de TODAS as linhas do CSV.
    Retorna: (all_feedbacks, orphan_count)
      - all_feedbacks: dicionário mapeando message_id -> lista de feedbacks
      - orphan_count: feedbacks que não puderam ser associados a nenhuma mensagem

    LÓGICA DE BUSCA (em ordem de prioridade):
    1. BUSCA GLOBAL POR ID: Usa o mapa global para encontrar o ID em QUALQUER linha
    2. BUSCA TEMPORAL (Heurística): Para IDs não encontrados, busca a mensagem de BOT 
       mais próxima ANTES do feedback NA MESMA LINHA
    
    TIPOS DE FEEDBACK CAPTURADOS:
    - invoke com actionName='feedback' (feedback com texto e reação like/dislike)
    
    NOTA: messageReaction não é capturado porque no dataset atual não contém 
    informação sobre o tipo de reação (like/dislike), apenas que houve interação.

    Conversas de teste (modo design) são ignoradas para que feedbacks dados
    durante testes não contaminem as métricas de uso real.

    Um feedback fica órfão quando seu replyToId aponta para uma mensagem que não
    existe em nenhuma linha do CSV (conversa de origem não exportada) e não há
    mensagem de bot anterior na mesma linha para servir de âncora.
    """
    if debug: print("Carregando todos os feedbacks...")
    all_feedbacks = {}  # {message_id: [lista de feedbacks]}
    orphan_count = 0
    
    for idx, content in enumerate(df_content_series):
        try:
            if pd.isna(content):
                continue
            if idx < len(design_flags) and design_flags[idx]:
                continue
            data = json.loads(content)
            activities = data.get('activities', [])
            
            # Ordenar atividades cronologicamente (essencial para heurística temporal)
            activities.sort(key=lambda x: x.get('timestamp', 0))
            
            # ================================================================
            # Feedbacks invoke (actionName='feedback')
            # ================================================================
            for i, activity in enumerate(activities):
                if (activity.get('type') == 'invoke' and 
                    activity.get('name') == 'message/submitAction'):
                    
                    value = activity.get('value', {})
                    if value.get('actionName') == 'feedback':
                        target_msg_id = activity.get('replyToId')
                        found_msg_id = None
                        metodo = None
                        
                        # TENTATIVA 1: Busca GLOBAL por ID (em TODAS as linhas)
                        if target_msg_id and target_msg_id in _global_id_map:
                            found_msg_id = target_msg_id
                            # Verificar se está na mesma linha ou em outra
                            rows_with_id = _global_id_map[target_msg_id]['rows']
                            if idx in rows_with_id:
                                metodo = 'ID'
                            else:
                                metodo = 'ID_CROSS'  # ID encontrado em outra linha
                        
                        # TENTATIVA 2: Busca temporal (Heurística) - fallback
                        # Procura a mensagem de BOT mais próxima ANTES deste feedback
                        if not found_msg_id:
                            for j in range(i - 1, -1, -1):
                                cand = activities[j]
                                role = cand.get('from', {}).get('role')
                                cand_id = cand.get('id')
                                
                                # Verifica se é mensagem tradicional do Bot (role 0)
                                is_bot_message = cand.get('type') == 'message' and role == 0
                                
                                # Verifica se é trace/GeneratedAnswer do Bot
                                is_generated_answer = (
                                    cand.get('type') == 'trace' and
                                    cand.get('valueType') == 'VariableAssignment' and
                                    cand.get('value', {}).get('name') == 'GeneratedAnswer' and
                                    role == 0
                                )
                                
                                if (is_bot_message or is_generated_answer) and cand_id:
                                    found_msg_id = cand_id
                                    metodo = 'TEMPO'
                                    break
                        
                        # Se encontrou a mensagem alvo, associar o feedback
                        if found_msg_id:
                            if found_msg_id not in all_feedbacks:
                                all_feedbacks[found_msg_id] = []
                            
                            feedback_data = value.get('actionValue', {}).copy()
                            feedback_data['_metodo_identificacao'] = metodo
                            all_feedbacks[found_msg_id].append(feedback_data)
                        else:
                            orphan_count += 1
                        
        except Exception:
            continue
    
    return all_feedbacks, orphan_count


def extract_feedback_column(json_string, all_feedbacks_map, _global_id_map):
    """
    Retorna POSITIVO, NEGATIVO ou vazio para a coluna feedback.
    
    Esta função verifica se as MENSAGENS desta linha receberam feedbacks,
    independentemente de em qual linha do CSV o feedback está.
    
    REGRA: A coluna 'feedback' indica se alguma mensagem DESTA linha
    recebeu feedback, não se esta linha contém atividades de feedback.
    """
    if debug: print("Extraindo coluna de feedback...")
    try:
        data = json.loads(json_string)
        activities = data.get('activities', [])
        
        # Coletar IDs de mensagens desta linha
        message_ids = set()
        for activity in activities:
            msg_id = activity.get('id')
            if not msg_id:
                continue
                
            # Mensagem tradicional
            if activity.get('type') == 'message':
                message_ids.add(msg_id)
            
            # Trace/GeneratedAnswer do Bot
            elif (activity.get('type') == 'trace' and
                  activity.get('valueType') == 'VariableAssignment' and
                  activity.get('value', {}).get('name') == 'GeneratedAnswer'):
                message_ids.add(msg_id)
        
        # Verificar se alguma mensagem desta linha recebeu feedback
        has_positive = False
        has_negative = False
        
        for msg_id in message_ids:
            feedbacks = all_feedbacks_map.get(msg_id, [])
            for feedback in feedbacks:
                reaction = feedback.get('reaction', '')
                if reaction == 'like':
                    has_positive = True
                elif reaction == 'dislike':
                    has_negative = True
        
        # Priorizar negativo se houver ambos
        if has_negative:
            return 'NEGATIVO'
        elif has_positive:
            return 'POSITIVO'
        else:
            return ''
    except Exception:
        return ''


def format_timestamp(timestamp_str):
    """
    Formata timestamp para formato legível: HH:MM:SS
    """
    try:
        # Tentar como ISO string
        dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        return dt.strftime('%H:%M:%S')
    except:
        try:
            # Tentar como timestamp Unix (segundos desde epoch)
            if isinstance(timestamp_str, (int, float)) or (isinstance(timestamp_str, str) and timestamp_str.isdigit()):
                dt = datetime.fromtimestamp(int(timestamp_str))
                return dt.strftime('%H:%M:%S')
        except:
            pass
        return str(timestamp_str)


def extract_chat_content(parsed_data, all_feedbacks_map):
    """
    Extrai mensagens de UMA linha do CSV (já parseada) e associa feedbacks de TODAS as linhas.
    
    Args:
        parsed_data: Dados JSON já parseados da linha atual
        all_feedbacks_map: Dicionário com TODOS os feedbacks do CSV inteiro
    
    Returns:
        Lista de mensagens com seus feedbacks associados
    """
    if debug: print("Extraindo conteúdo do chat...")
    try:
        if parsed_data is None:
            return []
            
        activities = parsed_data.get('activities', [])
        
        # Ordenar atividades cronologicamente para exibição correta
        activities.sort(key=lambda x: x.get('timestamp', 0))
        
        # Extrair mensagens desta linha
        messages = []
        for activity in activities:
            msg_id = activity.get('id')
            text = None
            is_user = False
            should_include = False
            
            # Mensagem tradicional
            if activity.get('type') == 'message':
                text = activity.get('text', '').strip()
                is_user = activity.get('from', {}).get('role') == 1
                
                # Verificar se tem attachments (cards visuais)
                if not text:
                    if activity.get('attachments'):
                        text = "[Conteúdo Visual/Card]"
                        should_include = True
                    else:
                        # Verificar se tem feedback associado (mensagem vazia com feedback)
                        if msg_id and msg_id in all_feedbacks_map:
                            text = "[Mensagem sem texto]"
                            should_include = True
                else:
                    should_include = True
            
            # Trace/GeneratedAnswer do Bot (nova estrutura)
            elif (activity.get('type') == 'trace' and
                  activity.get('valueType') == 'VariableAssignment' and
                  activity.get('value', {}).get('name') == 'GeneratedAnswer'):
                text = activity.get('value', {}).get('newValue', '').strip()
                is_user = False  # GeneratedAnswer é sempre do bot
                
                if text:
                    should_include = True
                elif msg_id and msg_id in all_feedbacks_map:
                    # Trace vazio mas com feedback
                    text = "[Resposta gerada vazia]"
                    should_include = True
            
            # Se encontrou uma mensagem válida ou com feedback, adicionar à lista
            if should_include and msg_id:
                # Buscar feedbacks para esta mensagem em TODAS as linhas do CSV
                feedbacks_for_this_message = all_feedbacks_map.get(msg_id, [])
                
                messages.append({
                    'id': msg_id,
                    'time': format_timestamp(activity.get('timestamp', '')),
                    'is_user': is_user,
                    'text': text,
                    'feedbacks': feedbacks_for_this_message,
                    'aadObjectId': activity.get('from', {}).get('aadObjectId', '')
                })
        
        return messages
    except Exception as e:
        st.error(f"Erro ao processar chat: {str(e)}")
        return []


def extract_feedback_text(feedback_value):
    """
    Extrai o texto do feedback do campo 'feedback' que é uma string JSON.
    """
    try:
        feedback_str = feedback_value.get('feedback', '{}')
        if isinstance(feedback_str, str):
            feedback_data = json.loads(feedback_str)
            return feedback_data.get('feedbackText', '[Sem comentário]')
        return '[Sem comentário]'
    except:
        return '[Sem comentário]'


def render_chat_message(msg):
    """
    Renderiza uma mensagem do chat com seus feedbacks (se houver).
    """
    # Determinar classe CSS baseado no tipo de mensagem
    msg_class = "message-user" if msg['is_user'] else "message-bot"
    emoji = "👤" if msg['is_user'] else "🤖"
    role = "USUÁRIO" if msg['is_user'] else "BOT"
    
    aad_id = msg.get('aadObjectId', '')
    role_display = f"{role} <span style='font-size:0.8em; color:#888;'>({aad_id})</span>" if aad_id else role
    
    # Construir HTML da mensagem
    html = f"""
    <div class="{msg_class}">
        <div class="header">{emoji} {role_display} <span>{msg['time']}</span></div>
        <div class="text">{msg['text']}</div>
    </div>
    """
    
    # Renderizar a mensagem principal
    st.markdown(html, unsafe_allow_html=True)
    
    # Renderizar feedbacks como mensagens separadas (se existirem)
    feedbacks = msg.get('feedbacks', [])
    if feedbacks:
        for idx, feedback in enumerate(feedbacks, 1):
            reaction = feedback.get('reaction', '')
            feedback_text = extract_feedback_text(feedback)
            
            # Determinar estilo do feedback
            if reaction == 'like':
                feedback_class = "message-feedback-positive"
                emoji_fb = "✅"
                label = "FEEDBACK POSITIVO"
            else:
                feedback_class = "message-feedback-negative"
                emoji_fb = "❌"
                label = "FEEDBACK NEGATIVO"
            
            # Adicionar contador se houver múltiplos feedbacks
            counter_text = ""
            if len(feedbacks) > 1:
                counter_text = f" #{idx}"
            
            # Obter método de identificação
            metodo = feedback.get('_metodo_identificacao', 'ID')
            if metodo == 'ID':
                metodo_badge = '<span style="background-color: #1976D2; color: white; padding: 2px 6px; border-radius: 4px; font-size: 0.75em; margin-left: 8px;">🔗 ID</span>'
            elif metodo == 'ID_CROSS':
                metodo_badge = '<span style="background-color: #9C27B0; color: white; padding: 2px 6px; border-radius: 4px; font-size: 0.75em; margin-left: 8px;">🔗 ID (outra linha)</span>'
            else:
                metodo_badge = '<span style="background-color: #FF9800; color: white; padding: 2px 6px; border-radius: 4px; font-size: 0.75em; margin-left: 8px;">⏱️ TEMPO</span>'
            
            # Renderizar feedback como uma mensagem separada
            feedback_html = f"""
            <div class="{feedback_class}">
                <div class="header">{emoji_fb} {label}{counter_text} {metodo_badge}</div>
                <div class="text">{feedback_text}</div>
            </div>
            """
            
            st.markdown(feedback_html, unsafe_allow_html=True)


def _break_long_tokens(text, max_len=45):
    """
    Insere pontos de quebra dentro de tokens muito longos sem espaços
    (ex: URLs), permitindo que o motor de PDF (xhtml2pdf) quebre a linha.
    Sem isso, textos como links longos vazam para fora da caixa da mensagem
    (o motor de PDF usado não trata corretamente CSS word-break/wbr/zero-width
    space para forçar a quebra de uma palavra única muito longa).
    """
    def _break_token(match):
        token = match.group(0)
        if len(token) <= max_len:
            return token
        return ' '.join(token[i:i + max_len] for i in range(0, len(token), max_len))

    return re.sub(r'\S+', _break_token, text)


def render_markdown_for_pdf(text):
    """
    Converte texto (possivelmente em Markdown, como as respostas do bot)
    em HTML, para que negrito/itálico/links/listas fiquem visualmente
    equivalentes ao que é exibido em tela pelo st.markdown.
    """
    if not text:
        return ""
    try:
        text = _break_long_tokens(str(text))
        return markdown_lib.markdown(text, extensions=['nl2br'])
    except Exception:
        return str(text)


def build_message_html_for_pdf(msg):
    """
    Constrói o HTML de uma mensagem (e seus feedbacks) para o PDF exportado.
    Segue a mesma estrutura visual da tela, mas usando apenas CSS compatível
    com o motor de geração de PDF (xhtml2pdf) - por exemplo, uma tabela no
    lugar de flexbox para alinhar o horário à direita do cabeçalho.
    """
    msg_class = "message-user" if msg['is_user'] else "message-bot"
    emoji = "👤" if msg['is_user'] else "🤖"
    role = "USUÁRIO" if msg['is_user'] else "BOT"

    aad_id = msg.get('aadObjectId', '')
    role_display = f"{role} <span style='font-size:8pt; color:#888;'>({aad_id})</span>" if aad_id else role

    header_table = f"""
    <table class="msg-header-table"><tr>
        <td class="msg-header-left">{emoji} {role_display}</td>
        <td class="msg-header-right">{msg['time']}</td>
    </tr></table>
    """

    parts = [f"""
    <div class="{msg_class}">
        <div class="msg-header">{header_table}</div>
        <div class="msg-text">{render_markdown_for_pdf(msg['text'])}</div>
    </div>
    """]

    feedbacks = msg.get('feedbacks', [])
    if feedbacks:
        for idx, feedback in enumerate(feedbacks, 1):
            reaction = feedback.get('reaction', '')
            feedback_text = extract_feedback_text(feedback)

            if reaction == 'like':
                feedback_class = "message-feedback-positive"
                emoji_fb = "✅"
                label = "FEEDBACK POSITIVO"
            else:
                feedback_class = "message-feedback-negative"
                emoji_fb = "❌"
                label = "FEEDBACK NEGATIVO"

            counter_text = f" #{idx}" if len(feedbacks) > 1 else ""

            metodo = feedback.get('_metodo_identificacao', 'ID')
            if metodo == 'ID':
                badge = '<span class="badge" style="background-color:#1976D2;">ID</span>'
            elif metodo == 'ID_CROSS':
                badge = '<span class="badge" style="background-color:#9C27B0;">ID (outra linha)</span>'
            else:
                badge = '<span class="badge" style="background-color:#FF9800;">TEMPO</span>'

            parts.append(f"""
            <div class="{feedback_class}">
                <div class="msg-header">{emoji_fb} {label}{counter_text}{badge}</div>
                <div class="msg-text">{render_markdown_for_pdf(feedback_text)}</div>
            </div>
            """)

    return "".join(parts)


def build_conversation_section_html(row_idx, messages, conversation_date=None, add_page_break=True):
    """
    Constrói a seção HTML de uma conversa para o PDF exportado.

    O identificador da conversa (e, portanto, dos feedbacks nela contidos)
    é o próprio número da linha (índice 0-based do arquivo original),
    exibido como "LINHA #{row_idx}" - igual ao usado na visualização em tela.
    """
    header_html = f'<div class="row-number"> #{row_idx}</div>'

    meta_parts = []
    if conversation_date:
        meta_parts.append(f"<b>Data da conversa:</b> {conversation_date}")
    if messages:
        meta_parts.append(f"Total de mensagens: {len(messages)}")

    meta_html = f'<div class="conversation-meta">{" &nbsp;|&nbsp; ".join(meta_parts)}</div>' if meta_parts else ""

    if messages:
        messages_html = "".join(build_message_html_for_pdf(msg) for msg in messages)
    else:
        messages_html = '<div class="no-messages">Nenhuma mensagem encontrada nesta conversa.</div>'

    section_class = "conversation-section page-break" if add_page_break else "conversation-section"
    return f'<div class="{section_class}">{header_html}{meta_html}{messages_html}</div>'


def generate_conversations_pdf(df_export, parsed_json_cache, all_feedbacks_map, context_info=None):
    """
    Gera um PDF visualmente semelhante à visualização de conversa em tela,
    contendo todas as linhas presentes em df_export (já filtradas pelos
    controles da barra lateral).

    IMPORTANTE: o ID usado para identificar cada conversa (e os feedbacks
    nela contidos) no PDF é o próprio número da linha (0-based) do arquivo
    original - o mesmo índice usado na visualização em tela ("LINHA #{idx}").

    A contagem de feedbacks impressa na capa é obtida da MESMA travessia usada
    para renderizar as conversas, e por isso é sempre idêntica à exibida na
    barra lateral (que cobre exatamente este mesmo conjunto de conversas).

    Retorna: (pdf_bytes, error_message). Em caso de sucesso, error_message é None.
    """
    if debug: print(f"Gerando PDF para {len(df_export)} conversa(s)...")

    context_info = context_info or {}
    generated_at = datetime.now().strftime('%d/%m/%Y')

    row_indices = list(df_export.index)
    dates_by_row = context_info.get('datas_por_linha') or {}

    sections = []
    total_positive = 0
    total_negative = 0
    total_other = 0

    for i, row_idx in enumerate(row_indices):
        parsed_data = parsed_json_cache.get(row_idx)
        messages = extract_chat_content(parsed_data, all_feedbacks_map)

        for msg in messages:
            for feedback in msg.get('feedbacks', []):
                reaction = feedback.get('reaction', '')
                if reaction == 'like':
                    total_positive += 1
                elif reaction == 'dislike':
                    total_negative += 1
                else:
                    total_other += 1

        is_last = (i == len(row_indices) - 1)
        sections.append(build_conversation_section_html(
            row_idx,
            messages,
            conversation_date=dates_by_row.get(row_idx),
            add_page_break=not is_last
        ))

    context_lines = [f"<b>Gerado em:</b> {generated_at}"]
    if context_info.get('ambiente'):
        context_lines.append(f"<b>Ambiente:</b> {context_info['ambiente']}")
    if context_info.get('agente'):
        context_lines.append(f"<b>Agente:</b> {context_info['agente']}")
    if context_info.get('data_inicial'):
        context_lines.append(f"<b>Conversas desde:</b> {context_info['data_inicial']}")
    if context_info.get('apenas_com_feedback'):
        context_lines.append("<b>Filtro:</b> Apenas conversas com feedback")
    context_lines.append("<b>Conversas de teste (modo design):</b> excluídas")
    context_lines.append(f"<b>Total de conversas exportadas:</b> {len(df_export)}")

    total_feedbacks = total_positive + total_negative + total_other
    context_lines.append(f"<b>Feedbacks positivos:</b> {total_positive}")
    context_lines.append(f"<b>Feedbacks negativos:</b> {total_negative}")
    if total_other:
        context_lines.append(f"<b>Feedbacks sem reação identificada:</b> {total_other}")
    context_lines.append(f"<b>Total de feedbacks:</b> {total_feedbacks}")

    cover_html = f"""
    <div class="conversation-section page-break">
        <h1>Exportação de Transcrições de Chat</h1>
        <p>{'<br/>'.join(context_lines)}</p>
    </div>
    """

    full_html = f"""
    <html>
    <head>{PDF_CSS}</head>
    <body>
        {cover_html}
        {''.join(sections)}
    </body>
    </html>
    """

    try:
        buffer = BytesIO()
        result = pisa.CreatePDF(src=full_html, dest=buffer)
        if result.err:
            return None, "Erro ao converter HTML em PDF."
        return buffer.getvalue(), None
    except Exception as e:
        return None, str(e)


def format_datetime(datetime_str):
    """
    Formata datetime para AAAA/MM/DD
    """
    try:
        dt = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
        return dt.strftime('%Y/%m/%d')
    except:
        return datetime_str


def format_conversation_datetime(datetime_str):
    """
    Formata a data/hora de início da conversa para DD/MM/AAAA HH:MM (exibida no PDF).

    Trata os dois formatos presentes nos CSVs exportados do Dataverse:
    '2026-06-24T12:55:42Z' e '2026-05-27 13:13:48.0000000'.
    """
    if datetime_str is None or (isinstance(datetime_str, float) and pd.isna(datetime_str)):
        return ""
    try:
        dt = pd.to_datetime(datetime_str, errors='coerce')
        if pd.isna(dt):
            return str(datetime_str)
        return dt.strftime('%d/%m/%Y %H:%M')
    except Exception:
        return str(datetime_str)


# ============================================================================
# APLICAÇÃO PRINCIPAL
# ============================================================================

st.title("📊 Visualizador de Transcrições de Chat")

CSV_FILES = {
    "MRS-IA-HML": "conversationtranscripts_hml.csv",
    "MRS-IA-PROD": "conversationtranscripts_prod.csv",
    "MRS-IA-SANDBOX": "conversationtranscripts_sandbox.csv",
}

selected_env = st.sidebar.selectbox("Ambiente", list(CSV_FILES.keys()))
csv_path = CSV_FILES[selected_env]

# Carregar CSV
try:
    # Carregar dados com cache (executa só uma vez)
    df = load_csv_data(csv_path)
    
    # Construir mapa global de IDs (com cache)
    with st.spinner("Construindo índice de mensagens..."):
        global_id_map = build_global_id_map(tuple(df['content'].tolist()))
    
    # Identificar conversas de teste (modo design) - com cache
    content_tuple = tuple(df['content'].tolist())
    design_flags = compute_design_mode_flags(content_tuple)

    # Carregar TODOS os feedbacks do CSV (com cache), ignorando conversas de teste
    with st.spinner("Carregando feedbacks..."):
        all_feedbacks_global, orphan_feedbacks = load_all_feedbacks(
            content_tuple,
            global_id_map,
            design_flags
        )
    
    # Parsear todos os JSONs (com cache) para visualização rápida
    with st.spinner("Preparando dados..."):
        parsed_json_cache = parse_all_json_content(content_tuple)
    
    # Adicionar coluna de feedback (CACHEADO)
    df['feedback'] = compute_feedback_column(content_tuple, all_feedbacks_global)
    
    # Adicionar coluna de contagem de feedbacks (CACHEADO)
    df['feedback_count'] = compute_feedback_count_column(content_tuple, all_feedbacks_global)
    
    # Formatar conversationstarttime se existir
    if 'conversationstarttime' in df.columns:
        df['conversationstarttime_formatted'] = df['conversationstarttime'].apply(format_datetime)
        # Criar coluna de data (sem hora) para filtro
        df['conversation_date'] = pd.to_datetime(df['conversationstarttime'], errors='coerce').dt.date

    # Remover conversas de teste (modo design) de TODAS as visões: lista,
    # estatísticas e exportação em PDF. O índice original das linhas é
    # preservado, pois é a chave usada em parsed_json_cache.
    df['is_design_mode'] = list(design_flags)
    total_design_mode = int(df['is_design_mode'].sum())
    df = df[~df['is_design_mode']]
    
    # ========================================================================
    # SIDEBAR - CONTROLES
    # ========================================================================
    
    st.sidebar.header("⚙️ Configurações")
    
    # Seleção de colunas visíveis
    st.sidebar.subheader("Colunas Visíveis")
    all_columns = [col for col in df.columns
                   if col not in ('conversationstarttime', 'is_design_mode')]
    
    # Colunas padrão visíveis
    default_visible = ['feedback', 'feedback_count', 'content']
    if 'conversationstarttime_formatted' in df.columns:
        default_visible.insert(2, 'conversationstarttime_formatted')
    
    visible_columns = st.sidebar.multiselect(
        "Selecione as colunas:",
        options=all_columns,
        default=[col for col in default_visible if col in all_columns]
    )
    
    # Filtro de feedback
    st.sidebar.subheader("Filtros")
    only_with_feedback = st.sidebar.checkbox("Mostrar apenas conversas com feedback")
    
    # Filtro de data
    if 'conversation_date' in df.columns:
        min_date = df['conversation_date'].min()
        max_date = df['conversation_date'].max()
        
        if pd.notna(min_date) and pd.notna(max_date):
            selected_date = st.sidebar.date_input(
                "Data inicial:",
                value=min_date,
                min_value=min_date,
                max_value=max_date,
                help="Mostra conversas desta data em diante"
            )
    
    # Filtro de Agente
    agent_column = '_bot_conversationtranscriptid_value@OData.Community.Display.V1.FormattedValue'
    selected_agent = None
    if agent_column in df.columns:
        # Obter valores únicos da coluna de agentes (ignorando valores nulos)
        unique_agents = df[agent_column].dropna().unique().tolist()
        unique_agents.sort()
        # Adicionar opção "<All>" no início
        agent_options = ['<All>'] + unique_agents
        
        selected_agent = st.sidebar.selectbox(
            "Agente:",
            options=agent_options,
            index=0,
            help="Filtra conversas por agente específico"
        )
    
    # ========================================================================
    # CONJUNTO FILTRADO ÚNICO
    # Lista, estatísticas da barra lateral e PDF usam EXATAMENTE este conjunto,
    # para que as contagens exibidas e exportadas nunca divirjam.
    # ========================================================================
    df_filtered = df.copy()

    if only_with_feedback:
        df_filtered = df_filtered[df_filtered['feedback'] != '']

    if 'conversation_date' in df.columns and pd.notna(min_date) and pd.notna(max_date):
        df_filtered = df_filtered[df_filtered['conversation_date'] >= selected_date]

    if selected_agent and selected_agent != '<All>' and agent_column in df.columns:
        df_filtered = df_filtered[df_filtered[agent_column] == selected_agent]

    # Painel de estatísticas (CACHEADO)
    st.sidebar.subheader("📈 Estatísticas")

    total_positive, total_negative, total_other = compute_statistics(
        tuple(df_filtered.index),
        parsed_json_cache,
        all_feedbacks_global,
        csv_path
    )

    total_feedbacks = total_positive + total_negative + total_other
    total_conversations = len(df_filtered)
    
    MESES_PT = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun',
                'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez']
    label_date = f"{selected_date.day} {MESES_PT[selected_date.month - 1]}"
    st.sidebar.metric(f"Total de Conversas (desde {label_date})", total_conversations)
    st.sidebar.metric("✅ Feedbacks Positivos", total_positive)
    st.sidebar.metric("❌ Feedbacks Negativos", total_negative)
    if total_other:
        st.sidebar.metric("❔ Feedbacks sem reação", total_other)
    st.sidebar.metric("📈 Total de Feedbacks", total_feedbacks)
    
    if total_positive + total_negative > 0:
        percentual_positivo = (total_positive / (total_positive + total_negative)) * 100
        st.sidebar.metric("Percentual Positivo", f"{percentual_positivo:.1f}%")

    if total_design_mode:
        st.sidebar.caption(
            f"🧪 {total_design_mode} conversa(s) de teste (modo design) excluídas "
            "das contagens e da exportação."
        )
    if orphan_feedbacks:
        st.sidebar.caption(
            f"⚠️ {orphan_feedbacks} feedback(s) não puderam ser associados a nenhuma "
            "mensagem do CSV (conversa de origem não exportada) e ficam fora do total."
        )
    
    # ========================================================================
    # LAYOUT PRINCIPAL - 2 COLUNAS
    # ========================================================================
    
    col_left, col_right = st.columns([1, 1])
    
    with col_left:
        st.header("📋 Lista de Conversas")
        
        # Mesmo conjunto usado nas estatísticas da barra lateral e no PDF
        df_display = df_filtered.copy()
        
        # Garantir que 'feedback' esteja nas colunas visíveis
        if 'feedback' not in visible_columns and len(visible_columns) > 0:
            visible_columns = ['feedback'] + visible_columns
        
        # Mostrar dataframe
        if len(visible_columns) > 0:
            # Adicionar coluna de índice original para referência
            df_display['#'] = df_display.index
            display_cols = ['#'] + visible_columns
            
            st.dataframe(
                df_display[display_cols],
                width='stretch',
                hide_index=True
            )
            
            # ================================================================
            # EXPORTAÇÃO PARA PDF - exporta a seleção/filtragem atual
            # ================================================================
            st.markdown("---")
            col_export_btn, col_export_download = st.columns([1, 1])
            
            with col_export_btn:
                export_clicked = st.button(
                    "📄 Exportar conversas para PDF",
                    help="Exporta todas as conversas filtradas (visíveis na tabela acima) para um PDF, no mesmo formato visual usado ao visualizar uma conversa."
                )
            
            if export_clicked:
                if len(df_display) == 0:
                    st.warning("Nenhuma conversa para exportar com os filtros atuais.")
                else:
                    with st.spinner(f"Gerando PDF com {len(df_display)} conversa(s)..."):
                        pdf_bytes, pdf_error = generate_conversations_pdf(
                            df_display,
                            parsed_json_cache,
                            all_feedbacks_global,
                            context_info={
                                'ambiente': selected_env,
                                'agente': selected_agent if selected_agent and selected_agent != '<All>' else 'Todos',
                                'data_inicial': locals().get('selected_date').strftime('%d/%m/%Y') if locals().get('selected_date') else None,
                                'apenas_com_feedback': only_with_feedback,
                                'datas_por_linha': {
                                    idx: format_conversation_datetime(valor)
                                    for idx, valor in df_display['conversationstarttime'].items()
                                } if 'conversationstarttime' in df_display.columns else {},
                            }
                        )
                    
                    if pdf_error:
                        st.error(f"❌ Erro ao gerar PDF: {pdf_error}")
                    else:
                        st.session_state['pdf_export_bytes'] = pdf_bytes
                        st.session_state['pdf_export_filename'] = (
                            f"conversas_{selected_env}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                        )
                        st.success(f"✅ PDF gerado com {len(df_display)} conversa(s)!")
            
            if 'pdf_export_bytes' in st.session_state:
                with col_export_download:
                    st.download_button(
                        label="⬇️ Baixar PDF",
                        data=st.session_state['pdf_export_bytes'],
                        file_name=st.session_state.get('pdf_export_filename', 'conversas.pdf'),
                        mime="application/pdf"
                    )
            
            # Seletor de linha
            st.subheader("Selecione uma conversa para visualizar")
            
            col_input, col_spacer = st.columns([1, 2])
            
            with col_input:
                # O '#' exibido é o índice original do CSV, que não é contíguo
                # após a remoção das conversas de teste - por isso o limite é o
                # maior índice existente, e não a quantidade de linhas.
                selected_index = st.number_input(
                    "Digite o número da linha (#):",
                    min_value=0,
                    max_value=int(df.index.max()) if len(df) else 0,
                    value=0,
                    step=1
                )
            
            if st.button("🔍 Visualizar Conversa", type="primary"):
                st.session_state['selected_row'] = selected_index
        else:
            st.warning("Selecione pelo menos uma coluna para visualizar.")
    
    with col_right:
        st.header("💬 Visualização do Chat")
        
        if 'selected_row' in st.session_state:
            row_idx = st.session_state['selected_row']
            
            # Mostrar número da linha
            st.markdown(
                f'<div class="row-number">📍 LINHA #{row_idx}</div>',
                unsafe_allow_html=True
            )
            
            # Extrair mensagens usando o cache de JSON parseado
            parsed_data = parsed_json_cache.get(row_idx)
            messages = extract_chat_content(parsed_data, all_feedbacks_global)
            
            if messages:
                st.info(f"**Total de mensagens:** {len(messages)}")
                
                # Renderizar cada mensagem
                for msg in messages:
                    render_chat_message(msg)
            else:
                st.warning("Nenhuma mensagem encontrada nesta conversa.")
        else:
            st.info("👈 Selecione uma conversa na lista à esquerda e clique em 'Visualizar Conversa'")

except FileNotFoundError:
    st.error(f"❌ Arquivo '{csv_path}' não encontrado!")
    st.info("Execute o script de download: python data_extract/download_conversation_transcripts.py")
except Exception as e:
    st.error(f"❌ Erro ao carregar dados: {str(e)}")
    st.exception(e)
