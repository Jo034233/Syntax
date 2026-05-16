import streamlit as st
from groq import Groq

# 1. Configuration de l'interface graphique (Style épuré et professionnel)
st.set_page_config(page_title="Syntax", page_icon="🤖", layout="centered")
st.title("🤖 Syntax")
st.caption("Ton assistant IA textuel personnel")

# Lecture sécurisée de la clé sur les serveurs de Streamlit
GROQ_API_KEY = st.secrets["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"]

# Consigne de personnalité calquée sur moi (Copilot / IA d'accompagnement)
SYSTEM_INSTRUCTION = (
    "Tu t'appelles Syntax. Tu es un assistant IA personnel spécialisé dans l'accompagnement technique, "
    "le développement, et la résolution de problèmes. Ton ton est identique à celui d'un grand modèle "
    "de langage moderne : tu es amical, extrêmement pédagogue, clair, et tu utilises un ton enthousiaste "
    "et constructif (avec quelques emojis bien placés pour structurer tes réponses). "
    "Tu t'adresses directement à l'utilisateur. Tu es un modèle purement textuel : "
    "tu ne génères JAMAIS d'images ni de musique. Si on te le demande, refuse poliment en expliquant tes limites."
)

# 3. Gestion de l'historique de la discussion
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "system", "content": SYSTEM_INSTRUCTION}]

# 4. Affichage de l'historique des messages (en masquant la consigne système)
for message in st.session_state.messages:
    if message["role"] != "system":
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

# 5. Zone d'écriture
if user_input := st.chat_input("Discute avec Syntax..."):
    # On affiche et sauvegarde le message de l'utilisateur
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # Requête sécurisée à Groq avec la nouvelle personnalité
    with st.chat_message("assistant"):
        with st.spinner("Syntax réfléchit..."):
            try:
                client = Groq(api_key=GROQ_API_KEY)
                
                chat_completion = client.chat.completions.create(
                    messages=st.session_state.messages,
                    model="llama-3.3-70b-versatile",
                    temperature=0.7,
                )
                response_text = chat_completion.choices[0].message.content
                st.markdown(response_text)
                
                # Sauvegarde du message de Syntax
                st.session_state.messages.append({"role": "assistant", "content": response_text})
                
            except Exception as e:
                st.error(f"Erreur technique : {e}")