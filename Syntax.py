import streamlit as st
import hashlib
import json
import datetime
import os
import io
import base64
from groq import Groq
from streamlit_cookies_controller import CookieController

# Import des modules d'analyse
try: import pypdf
except ImportError: pypdf = None
try: import docx
except ImportError: docx = None
try: import pandas as pd
except ImportError: pd = None

# ==============================================================================
# 1. CONFIGURATION DE LA PAGE & COOKIES
# ==============================================================================
st.set_page_config(page_title="Syntax IA", page_icon="⚡", layout="wide")

cookies = CookieController()
DATA_FILE = "syntax_data.json"

# ==============================================================================
# 2. GESTION DE LA BASE DE DONNÉES LOCALE
# ==============================================================================
def load_global_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f: return json.load(f)
        except: pass
    return {"users": {}, "conversations": {}}

def save_global_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=4)

def hash_password(password): return hashlib.sha256(password.encode()).hexdigest()

def register_user(email, password, username):
    data = load_global_data()
    email_clean = email.lower().strip()
    if email_clean in data["users"]: return False, "Cet e-mail est déjà utilisé."
    data["users"][email_clean] = {"password_hash": hash_password(password), "username": username.strip()}
    save_global_data(data)
    return True, "Utilisateur créé avec succès !"

def check_user(email, password):
    data = load_global_data()
    email_clean = email.lower().strip()
    if email_clean in data["users"] and data["users"][email_clean]["password_hash"] == hash_password(password):
        return data["users"][email_clean]["username"]
    return None

def save_conversation_local(user_email, chat_id, title, messages, is_pinned=False):
    data = load_global_data()
    email_clean = user_email.lower().strip()
    if email_clean not in data["conversations"]: data["conversations"][email_clean] = {}
    data["conversations"][email_clean][chat_id] = {
        "title": title,
        "messages": [{"role": str(m["role"]), "content": str(m["content"]), "is_image": m.get("is_image", False), "image_b64": m.get("image_b64", "")} for m in messages if isinstance(m, dict)],
        "is_pinned": is_pinned
    }
    save_global_data(data)

def delete_conversation_local(user_email, chat_id):
    data = load_global_data()
    email_clean = user_email.lower().strip()
    if email_clean in data["conversations"] and chat_id in data["conversations"][email_clean]:
        del data["conversations"][email_clean][chat_id]
        save_global_data(data)

def load_conversations_local(user_email):
    return load_global_data()["conversations"].get(user_email.lower().strip(), {})

# ==============================================================================
# 3. MOTEUR D'EXTRACTION UNIVERSEL CORRIGÉ
# ==============================================================================
def extract_file_content(uploaded_file, client_groq=None, action_type="Analyse standard"):
    name = uploaded_file.name.lower()
    ext = os.path.splitext(name)[1]
    file_bytes = uploaded_file.read()
    
    # --- IMAGES (Nouveau Modèle Supporté) ---
    if ext in [".png", ".jpg", ".jpeg", ".webp"]:
        encoded = base64.b64encode(file_bytes).decode("utf-8")
        mime = "image/jpeg" if ext in [".jpg", ".jpeg"] else f"image/{ext[1:]}"
        return {"type": "image", "data": f"data:{mime};base64,{encoded}"}

    # --- AUDIO PUR (Pas de transcription forcée, évite le texte bizarre) ---
    elif ext in [".mp3", ".wav", ".m4a"]:
        taille_mb = len(file_bytes) / (1024 * 1024)
        info_audio = f"--- FICHIER AUDIO IMPORTE ---\nNom : {uploaded_file.name}\nTaille : {taille_mb:.2f} MB\nAction demandée : {action_type}\n\n[L'utilisateur souhaite que tu analyses ce fichier audio/musique selon ses instructions de prompt.]"
        return {"type": "text", "data": info_audio}

    # --- VIDÉO MP4 (Extraction simplifiée sans MoviePy pour éviter le bug) ---
    elif ext == ".mp4":
        taille_mb = len(file_bytes) / (1024 * 1024)
        info_video = f"--- FICHIER VIDÉO MP4 IMPORTÉ ---\nNom : {uploaded_file.name}\nTaille : {taille_mb:.2f} MB\nAction demandée : {action_type}\n\n[Ce fichier MP4 a été téléversé avec succès. Analyse le contenu, sa structure ou réponds aux questions associées.]"
        return {"type": "text", "data": info_video}

    # --- DOCUMENTS TEXTES & DATA ---
    elif ext == ".pdf":
        if pypdf is None: return {"type": "text", "data": "Erreur : pypdf manquant."}
        pdf_reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        text = "".join([page.extract_text() + "\n" for page in pdf_reader.pages])
        return {"type": "text", "data": f"🎯 Objectif : {action_type}\n\n{text}"}
        
    elif ext == ".docx":
        if docx is None: return {"type": "text", "data": "Erreur : python-docx manquant."}
        doc = docx.Document(io.BytesIO(file_bytes))
        text = "\n".join([p.text for p in doc.paragraphs])
        return {"type": "text", "data": f"🎯 Objectif : {action_type}\n\n{text}"}
        
    elif ext in [".xlsx", ".xls", ".csv"]:
        if pd is None: return {"type": "text", "data": "Erreur : pandas manquant."}
        df = pd.read_csv(io.BytesIO(file_bytes)) if ext == ".csv" else pd.read_excel(io.BytesIO(file_bytes))
        return {"type": "text", "data": f"🎯 Objectif : {action_type}\n\n{df.to_markdown(index=False)}"}
        
    else:
        try: text_content = file_bytes.decode("utf-8")
        except: text_content = file_bytes.decode("latin-1")
        return {"type": "text", "data": f"🎯 Objectif : {action_type}\n\n{text_content}"}

# ==============================================================================
# 4. AUTHENTIFICATION COOKIES
# ==============================================================================
if "connected" not in st.session_state: st.session_state.connected = False
if "user_name" not in st.session_state: st.session_state.user_name = "Utilisateur"
if "user_email" not in st.session_state: st.session_state.user_email = ""

if not st.session_state.connected:
    saved_email = cookies.get("syntax_user_email")
    if saved_email:
        data = load_global_data()
        if saved_email.lower().strip() in data["users"]:
            st.session_state.connected = True
            st.session_state.user_email = saved_email
            st.session_state.user_name = data["users"][saved_email.lower().strip()]["username"]
            st.rerun()

if not st.session_state.connected:
    st.markdown("""
        <style>
        .stApp { background-color: #0b0b0f !important; color: white !important; }
        .login-box { max-width: 450px; margin: 10vh auto 0 auto; padding: 35px; background-color: #16161f; border: 1px solid rgba(128, 128, 128, 0.2); border-radius: 14px; box-shadow: 0 10px 25px rgba(0,0,0,0.3); }
        .stTabs [data-baseweb="tab-list"] { justify-content: center; }
        </style>
    """, unsafe_allow_html=True)
    st.markdown('<div class="login-box">', unsafe_allow_html=True)
    st.title("🤖 Bienvenue sur Syntax")
    tab_login, tab_register = st.tabs(["🔒 Se connecter", "📝 Créer un compte"])
    
    with tab_login:
        with st.form("login_form"):
            email_log = st.text_input("Adresse e-mail", placeholder="nom@exemple.com")
            pass_log = st.text_input("Mot de passe", type="password", placeholder="••••••••")
            if st.form_submit_button("🔑 Connexion"):
                db_username = check_user(email_log, pass_log)
                if db_username:
                    st.session_state.connected = True
                    st.session_state.user_email = email_log.lower()
                    st.session_state.user_name = db_username
                    cookies.set("syntax_user_email", email_log.lower(), expires=datetime.datetime.now() + datetime.timedelta(days=30))
                    st.session_state.conversations = load_conversations_local(email_log.lower())
                    st.session_state.current_chat_id = list(st.session_state.conversations.keys())[0] if st.session_state.conversations else None
                    st.rerun()
                else: st.error("E-mail ou mot de passe incorrect.")
                    
    with tab_register:
        with st.form("register_form"):
            email_reg = st.text_input("Adresse e-mail", placeholder="nom@exemple.com")
            pass_reg = st.text_input("Mot de passe", type="password", placeholder="Minimum 6 caractères")
            username_reg = st.text_input("Comment dois-je vous appeler ?", placeholder="Votre prénom ou pseudo")
            if st.form_submit_button("✨ Créer mon compte"):
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
# 5. INITIALISATION HISTORIQUE
# ==============================================================================
if "conversations" not in st.session_state or not st.session_state.conversations:
    saved_chats = load_conversations_local(st.session_state.user_email)
    st.session_state.conversations = saved_chats if saved_chats else {}
    if saved_chats and ("current_chat_id" not in st.session_state or st.session_state.current_chat_id is None):
        st.session_state.current_chat_id = list(saved_chats.keys())[0]
    elif "current_chat_id" not in st.session_state: st.session_state.current_chat_id = None

# ==============================================================================
# 6. STYLES DESIGN INTERFACE (Alignement Prompt et Import)
# ==============================================================================
st.markdown("""
    <style>
    .stApp, .stAppHeader { background-color: var(--background-color) !important; color: var(--text-color) !important; }
    section[data-testid="stSidebar"] { background-color: var(--secondary-background-color) !important; border-right: 1px solid rgba(128, 128, 128, 0.1); }
    .stButton>button[kind="primary"] { background-color: #6d28d9 !important; color: white !important; border-radius: 20px !important; font-weight: 600 !important; width: 100%; }
    
    div.sidebar-chat-btn > button { background-color: transparent !important; color: var(--text-color) !important; border: none !important; text-align: left !important; padding: 8px 10px !important; width: 100% !important; border-radius: 8px !important; font-size: 14px !important; text-overflow: ellipsis; white-space: nowrap; overflow: hidden; display: block; }
    div.sidebar-chat-btn > button:hover { background-color: rgba(255, 255, 255, 0.05) !important; }
    div.sidebar-chat-active > button { background-color: rgba(109, 40, 217, 0.15) !important; color: #a78bfa !important; font-weight: 500; }
    
    /* Design de la zone de contrôle du bas */
    .custom-input-container { background-color: #16161f; border: 1px solid rgba(128, 128, 128, 0.2); border-radius: 16px; padding: 15px; margin-top: 10px; }
    
    .syntax-logo { width: 50px; height: 50px; background: linear-gradient(135deg, #8b5cf6, #d946ef); border-radius: 14px; display: flex; align-items: center; justify-content: center; font-family: 'Courier New', monospace; font-weight: bold; font-size: 24px; color: white; box-shadow: 0 0 20px rgba(139, 92, 246, 0.3); margin: 0 auto 15px auto; }
    .welcome-text { text-align: center; font-size: 32px; font-weight: 500; color: var(--text-color); margin-top: 15vh; opacity: 0.9; }
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# 7. INITIALISATION DE L'IA GROQ & MODÈLES ACTIFS 2026
# ==============================================================================
if "GROQ_API_KEY" in st.secrets: client = Groq(api_key=st.secrets["GROQ_API_KEY"])
else: client = None

TEXT_MODEL = "llama-3.3-70b-specdec"  # Modèle texte & raisonnement ultra-rapide et à jour
VISION_MODEL = "llama-3.2-90b-vision-preview" # Nouveau modèle Vision valide et actif

SYSTEM_INSTRUCTION = (
    "Tu t'appelles Syntax. Tu es une IA multimédia de pointe. Tu analyses avec précision les textes, codes, images, musiques et vidéos. "
    "Sois direct, efficace et réponds de manière structurée sans formules de politesse superflues."
)

# ==============================================================================
# 8. PANNEAU LATÉRAL (SIDEBAR)
# ==============================================================================
with st.sidebar:
    st.write("")
    st.markdown('<div class="syntax-logo">&lt;/&gt;</div>', unsafe_allow_html=True)
    st.markdown("<h3 style='text-align: center;'>Syntax</h3>", unsafe_allow_html=True)
    st.caption(f"👋 {st.session_state.user_name}")
    
    if st.button("➕ Nouvelle discussion", key="global_new_chat", type="primary"):
        new_id = f"chat_{int(datetime.datetime.now().timestamp())}"
        st.session_state.conversations[new_id] = {"title": "Nouvelle discussion", "messages": [], "is_pinned": False}
        st.session_state.current_chat_id = new_id
        save_conversation_local(st.session_state.user_email, new_id, "Nouvelle discussion", [], False)
        st.rerun()

    st.markdown("---")
    
    sorted_chats = sorted(st.session_state.conversations.items(), key=lambda x: (x[1].get("is_pinned", False), x[0]), reverse=True)
    for chat_id, chat_data in sorted_chats:
        is_active = (chat_id == st.session_state.current_chat_id)
        is_pinned = chat_data.get("is_pinned", False)
        prefix = "📌 " if is_pinned else "💬 "
        display_title = chat_data['title']
        
        col_btn, col_opt = st.columns([0.82, 0.18])
        with col_btn:
            active_class = "sidebar-chat-active" if is_active else ""
            st.markdown(f'<div class="sidebar-chat-btn {active_class}">', unsafe_allow_html=True)
            if st.button(f"{prefix}{display_title}", key=f"nav_{chat_id}"):
                st.session_state.current_chat_id = chat_id
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
            
        with col_opt:
            with st.popover("⋮", help="Options"):
                if st.button("🔗 Partager", key=f"share_{chat_id}"): st.toast(f"Lien copié : {display_title}")
                pin_label = "📍 Désépingler" if is_pinned else "📌 Épingler"
                if st.button(pin_label, key=f"pin_{chat_id}"):
                    st.session_state.conversations[chat_id]["is_pinned"] = not is_pinned
                    save_conversation_local(st.session_state.user_email, chat_id, display_title, chat_data["messages"], not is_pinned)
                    st.rerun()
                new_title = st.text_input("Nom", value=display_title, key=f"ren_input_{chat_id}")
                if new_title != display_title and new_title.strip() != "":
                    st.session_state.conversations[chat_id]["title"] = new_title.strip()
                    save_conversation_local(st.session_state.user_email, chat_id, new_title.strip(), chat_data["messages"], is_pinned)
                    st.rerun()
                st.markdown("---")
                if st.button("🗑️ Supprimer", key=f"del_{chat_id}"):
                    delete_conversation_local(st.session_state.user_email, chat_id)
                    del st.session_state.conversations[chat_id]
                    if st.session_state.current_chat_id == chat_id:
                        st.session_state.current_chat_id = list(st.session_state.conversations.keys())[0] if st.session_state.conversations else None
                    st.rerun()
        
    st.container(height=50, border=False) 
    st.markdown("---")
    if st.button("🚪 Déconnexion", key="global_logout"):
        cookies.remove("syntax_user_email")
        for key in list(st.session_state.keys()): del st.session_state[key]
        st.rerun()

# ==============================================================================
# 9. ZONE DE CHAT VISUELLE
# ==============================================================================
if st.session_state.current_chat_id is None or st.session_state.current_chat_id not in st.session_state.conversations:
    st.markdown(f'<div class="welcome-text">Syntax IA — Prêt pour vos analyses multimédias.</div>', unsafe_allow_html=True)
    active_messages = []
else:
    active_chat = st.session_state.conversations[st.session_state.current_chat_id]
    active_messages = active_chat["messages"]
    if len(active_messages) == 0:
        st.markdown(f'<div class="welcome-text">Syntax IA — Prêt pour vos analyses multimédias.</div>', unsafe_allow_html=True)
    else:
        for message in active_messages:
            with st.chat_message(message["role"]):
                if message.get("is_image", False):
                    st.image(message["image_b64"], caption="Fichier Image")
                st.markdown(message["content"])

# ==============================================================================
# 10. NOUVELLE BARRE DE PROMPT AVEC IMPORTATION ET ACTION À GAUCHE
# ==============================================================================
st.write("") # Espace visuel avant la barre fixe du bas

with st.container():
    st.markdown('<div class="custom-input-container">', unsafe_allow_html=True)
    
    # Découpage en colonnes : Importation / Choix de l'action / Barre d'écriture
    c_file, c_action, c_prompt = st.columns([0.25, 0.25, 0.50])
    
    with c_file:
        up_file = st.file_uploader(
            "Importer", 
            type=["txt", "py", "js", "json", "md", "csv", "pdf", "docx", "xlsx", "png", "jpg", "jpeg", "webp", "mp3", "wav", "m4a", "mp4"],
            label_visibility="collapsed",
            key="barre_upload"
        )
    
    with c_action:
        choix_action = st.selectbox(
            "Que faire avec ce fichier ?",
            ["Analyse standard", "Résumé exhaustif", "Trouver les erreurs / bugs", "Extraire les points clés", "Explication simple"],
            label_visibility="collapsed",
            key="barre_action"
        )
        
    with c_prompt:
        user_prompt = st.text_input(
            "Pose ta question à Syntax...", 
            label_visibility="collapsed",
            placeholder="Pose ta question ou ajoute des détails sur le fichier ici... (Entrée pour envoyer)",
            key="barre_prompt"
        )
        
    st.markdown('</div>', unsafe_allow_html=True)

# ==============================================================================
# 11. TRAITEMENT DE L'ENVOI MULTIMÉDIA COMBINÉ
# ==============================================================================
if user_prompt or (up_file is not None and "sent_" + up_file.name not in st.session_state):
    if client is None:
        st.error("Clé Groq manquante."); st.stop()
        
    # Créer une discussion si aucune n'est active
    if st.session_state.current_chat_id is None:
        new_id = f"chat_{int(datetime.datetime.now().timestamp())}"
        st.session_state.conversations[new_id] = {"title": "Nouvelle discussion", "messages": [], "is_pinned": False}
        st.session_state.current_chat_id = new_id
        active_chat = st.session_state.conversations[new_id]
        active_messages = active_chat["messages"]

    # Scénario 1 : Un fichier est importé
    if up_file is not None and "sent_" + up_file.name not in st.session_state:
        st.session_state["sent_" + up_file.name] = True
        with st.spinner("Analyse du média..."):
            result = extract_file_content(up_file, client_groq=client, action_type=choix_action)
            
            texte_final = result["data"]
            if user_prompt:
                texte_final += f"\n\n👉 **Instruction complémentaire de l'utilisateur** : {user_prompt}"
                
            if result["type"] == "image":
                active_messages.append({
                    "role": "user", 
                    "content": f"Action requise : {choix_action}. " + (user_prompt if user_prompt else "Analyse cette image."), 
                    "is_image": True, 
                    "image_b64": result["data"]
                })
            else:
                active_messages.append({"role": "user", "content": texte_final, "is_image": False, "image_b64": ""})
                
            if len(active_messages) <= 2: active_chat["title"] = f"📁 {up_file.name[:12]}..."
    
    # Scénario 2 : Message texte pur
    elif user_prompt:
        active_messages.append({"role": "user", "content": user_prompt, "is_image": False, "image_b64": ""})
        if len(active_messages) == 1: active_chat["title"] = user_prompt[:18] + "..."

    save_conversation_local(st.session_state.user_email, st.session_state.current_chat_id, active_chat["title"], active_messages, active_chat.get("is_pinned", False))
    st.rerun()

# ==============================================================================
# 12. STREAM DE L'API (ROUTAGE INTELLIGENT)
# ==============================================================================
if st.session_state.current_chat_id is not None and len(active_messages) > 0 and active_messages[-1]["role"] == "user":
    last_msg = active_messages[-1]
    is_vision_turn = last_msg.get("is_image", False)
    
    selected_model = VISION_MODEL if is_vision_turn else TEXT_MODEL
    messages_for_api = []
    
    if is_vision_turn:
        messages_for_api = [
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": last_msg["content"]},
                    {"type": "image_url", "image_url": {"url": last_msg["image_b64"]}}
                ]
            }
        ]
    else:
        messages_for_api.append({"role": "system", "content": SYSTEM_INSTRUCTION})
        for msg in active_messages:
            if isinstance(msg, dict):
                if msg.get("is_image", False):
                    messages_for_api.append({"role": "user", "content": "[Image analysée en début de session]"})
                else:
                    messages_for_api.append({"role": str(msg["role"]), "content": str(msg["content"])})
        
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""
        try:
            completion = client.chat.completions.create(model=selected_model, messages=messages_for_api, temperature=0.2, stream=True)
            for chunk in completion:
                if chunk.choices[0].delta.content is not None:
                    full_response += chunk.choices[0].delta.content
                    message_placeholder.markdown(full_response + " ▌")
            message_placeholder.markdown(full_response)
            active_messages.append({"role": "assistant", "content": full_response, "is_image": False, "image_b64": ""})
            save_conversation_local(st.session_state.user_email, st.session_state.current_chat_id, active_chat["title"], active_messages, active_chat.get("is_pinned", False))
            st.rerun()
        except Exception as e: st.error(f"Erreur d'API : {e}")