import os
import re  # Used for date validation
import ast # Used to safely parse the string from db.run()
from datetime import datetime

# === LANGCHAIN CORE IMPORTS ===
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.tools import tool 

# === LANGCHAIN AI & DB IMPORTS ===
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.utilities.sql_database import SQLDatabase

# === LANGCHAIN RAG IMPORTS ===
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_pinecone import PineconeVectorStore

# === LANGCHAIN AGENT IMPORTS ===
from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver # For agent memory
from langchain_core.messages import HumanMessage, AIMessage

# === OTHER LIBRARIES ===
from pinecone import Pinecone
from dotenv import load_dotenv

load_dotenv()

db_uri = "postgresql://postgres:postgres@localhost:54876/hospital_db"
db = SQLDatabase.from_uri(db_uri)
print(db.dialect)
print(db.get_table_names())

llm = ChatOpenAI(model = "gpt-5-nano", temperature=0)

# Function to reset Pinecone vector database incase of changing the any parameters
def reset_vector_db():
    pc = Pinecone(api_key=os.environ.get("PINECONE_API_KEY"))
    index = pc.Index("hospitalbot")
    index.delete(delete_all=True)
    print("Vector DB 'hospitalbot' erased.")

reset_vector_db()

def setup_pinecone_rag():
    """Initialize Pinecone vector store with knowledge base"""
    print("\\n🔄 Setting up Pinecone RAG system...")
    
    # Initialize Pinecone
    index_name = "hospitalbot"
    
    # Load knowledge base PDF
    print("  Loading knowledge_base.pdf...")
    loader = PyPDFLoader("/Users/sivamanipatnala/Downloads/Projects/Hospital_bot/knowledge_base.pdf")
    documents = loader.load()
    print(f"  ✓ Loaded {len(documents)} pages")
    
    # Split documents
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=256, # Adjusted chunk size for small 8 page knowledge base (1732 words)
        chunk_overlap=50
    )
    splits = text_splitter.split_documents(documents)
    print(f"  ✓ Created {len(splits)} document chunks")
    
    # Create embeddings
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    
    # Create or connect to Pinecone index
    print("  Creating vector store...")
    vectorstore = PineconeVectorStore.from_documents(
        documents=splits,
        embedding=embeddings,
        index_name=index_name
    )
    print("✓ Pinecone RAG system ready\\n")
    
    return vectorstore.as_retriever(search_type="similarity",search_kwargs={"k": 3})

retriever = setup_pinecone_rag()



@tool
def get_doctor_recommendations(symptoms: str) -> str:
    """
    Use this tool to find the correct medical specialty for a patient's symptoms.
    The input should be a string describing the patient's complaints or condition.
    The output will be a single string: the name of the specialty.
    """
    print(f"\n🤖 RAG Tool: Searching for specialty for symptoms: '{symptoms}'")
    
    try:
        # 1. Retrieve relevant documents from your PDF
        docs = retriever.invoke(symptoms)
        
        # 2. Format the retrieved context
        context = "\n\n".join([doc.page_content for doc in docs])
        
        # 3. Create a strict prompt to extract *only* the specialty name
        # This is the most critical change.
        prompt = f"""
        You are an expert medical router. Your job is to extract the correct medical specialty 
        from the provided context, based on the patient's symptoms.
        
        The user's symptoms are: "{symptoms}"
        
        Here is the hospital guide (context) from the knowledge base:
        ---
        {context}
        ---
        
        Based *only* on the context and symptoms, what is the single, exact specialty name
        the patient should be referred to?
        
        - If the symptoms are an EMERGENCY (e.g., severe chest pain, stroke, can't breathe),
          return the string "EMERGENCY".
        - If the symptoms are vague or general (e.g., "feel sick", "checkup"), 
          return the string "General Physician".
        - For all other cases, return the *exact* specialty name from the text 
          (e.g., "Cardiology", "Dermatology", "Neurology").
        
        Do not add any explanation or conversational text. Just return the specialty name.
        
        Specialty:
        """
        
        # 4. Invoke the LLM (which is now correctly in the global scope)
        response = llm.invoke(prompt)
        specialty = response.content.strip()
        
        print(f"  ✓ RAG Tool: Found specialty: '{specialty}'")
        return specialty
        
    except Exception as e:
        print(f"  ❌ RAG Tool: Error getting recommendations: {str(e)}")
        # Fallback to a safe default that is in your database
        return "General Physician"
    
# Prevent SQL injection
# This is our security "allow-list"
SPECIALTY_ALLOW_LIST = [
    'Cardiology', 'Pediatrics', 'Orthopedics', 'Dermatology', 'Neurology',
    'General Physician', 'Psychiatry', 'Gynecology', 'Gastroenterology',
    'Pulmonology', 'Urology', 'Ophthalmology', 'Endocrinology', 'Nephrology'
]

@tool
def get_available_doctors(specialty: str) -> str:
    """
    Finds the least-busy doctors for a given medical specialty.
    
    Args:
        specialty: The medical specialty (e.g., Cardiology, Dermatology)
    
    Returns:
        A string list of available doctors and their total scheduled appointments.
    """
    print(f"\n🤖 SQL Tool: Searching for doctors in: '{specialty}'")

    # --- SQL INJECTION VALIDATION ---
    if specialty not in SPECIALTY_ALLOW_LIST:
        print(f"  ❌ SQL Tool: Invalid specialty '{specialty}'. Not in allow-list.")
        return f"Error: The specialty '{specialty}' is not recognized. Please try a valid specialty."

    try:
        # The query is now safe because 'specialty' is validated
        query = f"""
        SELECT 
            d.doctor_id,
            d.name,
            d.speciality
        FROM doctors d
        LEFT JOIN appointments a ON d.doctor_id = a.doctor_id 
            AND a.status = 'Scheduled'
        WHERE d.speciality = '{specialty}'
        GROUP BY d.doctor_id, d.name, d.speciality
        ORDER BY COUNT(a.appointment_id) ASC
        LIMIT 5
        """
        
        result = db.run(query)
        
        if result:
            # --- REMOVED DECEPTIVE OUTPUT ---
            # Just return the raw data. The agent will handle the conversation.
            output = f"Here is a list of available doctors for {specialty}:\n{result}"
            print(f"  ✓ SQL Tool: Found doctors:\n{result}")
            return output
        else:
            # This is a good fallback!
            print(f"  ✓ SQL Tool: No doctors found for '{specialty}'.")
            return f"No {specialty} doctors found in our system. Would you like to see a General Physician instead?"
            
    except Exception as e:
        print(f"  ❌ SQL Tool: Error querying database: {str(e)}")
        return f"Error querying doctors: {str(e)}"
    
# 'db' (SQLDatabase object) is already defined globally
# 'db' will be used in all tools below

@tool
def check_appointment_slots(doctor_id: int, date: str) -> str:
    """
    Check available time slots for a specific doctor on a given date.
    Assumes 30-minute appointment slots from 9 AM to 5 PM (with 1-2 PM lunch).
    
    Args:
        doctor_id: Doctor's ID from database
        date: Date in YYYY-MM-DD format
    
    Returns:
        A string list of available time slots
    """
    print(f"\n🤖 Slot Tool: Checking slots for Dr. {doctor_id} on {date}")

    # --- SECURITY VALIDATION ---
    # Validate date format to prevent SQL injection
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        print(f"  ❌ Slot Tool: Invalid date format: {date}")
        return "Error: Date must be in YYYY-MM-DD format."
        
    # Validate doctor_id is a number
    try:
        valid_doctor_id = int(doctor_id)
    except ValueError:
        print(f"  ❌ Slot Tool: Invalid doctor_id: {doctor_id}")
        return "Error: Invalid doctor_id."

    try:
        # Query is now safe as inputs are validated
        query = f"""
        SELECT 
            TO_CHAR(appointment_datetime, 'HH24:MI') as time_slot
        FROM appointments
        WHERE doctor_id = {valid_doctor_id} 
            AND DATE(appointment_datetime) = '{date}'
            AND status = 'Scheduled'
        ORDER BY appointment_datetime
        """
        
        booked_slots_result = db.run(query)
        
        # --- (Parsing db.run() output) ---
        # db.run() returns a string like "[('09:00',), ('10:30',)]"
        # We need to parse this string into a real list.
        booked_slots_list = []
        if booked_slots_result and str(booked_slots_result) != '[]':
            try:
                # ast.literal_eval safely parses the string representation
                parsed_result = ast.literal_eval(booked_slots_result)
                # Extract the time strings from the list of tuples
                booked_slots_list = [slot[0] for slot in parsed_result]
            except Exception as parse_error:
                print(f"  ❌ Slot Tool: Error parsing booked slots: {parse_error}")
                return f"Error: Could not parse booking data: {booked_slots_result}"
        
        booked_slots_set = set(booked_slots_list)
        print(f"  ✓ Slot Tool: Found booked slots: {booked_slots_set}")

        # Generate all possible slots (9 AM - 5 PM, 30-min intervals, 1-2 PM lunch)
        all_slots = [
            "09:00", "09:30", "10:00", "10:30", "11:00", "11:30",
            "12:00", "12:30", "14:00", "14:30", "15:00", "15:30",
            "16:00", "16:30"
        ]
        
        # Filtering 
        # This is the core logic 
        available_slots = [slot for slot in all_slots if slot not in booked_slots_set]
        
        if not available_slots:
            return f"No available time slots found for Doctor ID {valid_doctor_id} on {date}."

        # Format output
        output = f"Available time slots for Doctor ID {valid_doctor_id} on {date}:\n\n"
        for i, slot in enumerate(available_slots, 1):
            time_12hr = datetime.strptime(slot, "%H:%M").strftime("%I:%M %p")
            output += f"{i}. {slot} ({time_12hr})\n"
        
        return output
        
    except Exception as e:
        print(f"  ❌ Slot Tool: Unexpected error: {str(e)}")
        return f"Error checking slots: {str(e)}"
    
@tool
def create_patient_record(
    name: str, 
    phone: str, 
    email: str, 
    age: int, 
    gender: str, 
    emergency_contact_name: str = "", 
    emergency_contact_phone: str = "") -> str:
    """
    Create a new patient record in the database.
    
    Args:
        name: Patient full name
        phone: Contact phone (10 digits)
        email: Email address
        age: Patient age
        gender: Male or Female
        emergency_contact_name: Emergency contact name
        emergency_contact_phone: Emergency contact phone
    
    Returns:
        Patient ID if successful, error message otherwise
    """
    print(f"\n🤖 Patient Tool: Attempting to create patient: {name}")

    # --- SECURITY & VALIDATION ---
    if not all([name, phone, age, gender]):
        return "Error: Required fields missing (name, phone, age, gender)"
            
    if gender not in ['Male', 'Female']:
        return "Error: Gender must be 'Male' or 'Female'"
            
    if not re.match(r"^\d{10}$", str(phone)):
        return "Error: Phone must be exactly 10 digits."
        
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        return "Error: Invalid email address format."

    try:
        valid_age = int(age)
        if valid_age <= 0 or valid_age > 120:
            return "Error: Invalid age."
    except ValueError:
        return "Error: Age must be a number."

    # Sanitize string inputs to prevent SQL injection
    # This replaces single quotes to prevent breaking the SQL string
    safe_name = name.replace("'", "''")
    safe_email = email.replace("'", "''")
    safe_e_name = emergency_contact_name.replace("'", "''")
    safe_e_phone = emergency_contact_phone.replace("'", "''")
    # Phone, age, and gender are already validated
    
    try:
        # Check if patient already exists (using safe_phone)
        check_query = f"SELECT patient_id FROM patients WHERE phone = '{phone}' LIMIT 1"
        existing_result = db.run(check_query)
        
        if existing_result and str(existing_result) != '[]':
            # Parse the ID correctly
            patient_id = ast.literal_eval(existing_result)[0][0]
            print(f"  ✓ Patient Tool: Patient already exists (ID: {patient_id})")
            return f"Patient record already exists with this phone number. Patient ID: {patient_id}"
            
        # Insert new patient with safe, sanitized data
        query = f"""
        INSERT INTO patients (name, phone, email, age, gender, emergency_contact_name, emergency_contact_phone)
        VALUES ('{safe_name}', '{phone}', '{safe_email}', {valid_age}, '{gender}', '{safe_e_name}', '{safe_e_phone}')
        RETURNING patient_id
        """
        
        insert_result = db.run(query) # Will return string like "[('124',)]"
        
        # Parse the new ID correctly, again using ast for parsing db output
        new_patient_id = ast.literal_eval(insert_result)[0][0]
        print(f"  ✓ Patient Tool: Created new patient (ID: {new_patient_id})")
        return f"✓ Patient record created successfully. Patient ID: {new_patient_id}"
        
    except Exception as e:
        print(f"  ❌ Patient Tool: Error: {str(e)}")
        return f"Error creating patient record: {str(e)}"
    
@tool
def book_appointment(
    patient_id: int, 
    doctor_id: int, 
    appointment_date: str, 
    appointment_time: str, 
    reason: str) -> str:
    """
    Book an appointment in the database.
    
    Args:
        patient_id: Patient's ID from database
        doctor_id: Doctor's ID from database
        appointment_date: Date in YYYY-MM-DD format
        appointment_time: Time in HH:MM format (24-hour)
        reason: Reason for visit/symptoms
    
    Returns:
        Confirmation message with appointment details
    """
    print(f"\n🤖 Booking Tool: Attempting to book Dr. {doctor_id} for Pt. {patient_id} at {appointment_date} {appointment_time}")

    # --- SECURITY & VALIDATION ---
    try:
        valid_patient_id = int(patient_id)
        valid_doctor_id = int(doctor_id)
    except ValueError:
        return "Error: patient_id and doctor_id must be numbers."

    if not re.match(r"^\d{4}-\d{2}-\d{2}$", appointment_date):
        return "Error: Invalid date format. Use YYYY-MM-DD."
        
    if not re.match(r"^\d{2}:\d{2}$", appointment_time):
         return "Error: Invalid time format. Use HH:MM (24-hour)."

    try:
        appointment_datetime = f"{appointment_date} {appointment_time}:00"
        datetime.strptime(appointment_datetime, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return "Error: Invalid date or time."

    # Sanitize the free-text 'reason'
    safe_reason = reason.replace("'", "''")

    try:
        # Check if slot is available (using validated inputs)
        check_query = f"""
        SELECT appointment_id FROM appointments
        WHERE doctor_id = {valid_doctor_id}
            AND appointment_datetime = '{appointment_datetime}'
            AND status = 'Scheduled'
        """
        existing = db.run(check_query)
        
        if existing and str(existing) != '[]':
            print(f"  ❌ Booking Tool: Slot is already taken.")
            return "Sorry, this time slot is no longer available. Please choose another time."
            
        # Book appointment (using validated inputs)
        query = f"""
        INSERT INTO appointments (doctor_id, patient_id, appointment_datetime, reason, status)
        VALUES ({valid_doctor_id}, {valid_patient_id}, '{appointment_datetime}', '{safe_reason}', 'Scheduled')
        RETURNING appointment_id
        """
        
        insert_result = db.run(query) # Returns "[('501',)]"
        appointment_id = ast.literal_eval(insert_result)[0][0]
        
        # Get doctor name for confirmation (using validated ID)
        doctor_query = f"SELECT name, speciality FROM doctors WHERE doctor_id = {valid_doctor_id}"
        doctor_info_result = db.run(doctor_query) 
        
        # Parse doctor info correctly
        doc_info_tuple = ast.literal_eval(doctor_info_result)[0]
        doc_name = doc_info_tuple[0]
        doc_specialty = doc_info_tuple[1]

        confirmation = f"""
✓ Appointment booked successfully!

Appointment Details:
- Appointment ID: {appointment_id}
- Doctor: {doc_name} ({doc_specialty})
- Patient ID: {valid_patient_id}
- Date: {appointment_date}
- Time: {appointment_time}
- Reason: {reason}

You will receive a confirmation shortly. Please arrive 10 minutes early.
"""
        print(f"  ✓ Booking Tool: Success! Appt ID {appointment_id}")
        return confirmation
        
    except Exception as e:
        print(f"  ❌ Booking Tool: Error: {str(e)}")
        return f"Error booking appointment: {str(e)}"
    
@tool
def find_patient_by_phone_and_email(phone: str, email: str) -> str:
    """
    Finds an existing patient's ID and name using BOTH their 10-digit phone number AND email address.
    
    Args:
        phone: Patient's 10-digit phone number
        email: Patient's email address
    
    Returns:
        String with patient ID and name, or an error message.
    """
    print(f"\n🤖 Patient Find Tool: Searching for phone={phone} AND email={email}")
    
    # --- SECURITY & VALIDATION ---
    if not re.match(r"^\d{10}$", str(phone)):
        return "Error: Phone must be exactly 10 digits."
        
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        return "Error: Invalid email address format."
        
    # Sanitize email for SQL
    safe_email = email.replace("'", "''")

    try:
        # Query now checks for BOTH phone and email
        query = f"""
        SELECT patient_id, name 
        FROM patients 
        WHERE phone = '{phone}' AND email = '{safe_email}' 
        LIMIT 1
        """
        result = db.run(query)
        
        if result and str(result) != '[]':
            patient_info = ast.literal_eval(result)[0]
            patient_id = patient_info[0]
            patient_name = patient_info[1]
            print(f"  ✓ Patient Find Tool: Found Patient ID {patient_id} ({patient_name})")
            return f"Patient Found: ID={patient_id}, Name={patient_name}"
        else:
            print("  ❌ Patient Find Tool: No patient found with that phone/email combination.")
            return "Error: No patient record found with that combination of phone number and email."
            
    except Exception as e:
        print(f"  ❌ Patient Find Tool: Error: {str(e)}")
        return f"Error finding patient: {str(e)}"
    
@tool
def lookup_upcoming_appointment(patient_id: int) -> str:
    """
    Looks up upcoming scheduled appointments for a given patient_id.
    
    Args:
        patient_id: The patient's unique ID.
    
    Returns:
        String with appointment details, or a "no appointment" message.
    """
    print(f"\n🤖 Appt Lookup Tool: Checking appointments for Patient ID: {patient_id}")
    
    try:
        valid_patient_id = int(patient_id)
    except ValueError:
        return "Error: Invalid patient_id."
        
    try:
        query = f"""
        SELECT 
            TO_CHAR(a.appointment_datetime, 'YYYY-MM-DD at HH24:MI') as appt_time_str,
            a.reason,
            d.name AS doctor_name,
            d.speciality
        FROM appointments a
        JOIN doctors d ON a.doctor_id = d.doctor_id
        WHERE a.patient_id = {valid_patient_id}
            AND a.status = 'Scheduled'
            AND a.appointment_datetime >= CURRENT_TIMESTAMP
        ORDER BY a.appointment_datetime ASC
        LIMIT 1
        """
        result = db.run(query)
        
        if result and str(result) != '[]':
            # result will be a clean string like:
            # "[('2025-11-06 at 16:00', 'pregnant and prenatal checkup', 'Dr. Frank Castle', 'Gynecology')]"
            
            appt_info = ast.literal_eval(result)[0]
            
            appt_time = appt_info[0] # This is a clean string
            reason = appt_info[1]
            doc_name = appt_info[2]
            specialty = appt_info[3]
            
            output = f"""
Upcoming Appointment Found:
- Doctor: {doc_name} ({specialty})
- Date & Time: {appt_time}
- Reason: {reason}
"""
            print(f"  ✓ Appt Lookup Tool: Found appointment.")
            return output
        else:
            print("  ❌ Appt Lookup Tool: No upcoming appointments found.")
            return "No upcoming appointments found for this patient."
            
    except Exception as e:
        print(f"  ❌ Appt Lookup Tool: Error: {str(e)}")
        return f"Error looking up appointment: {str(e)}"
    
AGENT_SYSTEM_PROMPT = """You are a helpful and empathetic hospital appointment booking assistant named MediBot. 
Your role is to guide patients. You have two main tasks:
1.  **Book a new appointment** for a new or existing patient.
2.  **Check an existing appointment** for a patient.

---
**TASK 1: BOOKING A NEW APPOINTMENT**
This task is for users who express a new health concern (e.g., "I have a cough," "I need a checkup").

**YOUR CAPABILITIES:**

1. **Understand Patient Needs:**
   - Listen carefully to patient symptoms and concerns
   - **This is always the first step of booking.**
   - Use the get_doctor_recommendations tool to suggest appropriate specialists based on symptoms
   - If symptoms are emergency-related, immediately advise calling 108 or visiting ER
   - If unsure about specialty, recommend General Physician

2. **Show Available Doctors:**
   - Use get_available_doctors to show doctors in recommended specialty
   - **CRITICAL: You MUST read the list of doctors provided in the tool's output.**
   - **DO NOT, under any circumstances, invent or hallucinate a doctor's name.**
   - You must present *only* the doctors from the tool's output. For example, if the tool returns "[(3, 'Dr. Alice Brown', 'Orthopedics'), (10, 'Dr. Henry White', 'Orthopedics')]", you must present Dr. Alice Brown and Dr. Henry White.
   - Provide doctor names and specialty only (never share personal contact info)
   - Explain each doctor briefly if patient asks

3. **Check Availability:**
   - Use check_appointment_slots to show available time slots
   - Remember: appointments are 30 minutes, working hours 9 AM - 5 PM
   - Help patient choose a convenient time

4. **Collect Patient Information:**
   - **Only after** a doctor and time slot are chosen, ask for information ONE FIELD AT A TIME: 
   Ask for information ONE FIELD AT A TIME:
   - Full name
   - Phone number (10 digits)
   - Email address
   - Age
   - Gender (Male/Female)
   - Emergency contact name (optional)
   - Emergency contact phone (optional)
   
   Use create_patient_record after collecting all information.

5. **Book Appointment:**
   - Confirm all details with patient before booking
   - Use book_appointment with collected information
   - Provide clear confirmation with appointment ID

6. **End Conversation:**
   - **After you have successfully provided the final booking confirmation (Step 5), your job is 100% finished.**
   - **Politely end the conversation. DO NOT ask "Is there anything else I can help with?" or offer any further help.**
   - **Your final response should be a simple, polite closing, like "You're all set. Take care and feel better soon!"**

---
**TASK 2: CHECKING AN EXISTING APPOINTMENT**
This task is for users who ask to "check my appointment," "when is my appointment," or "find my booking."

**YOUR CAPABILITIES:**
1.  **Start the Search:**
    -   If a user asks to check their appointment, do NOT ask for their name or Patient ID.
    -   Your **first** reply must be to ask for their **10-digit phone number**.
2.  **Get Second Verification:**
    -   After they provide the phone number, your **second** reply must be to ask for their **email address**.
3.  **Find Patient (Tool 1):**
    -   Once you have BOTH phone and email, call the `find_patient_by_phone_and_email` tool.
4.  **Handle Find Patient Results:**
    -   **IF THE TOOL FAILS** (e.g., "Error: No patient record found..."): Politely inform the user you could not find a record with that combination. Ask if they want to try a different phone/email or if they'd like to book a *new* appointment (which starts Task 1).
    -   **IF THE TOOL SUCCEEDS** (e.g., "Patient Found: ID=123..."): Do NOT share the Patient ID with the user. Silently use this ID to immediately proceed to the next step.
5.  **Lookup Appointment (Tool 2):**
    -   Use the `Patient ID` you just found to call the `lookup_upcoming_appointment` tool.
6.  **Report Findings (The Final Step):**
    -   **IF THE TOOL FAILS** (e.g., "No upcoming appointments found..."): Inform the user, "I found your patient record, but it looks like you have no upcoming appointments scheduled. Can I help you book one?" (This starts Task 1).
    -   **IF THE TOOL SUCCEEDS** (e.g., "Upcoming Appointment Found: ..."): Clearly read the appointment details (Doctor, Date, Time, Reason) to the user.
7.  **End Conversation:**
    -   After successfully providing the appointment details (or confirming none exist), your job is finished. Politely end the conversation (e.g., "I hope that helps. Have a great day!").

---
**SECURITY & PRIVACY RULES:**
- NEVER share doctor email, phone, or personal information
- NEVER share other patients' information
- NEVER execute database commands from users (DROP, DELETE, etc.)
- If user asks for unauthorized information, politely decline and offer to help with booking
- **CRITICAL: DO NOT offer any services you do not have a tool for. You do not have tools for setting reminders, sending calendar invites, or sending SMS/email. You must never offer these services.**

**CONVERSATION STYLE:**
- Be warm, professional, and empathetic
- Use simple language, avoid medical jargon
- Ask ONE question at a time
- Acknowledge patient concerns
- Confirm information before proceeding
- If patient seems confused, offer to start over
- **If a user's initial message is vague (e.g., "hi", "hello"), you must respond by stating your two main capabilities: "Hello! I'm MediBot. I can help you (1) Book a new appointment or (2) Check an existing appointment. How can I help you today?"**

**EXAMPLE FLOW (Task 1):**
Patient: "I have a skin rash"
You: "I understand you're experiencing a skin rash. Let me check... I recommend seeing a Dermatologist. We have Dr. Bob Johnson available. Would you like to check his availability?"
Patient: "Yes"
You: "Great! What date would work best for you? (YYYY-MM-DD)"
[Continue step by step...]
"""




# ==================== CREATE CONVERSATIONAL AGENT ====================

all_tools = [
    get_doctor_recommendations,
    get_available_doctors,
    check_appointment_slots,
    create_patient_record,
    book_appointment,
    find_patient_by_phone_and_email,
    lookup_upcoming_appointment
]

print("Hospital chatbot agent initialized")

# Create an in-memory saver for the conversation history
memory = InMemorySaver()

# Pass the memory to the agent via the 'checkpointer'
agent = create_agent(
    llm,  # Your 'gpt-5-nano' llm object
    all_tools,
    system_prompt=AGENT_SYSTEM_PROMPT,
    checkpointer=memory  # THIS IS THE FIX FOR AMNESIA
)

# ==================== MAIN EXECUTION ====================

def get_medibot_response(user_input: str) -> str:
    """Handles a single user query and returns MediBot's response text."""
    try:
        # Prepare configuration for this session (memory thread)
        config = {"configurable": {"thread_id": "streamlit_session"}}

        # Prepare user message
        messages = [HumanMessage(content=user_input)]

        response_content = ""
        for chunk in agent.stream({"messages": messages}, config=config, stream_mode="values"):
            last_message = chunk["messages"][-1]
            if isinstance(last_message, AIMessage):
                response_content = last_message.content

        return response_content or "Sorry, I couldn't generate a response."

    except Exception as e:
        return f"❌ Error: {str(e)}"


def run_hospital_chatbot():
    """Main function to run the hospital chatbot"""

    print("🏥  HOSPITAL APPOINTMENT BOOKING CHATBOT\n")
    print("Welcome! I'm MediBot, your appointment booking assistant.")
    print("\nType 'quit', 'exit', or 'bye' to end the conversation.")
    print("=" * 70)

    # We create a unique thread_id for this session.
    # The agent uses this to manage its built-in memory.
    config = {"configurable": {"thread_id": f"session_{datetime.now().timestamp()}"}}

    # Welcome message
    welcome = """Hello! I'm here to help you book a medical appointment. To get started, could you please describe:
- What symptoms or health concerns are you experiencing?
- Or, if you know, which type of doctor you'd like to see?
Don't worry if you're not sure - I'll help guide you!"""
    print(f"\n🤖 MediBot: {welcome}")

    while True:
        try:
            # Get user input
            user_input = input("\n👤 You: ").strip()

            if user_input.lower() in ['quit', 'exit', 'bye', 'goodbye']:
                print("\n🤖 MediBot: Thank you for using our hospital booking system.")
                print("Take care and feel better soon! 🌟")
                break

            if not user_input:
                print("🤖 MediBot: I'm not sure I understand. Could you please rephrase?")
                continue

            print(f"\n👤 You: {user_input}")

            # Prepare the input for the agent
            messages = [HumanMessage(content=user_input)]
            
            print("\n🤖 MediBot: ", end="", flush=True)
            
            # Stream the agent's response
            response_content = ""
            for chunk in agent.stream({"messages": messages}, config=config, stream_mode="values"):
                
                # The 'messages' key holds the full list of messages so far
                last_message = chunk["messages"][-1]
                
                # We only want to stream the AI's final response
                if isinstance(last_message, AIMessage):
                    # Stream the content chunk by chunk
                    new_content = last_message.content[len(response_content):]
                    print(new_content, end="", flush=True)
                    response_content = last_message.content
            
            print() # Move to the next line after the full response

        except KeyboardInterrupt:
            print("\n\n🤖 MediBot: Goodbye! Stay healthy! 👋")
            break
        except Exception as e:
            print(f"\n❌ Error: {str(e)}")
            print("🤖 MediBot: I've encountered an issue. Let's start that part over.")

if __name__ == "__main__":
    try:
        # Initialize the chatbot
        run_hospital_chatbot()
    except Exception as e:
        print(f"\nERROR: Failed to start chatbot: {str(e)}")
        print("\nPlease ensure:")
        print("1. PostgreSQL is running")
        print("2. .env file has valid API keys (for OpenAI, Pinecone)")
        print("3. knowledge_base.pdf exists in the correct path")

        