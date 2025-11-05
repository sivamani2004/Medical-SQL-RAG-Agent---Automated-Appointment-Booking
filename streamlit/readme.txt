To have an interactive UI experience of the chatbot, use the same venv created before and run this command below :

pip install streamlit

After streamlit is installed, download app.py and main.py in the same root directory where venv is present.
The main.py is essentially the hospital_agent.ipynb notebook file converted to simple python file but with an additional 
get_medibot_response(user_input) function which is imported in app.py streamlit app file. Run the below command in terminal
to launch to app in localhost : 

streamlit run app.py
