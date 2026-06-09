import streamlit as st
import hashlib
import json
import datetime
import os
import io
import base64
from groq import Groq
from streamlit_cookies_controller import CookieController

# Import des modules d'analyse avancés
try: import pypdf
except ImportError: pypdf = None
try: import docx
except ImportError: docx = None
try: import pandas as pd
except ImportError: pd = None
try: from moviepy.editor import AudioFileClip
except ImportError: AudioFileClip = None

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
# 3. MOTEUR D'EXTRACTION UNIVERSEL (Texte, Data, Audio, Vidéo, Image)
# ==============================================================================
def extract_file_content(uploaded_file, client_groq=None):
    name = uploaded_file.name.lower()
    ext = os.path.splitext(name)[1]
    file_bytes = uploaded_file.read()
    
    # --- CATÉGORIE 1 : LES IMAGES (Vision) ---
    if ext in [".png", ".jpg", ".jpeg", ".webp"]:
        encoded = base64.b64encode(file_bytes).decode("utf-8")
        mime = "image/jpeg" if ext in [".jpg", ".jpeg"] else f"image/{ext[1:]}"
        return {"type": "image", "data": f"data:{mime};base64,{encoded}"}

    # --- CATÉGORIE 2 : LES AUDIOS ET VIDÉOS (Transcription Whisper) ---
    elif ext in [".mp3", ".wav", ".m4a", ".mp4"]:
        if client_groq is None:
            return {"type": "text", "data": "Erreur : Client Groq indisponible pour la transcription audio."}
        
        # Gestion spécifique du conteneur MP4 (Vidéo) -> Extraction Audio
        if ext == ".mp4":
            if AudioFileClip is None:
                return {"type": "text", "data": "Erreur : La bibliothèque 'moviepy' est requise pour analyser les vidéos MP4."}
            with open("temp_video.mp4", "wb") as f: f.write(file_bytes)
            try:
                clip = AudioFileClip("temp_video.mp4")
                clip.write_audiofile("temp_extracted.mp3", logger=None)
                clip.close()
                with open("temp_extracted.mp3", "rb") as audio_f: audio_bytes = audio_f.read()
                audio_name = "extracted_audio.mp3"
            finally:
                if os.path.exists("temp_video.mp4"): os.remove("temp_video.mp4")
                if os.path.exists("temp_extracted.mp3"): os.remove("temp_extracted.mp3")
        else:
            audio_bytes = file_bytes
            audio_name = uploaded_file.name

        # Envoi à l'API Whisper de Groq
        try:
            translation = client_groq.audio.transcriptions.create(
                file=(audio_name, audio_bytes),
                model="whisper-large-v3",
                response_format="text"
            )
            return {"type": "text", "data": f"--- TRANSCRIPTION AUTOMATIQUE DU FICHIER AUDIO/VIDÉO ({uploaded_file.name}) ---\n\n{translation}"}
        except Exception as e:
            return {"type": "text", "data": f"Erreur lors de la transcription audio par Groq : {str(e)}"}

    # --- CATÉGORIE 3 : DOCUMENTS CLASSIQUES (PDF, Word, Excel, Texte) ---
    elif ext == ".pdf":
        if pypdf is None: return {"type": "text", "data": "Erreur : pypdf manquant."}
        pdf_reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        text = "".join([page.extract_text() + "\n" for page in pdf_reader.pages])
        return {"type": "text", "data": text if text.strip() else "PDF vide ou uniquement composé d'images."}
        
    elif ext == ".docx":
        if docx is None: return {"type": "text", "data": "Erreur : python-docx manquant."}
        doc = docx.Document(io.BytesIO(file_bytes))
        return {"type": "text", "data": "\n".join([p.text for p in doc.paragraphs])}
        
    elif ext in [".xlsx", ".xls"]:
        if pd is None: return {"type": "text", "data": "Erreur : pandas manquant."}
        df = pd.read_excel(io.BytesIO(file_bytes))
        return {"type": "text", "data": df.to_markdown(index=False)}
        
    elif ext == ".csv":
        if pd is None: return {"type": "text", "data": "Erreur : pandas manquant."}
        df = pd.read_csv(io.BytesIO(file_bytes))
        return {"type": "text", "data": df.to_markdown(index=False)}
        
    else:
        try: return {"type": "text", "data": file_bytes.decode("utf-8")}
        except:
            try: return {"type": "text", "data": file_bytes.decode("latin-1")}
            except Exception as e: return {"type": "text", "data": f"Fichier texte illisible : {str(e)}"}

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
# 6. STYLES DESIGN INTERFACE
# ==============================================================================
st.markdown("""
    <style>
    .stApp, .stAppHeader { background-color: var(--background-color) !important; color: var(--text-color) !important; }
    div[data-testid="stChatInputContainer"] { background-color: var(--background-color) !important; border: none !important; padding-bottom: 25px; }
    div[data-testid="stChatInputContainer"] > div { background-color: var(--secondary-background-color) !important; border: 1px solid rgba(128, 128, 128, 0.2) !important; border-radius: 28px !important; }
    section[data-testid="stSidebar"] { background-color: var(--secondary-background-color) !important; border-right: 1px solid rgba(128, 128, 128, 0.1); }
    .stButton>button[kind="primary"] { background-color: #6d28d9 !important; color: white !important; border-radius: 20px !important; font-weight: 600 !important; width: 100%; }
    
    div.sidebar-chat-row { display: flex; align-items: center; justify-content: space-between; width: 100%; margin-bottom: 5px; }
    div.sidebar-chat-btn > button { background-color: transparent !important; color: var(--text-color) !important; border: none !important; text-align: left !important; padding: 8px 10px !important; width: 100% !important; border-radius: 8px !important; font-size: 14px !important; text-overflow: ellipsis; white-space: nowrap; overflow: hidden; display: block; }
    div.sidebar-chat-btn > button:hover { background-color: rgba(255, 255, 255, 0.05) !important; }
    div.sidebar-chat-active > button { background-color: rgba(109, 40, 217, 0.15) !important; color: #a78bfa !important; font-weight: 500; }
    
    div[data-testid="stPopover"] > button { background-color: transparent !important; border: none !important; padding: 4px 8px !important; color: var(--text-color) !important; opacity: 0.5; }
    div[data-testid="stPopover"] > button:hover { opacity: 1 !important; background-color: rgba(255, 255, 255, 0.1) !important; }
    
    .syntax-logo { width: 50px; height: 50px; background: linear-gradient(135deg, #8b5cf6, #d946ef); border-radius: 14px; display: flex; align-items: center; justify-content: center; font-family: 'Courier New', monospace; font-weight: bold; font-size: 24px; color: white; box-shadow: 0 0 20px rgba(139, 92, 246, 0.3); margin: 0 auto 15px auto; }
    .welcome-text { text-align: center; font-size: 32px; font-weight: 500; color: var(--text-color); margin-top: 15vh; opacity: 0.9; }
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# 7. INITIALISATION DE L'IA GROQ
# ==============================================================================
if "GROQ_API_KEY" in st.secrets: client = Groq(api_key=st.secrets["GROQ_API_KEY"])
else: client = None

TEXT_MODEL = "llama-3.1-8b-instant"
VISION_MODEL = "llama-3.2-11b-vision-preview"

SYSTEM_INSTRUCTION = (
    "Tu t'appelles Syntax. Tu es un système d'intelligence artificielle multimédia hautement perfectionné. "
    "Tu es capable d'analyser du code, des textes, des fichiers de données, des images, mais aussi des transcriptions de fichiers audios et vidéos."
    "RÈGLE D'ANALYSE : Sois direct, technique, précis et factuel sans fioritures."
)

# ==============================================================================
# 8. PANNEAU LATÉRAL (SIDEBAR) & OPTIONS
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
    st.markdown("📁 **Analyseur Multimédia Total**")
    uploaded_file = st.file_uploader(
        "Fichier", 
        type=["txt", "py", "js", "json", "md", "csv", "pdf", "docx", "xlsx", "png", "jpg", "jpeg", "webp", "mp3", "wav", "m4a", "mp4"], 
        label_visibility="collapsed"
    )
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
# 9. ZONE DE CHAT & TRAITEMENT
# ==============================================================================
if st.session_state.current_chat_id is None or st.session_state.current_chat_id not in st.session_state.conversations:
    st.markdown(f'<div class="welcome-text">Envoyez un texte, un document, une image, un audio ou un MP4...</div>', unsafe_allow_html=True)
    active_messages = []
else:
    active_chat = st.session_state.conversations[st.session_state.current_chat_id]
    active_messages = active_chat["messages"]
    if len(active_messages) == 0:
        st.markdown(f'<div class="welcome-text">Envoyez un texte, un document, une image, un audio ou un MP4...</div>', unsafe_allow_html=True)
    else:
        for message in active_messages:
            with st.chat_message(message["role"]):
                if message.get("is_image", False):
                    st.image(message["image_b64"], caption="Image analysée")
                st.markdown(message["content"])

# Gestion et interception des fichiers importés
if uploaded_file is not None and "last_uploaded" not in st.session_state:
    with st.spinner("Traitement du fichier multimédia en cours..."):
        result = extract_file_content(uploaded_file, client_groq=client)
        st.session_state.last_uploaded = uploaded_file.name
        
        if st.session_state.current_chat_id is None:
            new_id = f"chat_{int(datetime.datetime.now().timestamp())}"
            st.session_state.conversations[new_id] = {"title": f"📁 {uploaded_file.name[:12]}", "messages": [], "is_pinned": False}
            st.session_state.current_chat_id = new_id
            active_chat = st.session_state.conversations[new_id]
            active_messages = active_chat["messages"]
            
        if result["type"] == "image":
            active_messages.append({
                "role": "user", 
                "content": f"Analyse cette image ({uploaded_file.name}) en détail s'il te plaît.", 
                "is_image": True, 
                "image_b64": result["data"]
            })
        else:
            active_messages.append({"role": "user", "content": result["data"], "is_image": False, "image_b64": ""})
            
        save_conversation_local(st.session_state.user_email, st.session_state.current_chat_id, active_chat["title"], active_messages, active_chat.get("is_pinned", False))
        st.rerun()

if uploaded_file is None and "last_uploaded" in st.session_state:
    del st.session_state.last_uploaded

# Input Chat
if prompt := st.chat_input("Pose ta question à Syntax..."):
    if client is None: st.error("Clé Groq manquante."); st.stop()

    if st.session_state.current_chat_id is None:
        new_id = f"chat_{int(datetime.datetime.now().timestamp())}"
        st.session_state.conversations[new_id] = {"title": "Nouvelle discussion", "messages": [], "is_pinned": False}
        st.session_state.current_chat_id = new_id
        active_chat = st.session_state.conversations[new_id]
        active_messages = active_chat["messages"]

    active_messages.append({"role": "user", "content": prompt, "is_image": False, "image_b64": ""})
    if len(active_messages) == 1: active_chat["title"] = prompt[:18] + "..."
    save_conversation_local(st.session_state.user_email, st.session_state.current_chat_id, active_chat["title"], active_messages, active_chat.get("is_pinned", False))
    st.rerun()

# Stream de l'API avec routage Llama 3.1 (Texte) VS Llama 3.2 Vision (Image)
if st.session_state.current_chat_id is not None and len(active_messages) > 0 and active_messages[-1]["role"] == "user":
    # Détecter si la conversation contient une image à analyser au dernier tour
    last_msg = active_messages[-1]
    is_vision_turn = last_msg.get("is_image", False)
    
    messages_for_api = []
    selected_model = VISION_MODEL if is_vision_turn else TEXT_MODEL
    
    if is_vision_turn:
        # Format spécifique pour l'API Vision de Groq
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
                # Éviter de renvoyer le bloc lourd base64 d'image dans les tours de texte purs historiques si non supporté
                if msg.get("is_image", False):
                    messages_for_api.append({"role": "user", "content": "[Image envoyée précédemment]"})
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