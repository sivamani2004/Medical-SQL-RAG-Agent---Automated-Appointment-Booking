import streamlit as st
from main import get_medibot_response  

st.set_page_config(page_title="MediBot", page_icon="🩺")
st.title("🏥 MediBot — AI Appointment Assistant")

if "chat" not in st.session_state:
    st.session_state.chat = []

user_input = st.chat_input("Type your message...")
if user_input:
    st.session_state.chat.append(("You", user_input))
    with st.spinner("Thinking..."):
        reply = get_medibot_response(user_input)  
    st.session_state.chat.append(("MediBot", reply))

for role, msg in st.session_state.chat:
    with st.chat_message(role):
        st.markdown(msg)
