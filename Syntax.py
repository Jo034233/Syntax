import streamlit as st
import hashlib
import json
import datetime
import os
from groq import Groq
from streamlit_cookies_controller import CookieController

# ==============================================================================
# 1. CONFIGURATION DE LA PAGE & COOKIES
# ==============================================================================
st.set_page_config(page_title="Syntax IA", page_icon="⚡", layout="wide")

cookies = CookieController()

# ==============================================================================
# 2. GESTION DE LA BASE DE DONNÉES CLOUD (CONNEXION STREAMLIT)
# ==============================================================================
try:
    conn = st.connection("postgresql", type="sql")
except Exception:
    conn = None

def init_db():
    if conn is None:
        return
    with conn.session as session:
        session.execute("""
            CREATE TABLE IF NOT EXISTS syntax_users (
                email TEXT PRIMARY KEY,
                password_hash TEXT,
                username TEXT
            )
        """)
        session.execute("""
            CREATE TABLE IF NOT EXISTS syntax_conversations (
                id TEXT,
                user_email TEXT,
                title TEXT,
                messages_json TEXT,
                PRIMARY KEY (id, user_email)
            )
        """)
        session.commit()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def register_user(email, password, username):
    init_db()
    if conn is None:
        return False, "Base de données non connectée."
    
    with conn.session as session:
        result = session.execute("SELECT email FROM syntax_users WHERE LOWER(email) = :email", {"email": email.lower()}).fetchone()
        if result:
            return False, "Cet e-mail est déjà utilisé."
        
        session.execute("""
            INSERT INTO syntax_users (email, password_hash, username) 
            VALUES (:email, :password_hash, :username)
        """, {"email": email.lower(), "password_hash": hash_password(password), "username": username.strip()})
        session.commit()
    return True, "Utilisateur créé avec succès !"

def check_user(email, password):
    init_db()
    if conn is None:
        return None
    with conn.session as session:
        result = session.execute("""
            SELECT username FROM syntax_users 
            WHERE LOWER(email) = :email AND password_hash = :password_hash
        """, {"email": email.lower(), "password_hash": hash_password(password)}).fetchone()
        return result[0] if result else None

def save_conversation_to_db(user_email, chat_id, title, messages):
    if conn is None:
        return
    clean_messages = [{"role": str(m["role"]), "content": str(m["content"])} for m in messages if isinstance(m, dict) and "role" in m and "content" in m]
    messages_json = json.dumps(clean_messages)
    
    with conn.session as session:
        session.execute("""
            INSERT INTO syntax_conversations (id, user_email, title, messages_json)
            VALUES (:id, :user_email, :title, :messages_json)
            ON CONFLICT(id, user_email) DO UPDATE SET
                title = EXCLUDED.title,
                messages_json = EXCLUDED.messages_json
        """, {"id": chat_id, "user_email": user_email.lower(), "title": title, "messages_json": messages_json})
        session.commit()

def delete_conversation_from_db(user_email, chat_id):
    if conn is None:
        return
    with conn.session as session:
        session.execute("""
            DELETE FROM syntax_conversations 
            WHERE id = :id AND LOWER(user_email) = :user_email
        """, {"id": chat_id, "user_email": user_email.lower()})
        session.commit()

def load_conversations_from_db(user_email):
    if conn is None:
        return {}
    with conn.session as session:
        rows = session.execute("""
            SELECT id, title, messages_json FROM syntax_conversations 
            WHERE LOWER(user_email) = :user_email
        """, {"user_email": user_email.lower()}).fetchall()
        
    conversations = {}
    for row in rows:
        try: conversations[row[0]] = {"title": row[1], "messages": json.loads(row[2])}
        except: pass
    return conversations

init_db()

# ==============================================================================
# 3. SYSTÈME D'AUTHENTIFICATION (PAR COOKIES)
# ==============================================================================
if "connected" not in st.session_state:
    st.session_state.connected = False
if "user_name" not in st.session_state:
    st.session_state.user_name = "Utilisateur"
if "user_email" not in st.session_state:
    st.session_state.user_email = ""

if not st.session_state.connected:
    saved_email = cookies.get("syntax_user_email")
    if saved_email and conn:
        with conn.session as session:
            user_exists = session.execute("SELECT username FROM syntax_users WHERE LOWER(email) = :email", {"email": saved_email.lower()}).fetchone()
        if user_exists:
            st.session_state.connected = True
            st.session_state.user_email = saved_email
            st.session_state.user_name = user_exists[0]
            st.rerun()

if not st.session_state.connected:
    st.markdown("""
        <style>
        .stApp { background-color: #0b0b0f !important; color: white !important; }
        .login-box { max-width: 450px; margin: 10vh auto 0 auto; padding: 35px; background-color: #16161f; border: 1px solid rgba(128, 128, 128, 0.2); border-radius: 14px; font-family: sans-serif; box-shadow: 0 10px 25px rgba(0,0,0,0.3); }
        .stTabs [data-baseweb="tab-list"] { justify-content: center; }
        </style>
    """, unsafe_allow_html=True)
    
    st.markdown('<div class="login-box">', unsafe_allow_html=True)
    st.title("🤖 Bienvenue sur Syntax")
    
    if conn is None:
        st.warning("⚠️ L'application n'est pas encore connectée à sa base de données Cloud. Veuillez configurer les secrets SQL dans Streamlit Cloud.")
    
    tab_login, tab_register = st.tabs(["🔒 Se connecter", "📝 Créer un compte"])
    
    with tab_login:
        with st.form("login_form"):
            email_log = st.text_input("Adresse e-mail", key="log_email", placeholder="nom@exemple.com")
            pass_log = st.text_input("Mot de passe", type="password", key="log_pass", placeholder="••••••••")
            submit_log = st.form_submit_button("🔑 Connexion")
            
            if submit_log:
                db_username = check_user(email_log, pass_log)
                if db_username:
                    st.session_state.connected = True
                    st.session_state.user_email = email_log.lower()
                    st.session_state.user_name = db_username
                    cookies.set("syntax_user_email", email_log.lower(), expires=datetime.datetime.now() + datetime.timedelta(days=30))
                    st.session_state.conversations = load_conversations_from_db(email_log.lower())
                    st.session_state.current_chat_id = list(st.session_state.conversations.keys())[0] if st.session_state.conversations else None
                    st.rerun()
                else:
                    st.error("E-mail ou mot de passe incorrect.")
                    
    with tab_register:
        with st.form("register_form"):
            email_reg = st.text_input("Adresse e-mail", key="reg_email", placeholder="nom@exemple.com")
            pass_reg = st.text_input("Mot de passe", type="password", key="reg_pass", placeholder="Minimum 6 caractères")
            username_reg = st.text_input("Comment dois-je vous appeler ?", key="reg_username", placeholder="Votre prénom ou pseudo")
            submit_reg = st.form_submit_button("✨ Créer mon compte")
            
            if submit_reg:
                if len(pass_reg) < 6: st.error("Le mot de passe doit contenir au moins 6 caractères.")
                elif "@" not in email_reg or "." not in email_reg: st.error("Veuillez entrer une adresse e-mail valide.")
                elif not username_reg.strip(): st.error("Veuillez choisir comment je dois vous appeler.")
                else:
                    success, msg = register_user(email_reg, pass_reg, username_reg)
                    if success:
                        st.session_state.connected = True
                        st.session_state.user_email = email_reg.lower()
                        st.session_state.user_name = username_reg.strip()
                        cookies.set("syntax_user_email", email_reg.lower(), expires=datetime.datetime.now() + datetime.timedelta(days=30))
                        st.session_state.conversations = {}
                        st.session_state.current_chat_id = None
                        st.rerun()
                    else: st.error(msg)
                        
    st.markdown('</div>', unsafe_allow_html=True)
    st.stop()

# ==============================================================================
# 4. CHARGEMENT DE L'HISTORIQUE
# ==============================================================================
if "conversations" not in st.session_state or not st.session_state.conversations:
    saved_chats = load_conversations_from_db(st.session_state.user_email)
    st.session_state.conversations = saved_chats if saved_chats else {}
    if saved_chats and ("current_chat_id" not in st.session_state or st.session_state.current_chat_id is None):
        st.session_state.current_chat_id = list(saved_chats.keys())[0]
    elif "current_chat_id" not in st.session_state:
        st.session_state.current_chat_id = None

# ==============================================================================
# 5. STYLES DESIGN INTERFACE (Amélioration UI fluide & responsive)
# ==============================================================================
st.markdown("""
    <style>
    .stApp, .stAppHeader { background-color: var(--background-color) !important; color: var(--text-color) !important; }
    div[data-testid="stChatInputContainer"] { background-color: var(--background-color) !important; border: none !important; padding-bottom: 25px; }
    div[data-testid="stChatInputContainer"] > div { background-color: var(--secondary-background-color) !important; border: 1px solid rgba(128, 128, 128, 0.2) !important; border-radius: 28px !important; }
    div[data-testid="stChatInputContainer"] textarea { color: var(--text-color) !important; background-color: transparent !important; }
    section[data-testid="stSidebar"] { background-color: var(--secondary-background-color) !important; border-right: 1px solid rgba(128, 128, 128, 0.1); }
    .stButton>button { background-color: #6d28d9 !important; color: white !important; border-radius: 20px !important; border: none !important; font-weight: 600 !important; width: 100%; transition: 0.2s ease; }
    .stButton>button:hover { background-color: #5b21b6 !important; }
    div[data-testid="stSidebarUserContent"] div.stHorizontalBlock { align-items: center !important; gap: 0px !important; margin-bottom: 4px !important; background-color: transparent; }
    div.sidebar-chat-btn > button { background-color: transparent !important; color: var(--text-color) !important; opacity: 0.8; border: none !important; text-align: left !important; padding: 8px 10px !important; width: 100% !important; border-radius: 8px !important; font-size: 14px !important; text-overflow: ellipsis; white-space: nowrap; overflow: hidden; }
    div.sidebar-chat-btn > button:hover { background-color: rgba(109, 40, 217, 0.1) !important; color: #a78bfa !important; opacity: 1 !important; }
    div.sidebar-del-btn > button { background-color: transparent !important; color: var(--text-color) !important; opacity: 0.2 !important; border: none !important; padding: 8px 6px !important; font-size: 13px !important; width: 100% !important; }
    div.sidebar-del-btn > button:hover { color: #ef4444 !important; opacity: 1 !important; background-color: rgba(239, 68, 68, 0.15) !important; border-radius: 6px; }
    .syntax-logo { width: 50px; height: 50px; background: linear-gradient(135deg, #8b5cf6, #d946ef); border-radius: 14px; display: flex; align-items: center; justify-content: center; font-family: 'Courier New', monospace; font-weight: bold; font-size: 24px; color: white; box-shadow: 0 0 20px rgba(139, 92, 246, 0.3); margin: 0 auto 15px auto; }
    .welcome-text { text-align: center; font-size: 32px; font-weight: 500; color: var(--text-color); margin-top: 15vh; opacity: 0.9; }
    .file-box { background: rgba(255,255,255,0.03); border: 1px dashed rgba(128,128,128,0.3); padding: 10px; border-radius: 8px; margin-bottom: 10px;}
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# 6. INITIALISATION DE L'IA GROQ & PROMPT SYSTÈME OPTIMISÉ (Compétences accrues)
# ==============================================================================
if "GROQ_API_KEY" in st.secrets: 
    client = Groq(api_key=st.secrets["GROQ_API_KEY"])
else: 
    client = None

ACTIVE_MODEL = "llama-3.1-8b-instant"

# Le prompt système intègre désormais l'ensemble de tes requêtes linguistiques, de connaissances et d'analyses
SYSTEM_INSTRUCTION = (
    "Tu t'appelles Syntax. Tu es un système d'intelligence artificielle hautement perfectionné. "
    "COMPÉTENCES LINGUISTIQUES : Ta communication doit être claire, fluide, naturelle et d'une précision grammaticale irréprochable. "
    "CHAMPS DE CONNAISSANCES EXTENSIFS : Tu disposes d'expertises poussées dans les domaines scientifiques, technologiques, de la santé, informatiques et d'ingénierie. "
    "RAISONNEMENT ET RÉSOLUTION DE PROBLÈMES : Traite les requêtes de manière structurée, logique, efficace et efficiente. "
    "RÈGLE D'ANALYSE DE FICHIER : Si l'utilisateur te fournit du code, des données ou le contenu d'un fichier, effectue une analyse technique directe, objective et factuelle du contenu fourni. "
    "Évite les introductions superflues, les conclusions redondantes ou les bavardages, concentre-toi sur l'exactitude brute de l'analyse."
)

# ==============================================================================
# 7. PANNEAU LATÉRAL (SIDEBAR) & ZONE DE TÉLÉCHARGEMENT DE FICHIERS
# ==============================================================================
with st.sidebar:
    st.write("")
    st.markdown('<div class="syntax-logo">&lt;/&gt;</div>', unsafe_allow_html=True)
    st.markdown("<h3 style='text-align: center;'>Syntax</h3>", unsafe_allow_html=True)
    st.caption(f"👋 {st.session_state.user_name}")
    
    if st.button("➕ Nouvelle discussion", key="global_new_chat"):
        new_id = f"chat_{int(datetime.datetime.now().timestamp())}"
        st.session_state.conversations[new_id] = {"title": "Nouvelle discussion", "messages": []}
        st.session_state.current_chat_id = new_id
        save_conversation_to_db(st.session_state.user_email, new_id, "Nouvelle discussion", [])
        st.rerun()

    st.markdown("---")
    
    # Module UI d'analyse de fichiers (Demande : Analyse sans génération)
    st.markdown("📁 **Analyseur de fichiers**")
    uploaded_file = st.file_uploader("Dépose un fichier à analyser (TXT, PY, JS, JSON...)", type=["txt", "py", "js", "json", "md", "csv"], label_visibility="collapsed")
    
    st.markdown("---")
    total_chats = len(st.session_state.conversations)
    
    for chat_id, chat_data in list(st.session_state.conversations.items()):
        is_active = chat_id == st.session_state.current_chat_id
        prefix = "✨ " if is_active else "💬 "
        
        if total_chats > 1:
            c_link, c_del = st.columns([0.86, 0.14])
            with c_link:
                st.markdown('<div class="sidebar-chat-btn">', unsafe_allow_html=True)
                if st.button(f"{prefix}{chat_data['title']}", key=f"nav_{chat_id}"):
                    st.session_state.current_chat_id = chat_id
                    st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)
            with c_del:
                st.markdown('<div class="sidebar-del-btn">', unsafe_allow_html=True)
                if st.button("✕", key=f"del_{chat_id}"):
                    delete_conversation_from_db(st.session_state.user_email, chat_id)
                    del st.session_state.conversations[chat_id]
                    if st.session_state.current_chat_id == chat_id:
                        st.session_state.current_chat_id = list(st.session_state.conversations.keys())[0] if st.session_state.conversations else None
                    st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="sidebar-chat-btn">', unsafe_allow_html=True)
            if st.button(f"{prefix}{chat_data['title']}", key=f"nav_{chat_id}"):
                st.session_state.current_chat_id = chat_id
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
        
    st.container(height=100, border=False) 
    st.markdown("---")
    
    if st.button("🚪 Déconnexion", key="global_logout"):
        cookies.remove("syntax_user_email")
        for key in list(st.session_state.keys()): del st.session_state[key]
        st.rerun()

# ==============================================================================
# 8. ZONE DE CHAT & TRAITEMENT DES FLUX
# ==============================================================================
if st.session_state.current_chat_id is None or st.session_state.current_chat_id not in st.session_state.conversations:
    st.markdown(f'<div class="welcome-text">Que puis-je analyser ou résoudre pour vous aujourd\'hui, {st.session_state.user_name} ?</div>', unsafe_allow_html=True)
    active_messages = []
else:
    active_chat = st.session_state.conversations[st.session_state.current_chat_id]
    active_messages = active_chat["messages"]
    if len(active_messages) == 0:
        st.markdown(f'<div class="welcome-text">Que puis-je analyser ou résoudre pour vous aujourd\'hui, {st.session_state.user_name} ?</div>', unsafe_allow_html=True)
    else:
        for message in active_messages:
            with st.chat_message(message["role"]): st.markdown(message["content"])

# Gestion de l'injection d'un fichier dans le chat (Mode analyse pure)
if uploaded_file is not None and "last_uploaded" not in st.session_state:
    try:
        file_content = uploaded_file.read().decode("utf-8")
        st.session_state.last_uploaded = uploaded_file.name
        
        prompt_analyse = f"ANALYSE DE FICHIER DIRECTE (SANS GÉNÉRATION CRÉATIVE) :\nNom du fichier : {uploaded_file.name}\nContenu à analyser :\n```\n{file_content}\n```"
        
        if st.session_state.current_chat_id is None:
            new_id = f"chat_{int(datetime.datetime.now().timestamp())}"
            st.session_state.conversations[new_id] = {"title": f"📊 {uploaded_file.name[:12]}", "messages": []}
            st.session_state.current_chat_id = new_id
            active_chat = st.session_state.conversations[new_id]
            active_messages = active_chat["messages"]
            
        active_messages.append({"role": "user", "content": prompt_analyse})
        save_conversation_to_db(st.session_state.user_email, st.session_state.current_chat_id, active_chat["title"], active_messages)
        st.rerun()
    except Exception as e:
        st.error(f"Impossible de lire le fichier : {e}")

# Nettoyage de l'état du fichier si retiré
if uploaded_file is None and "last_uploaded" in st.session_state:
    del st.session_state.last_uploaded

# Chat classique input
if prompt := st.chat_input("Pose ta question à Syntax..."):
    if client is None:
        st.error("Erreur : Clé API Groq introuvable.")
        st.stop()

    if st.session_state.current_chat_id is None:
        new_id = f"chat_{int(datetime.datetime.now().timestamp())}"
        st.session_state.conversations[new_id] = {"title": "Nouvelle discussion", "messages": []}
        st.session_state.current_chat_id = new_id
        active_chat = st.session_state.conversations[new_id]
        active_messages = active_chat["messages"]

    active_messages.append({"role": "user", "content": prompt})
    if len(active_messages) == 1: active_chat["title"] = prompt[:15] + "..."
            
    save_conversation_to_db(st.session_state.user_email, st.session_state.current_chat_id, active_chat["title"], active_messages)
    st.rerun()

# Déclenchement de la réponse de l'IA
if st.session_state.current_chat_id is not None and len(active_messages) > 0 and active_messages[-1]["role"] == "user":
    messages_for_api = [{"role": "system", "content": str(SYSTEM_INSTRUCTION)}]
    for msg in active_messages:
        if isinstance(msg, dict) and "role" in msg and "content" in msg:
            messages_for_api.append({"role": str(msg["role"]), "content": str(msg["content"])})
        
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""
        try:
            completion = client.chat.completions.create(model=ACTIVE_MODEL, messages=messages_for_api, temperature=0.3, stream=True) # Température basse pour une analyse plus factuelle/rigoureuse
            for chunk in completion:
                if chunk.choices[0].delta.content is not None:
                    full_response += chunk.choices[0].delta.content
                    message_placeholder.markdown(full_response + " ▌")
            
            message_placeholder.markdown(full_response)
            active_messages.append({"role": "assistant", "content": full_response})
            save_conversation_to_db(st.session_state.user_email, st.session_state.current_chat_id, active_chat["title"], active_messages)
            st.rerun()
        except Exception as e: st.error(f"Erreur d'API : {e}")