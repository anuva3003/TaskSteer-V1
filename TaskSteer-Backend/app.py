import os
import datetime
import json
import re
import traceback # For detailed error logging

from flask import Flask, request, jsonify, session
from flask_cors import CORS
from werkzeug.utils import secure_filename

# Firebase and Google AI Imports
import firebase_admin
from firebase_admin import credentials, auth, firestore
import google.generativeai as genai

# Imports for file handling
import PyPDF2
import docx

print("📁 Current working directory:", os.getcwd())

# === CONFIGURE GEMINI ===
# IMPORTANT: Replace with your actual GOOGLE_API_KEY or load from an environment variable.
GOOGLE_API_KEY = "" # <--- REPLACE THIS
if GOOGLE_API_KEY == "YOUR_GOOGLE_API_KEY":
    print("⚠️ WARNING: Please replace 'YOUR_GOOGLE_API_KEY' with your actual Google API Key for Gemini.")

genai.configure(api_key=GOOGLE_API_KEY)
try:
    model = genai.GenerativeModel("models/gemini-1.5-flash")
    print("✅ Gemini Model initialized successfully.")
except Exception as e:
    print(f"🔥❌❌❌ Gemini Model Initialization Error: {e} ❌❌❌🔥")
    model = None

# === INITIALIZE FIRESTORE ===
db = None
try:
    print("🟡 Trying to initialize Firebase Admin...")
    # This now builds a path to the key file relative to this script's location.
    base_path = os.path.dirname(__file__)
    key_path = os.path.join(base_path, "ServiceAccountKey.json")
    print(f"🔑 Trying to load service account key from: {key_path}")
    cred = credentials.Certificate(key_path)
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("✅ Firebase Admin SDK initialized successfully and Firestore client obtained.")
except Exception as e:
    print(f"❌ Firebase Admin SDK Initialization Error: {e}")
    traceback.print_exc() # Print the full traceback for detailed debugging
    db = None

# === INITIALIZE FLASK APP ===
app = Flask(__name__)
app.secret_key = os.urandom(24) # Required for session management
# This will allow requests from your React app's origin and Live Server to access your backend API routes.
CORS(app, supports_credentials=True, origins=[
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://localhost:5175", 
    "http://127.0.0.1:5175",
    "http://localhost:5500",
    "http://127.0.0.1:5500",
])
print("✅ Flask App initialized with CORS for all routes.")

# === GEMINI TASK EXTRACTOR ===
def extract_tasks_with_gemini(transcript_text_value: str, meeting_date_value: str):
    if not model:
        print("❌ Gemini model not initialized. Cannot extract tasks.")
        return []
    
    # Updated prompt to use Status instead of Priority
    prompt = f"""
You are a hyper-attentive Task Analyst Engine. Your primary function is to process unstructured transcripts and extract tasks with actionable intelligence. You operate under a **Zero-Miss Directive** for finding tasks and a **Full-Context Mandate** for describing them. You MUST identify every commitment, enrich it, and assign a status. You do not explain yourself; you only output the final JSON.

---
### Core Protocol: From Identification to Output

**1. Aggressive Task Identification:**
Find any statement that implies future work. This includes direct commands ("Send me the file"), pledges ("I will do it"), and implied actions.

**2. Contextual Intelligence Gathering (FOR THE `description` FIELD):**
For EVERY task, find the **'why'** behind it by searching the surrounding sentences. A good description answers "Why is this task being done?". If no context exists, use an empty string `""`.

**3. Status Assignment (FOR THE `status` FIELD - CRITICAL RULE):**
You MUST analyze the language of the task assignment to determine its status. Assign ONE of the following values: `High Priority`, `To Do`, `In Progress`, `Review`, or `Completed`.

* **`High Priority`**: Assign this for tasks with words like "urgent," "ASAP," "critical," "immediately," "top priority," or "needs to be done first."
* **`In Progress`**: Assign this if the speaker mentions they have already started the work (e.g., "I'm already working on the slides," "I've started pulling the data").
* **`Review`**: Assign this for tasks that involve checking, approving, or reviewing someone else's work (e.g., "Send me the draft for review," "Can you look this over?").
* **`Completed`**: Assign this only if the speaker explicitly states the task is already finished (e.g., "I've already sent the report," "That's done.").
* **`To Do`**: This is the **default status**. Use it for any standard task that does not meet the criteria for the other statuses.

**4. Data Point Extraction & Formatting:**
For every identified task, you must extract these five data points:

-   **task:** The concise imperative command (e.g., "Draft the Q3 marketing report").
-   **assignee:** The responsible person or team (e.g., "Sarah", "Marketing", "Unassigned").
-   **deadline:** The calculated `YYYY-MM-DD` date. Use `""` if not specified.
-   **description:** The synthesized context you gathered in Step 2.
-   **status:** The status you determined in Step 3.

---
### **Final Output Specification**

**Schema:** A raw JSON array of objects. The output MUST start with `[` and end with `]`.

**Required Keys per object:** `task`, `assignee`, `deadline`, `description`, `status`.

**Example:**

* *Hypothetical Transcript Snippet:* "The client is very unhappy. We need to get this done ASAP. Sara, can you please put together a full RCA and send it to them by EOD tomorrow? John, I've already started the initial draft, can you take it over? And someone needs to review the final marketing copy."
* *Resulting JSON Object:*
```json
[
  {{
    "task": "Create and submit the Root Cause Analysis (RCA) report to the client",
    "assignee": "Sara",
    "deadline": "{datetime.date.today().replace(day=datetime.date.today().day + 1).isoformat()}",
    "description": "To address the client's unhappiness about a recent issue.",
    "status": "High Priority"
  }},
  {{
    "task": "Take over and complete the initial draft",
    "assignee": "John",
    "deadline": "",
    "description": "To continue the work that has already been started.",
    "status": "In Progress"
  }},
  {{
    "task": "Review the final marketing copy",
    "assignee": "Unassigned",
    "deadline": "",
    "description": "To ensure the marketing copy is ready for final use.",
    "status": "Review"
  }}
]
```
---
**Transcript to Analyze:**
{transcript_text_value}
"""
    try:
        response = model.generate_content(prompt)
        data = response.text.strip()
        print(f"🧪 Gemini raw response text:\n{data}")

        match = re.search(r'```json\s*([\s\S]*?)\s*```|(\[[\s\S]*\])', data, re.MULTILINE)
        json_string = None
        if match:
            json_string = match.group(1) or match.group(2)

        if not json_string:
            if data.startswith('[') and data.endswith(']'):
                json_string = data
            else:
                print("❌ No clear JSON array found in Gemini response.")
                return []
        
        print(f"🔬 Attempting to parse extracted JSON string: {json_string}")
        parsed_tasks = json.loads(json_string)
        if not isinstance(parsed_tasks, list):
            print(f"❌ Parsed JSON is not a list: {type(parsed_tasks)}")
            return []
        
        validated_tasks = []
        for t in parsed_tasks:
            if isinstance(t, dict) and "task" in t:
                # Correctly extract all fields, including the new 'status' field
                validated_tasks.append({
                    "task": t.get("task"),
                    "assignee": t.get("assignee", "Unassigned"),
                    "deadline": t.get("deadline", ""),
                    "description": t.get("description", ""),
                    "status": t.get("status", "To Do") 
                })
            else:
                print(f"⚠️ Skipping invalid task structure from Gemini: {t}")
        return validated_tasks

    except json.JSONDecodeError as je:
        print(f"❌ Gemini JSON Decode Error: {je}. Attempted to parse: {json_string if 'json_string' in locals() else data}")
        return []
    except Exception as e:
        print(f"❌ Gemini General Error in extract_tasks_with_gemini: {e}")
        traceback.print_exc()
        return []

# === API ENDPOINTS ===

@app.route("/")
def index():
    return jsonify({"message": "🚀 TaskSteer backend is running."}), 200

@app.route('/login', methods=['POST', 'OPTIONS'])
def login():
    if request.method == "OPTIONS": return '', 204
    try:
        data = request.get_json()
        token = data.get("token")
        if not token: return jsonify({"message": "Error: No token provided"}), 400
        
        decoded_token = auth.verify_id_token(token)
        uid = decoded_token['uid']
        print(f"✅ Token verified for UID: {uid}")
        
        session["user_token"] = token 
        return jsonify({"message": "Login successful", "uid": uid}), 200
    except Exception as e:
        print(f"Error during login: {e}")
        return jsonify({"error": "Invalid token or internal server error"}), 401

@app.route("/suggest-status", methods=["POST", "OPTIONS"])
def suggest_status():
    if request.method == "OPTIONS":
        return '', 204
    if not model:
        return jsonify({"error": "AI model not initialized"}), 500

    try:
        data = request.get_json()
        if not data or "title" not in data:
            return jsonify({"error": "Task title is required."}), 400
        
        task_title = data.get("title")
        task_description = data.get("description", "") # Description is optional

        prompt = f"""
Analyze the following task and suggest the most appropriate status.
Your response must be ONLY ONE of the following exact strings: 'High Priority', 'To Do', 'In Progress', 'Review', or 'Completed'. Do not add any other text or explanation.

Task Title: "{task_title}"
Task Description: "{task_description}"

Based on the content, keywords like 'urgent', 'review', 'already started', or 'finished' should guide your choice. Default to 'To Do' if no other status fits.

Suggested Status:
"""
        response = model.generate_content(prompt)
        suggested_status = response.text.strip()

        # Basic validation to ensure the model returns a valid status
        valid_statuses = ['High Priority', 'To Do', 'In Progress', 'Review', 'Completed']
        if suggested_status not in valid_statuses:
            print(f"⚠️ AI returned an invalid status: '{suggested_status}'. Defaulting to 'To Do'.")
            suggested_status = 'To Do'

        print(f"✅ AI suggested status: {suggested_status}")
        return jsonify({"suggested_status": suggested_status})

    except Exception as e:
        print(f"🔥❌ /suggest-status Error: {e}")
        traceback.print_exc()
        # Return a more specific error message to the frontend
        return jsonify({"error": f"Failed to get AI suggestion: {str(e)}"}), 500


@app.route("/upload", methods=["POST", "OPTIONS"])
def upload_transcript():
    if request.method == "OPTIONS":
        return '', 204
    if not db:
        return jsonify({"message": "❌ Database not initialized. Cannot process upload."}), 500

    if 'file' not in request.files:
        return jsonify({"message": "No file part in the request."}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"message": "No selected file."}), 400

    try:
        print(f"📄 Processing uploaded file: {file.filename}")
        content = ""
        filename = secure_filename(file.filename).lower()

        if filename.endswith('.pdf'):
            pdf_reader = PyPDF2.PdfReader(file.stream)
            for page in pdf_reader.pages:
                content += page.extract_text() or ''
        elif filename.endswith('.docx'):
            doc = docx.Document(file.stream)
            for para in doc.paragraphs:
                content += para.text + "\n"
        elif filename.endswith('.txt'):
            content = file.read().decode("utf-8")
        else:
            return jsonify({"message": f"Unsupported file type: {filename}. Please upload a PDF, DOCX, or TXT file."}), 400
        
        if not content.strip():
            return jsonify({"message": "File is empty or text could not be extracted."}), 400
            
        meeting_date = request.form.get("meeting_date", datetime.date.today().isoformat())
        
        tasks_from_gemini = extract_tasks_with_gemini(content, meeting_date)

        if not tasks_from_gemini:
            return jsonify({"message": "No valid tasks were extracted from the document."}), 200

        action = request.form.get('action')
        if not action:
            return jsonify({"message": "❌ Missing 'action' in form data."}), 400

        timestamp = firestore.SERVER_TIMESTAMP

        def format_status(status_str):
            return status_str.lower().replace(" ", "")

        if action == 'personalTasks':
            batch = db.batch()
            for t_gemini in tasks_from_gemini:
                doc_ref = db.collection("personal_tasks").document()
                batch.set(doc_ref, {
                    "title": t_gemini.get("task", "Untitled Task"),
                    "description": t_gemini.get("description", ""),
                    "assignee": t_gemini.get("assignee", ""),
                    "due_date": t_gemini.get("deadline", ""),
                    "status": format_status(t_gemini.get("status", "To Do")),
                    "deleted": False,
                    "created_at": timestamp,
                    "source": "transcript"
                })
            batch.commit()
            print(f"✅ Added {len(tasks_from_gemini)} task(s) to personal tasks.")
            return jsonify({"message": f"✅ Added {len(tasks_from_gemini)} task(s) to personal tasks."}), 200

        elif action == 'newList' or action == 'existingList':
            list_ref = None
            list_id = None
            list_name = None

            if action == 'newList':
                list_name = request.form.get('new_list_name', f"Tasks from {filename}")
                list_ref = db.collection("shared_lists").document()
                list_ref.set({"name": list_name, "created_at": timestamp, "deleted": False})
                list_id = list_ref.id
            else: # existingList
                list_id = request.form.get("list_id")
                if not list_id: return jsonify({"message": "❌ Missing 'list_id' for existing list."}), 400
                list_ref = db.collection("shared_lists").document(list_id)
                if not list_ref.get().exists: return jsonify({"message": f"❌ List with ID '{list_id}' not found."}), 404
            
            batch = db.batch()
            for t_gemini in tasks_from_gemini:
                task_doc_ref = list_ref.collection("tasks").document()
                batch.set(task_doc_ref, {
                    "title": t_gemini.get("task", "Untitled Task"),
                    "description": t_gemini.get("description", ""),
                    "assignee": t_gemini.get("assignee", ""),
                    "due_date": t_gemini.get("deadline", ""),
                    "status": format_status(t_gemini.get("status", "To Do")),
                    "deleted": False,
                    "created_at": timestamp
                })
            batch.commit()
            
            count = len(tasks_from_gemini)
            if action == 'newList':
                print(f"✅ Created new list '{list_name}' ({list_id}) with {count} task(s).")
                return jsonify({"message": f"✅ Created new list '{list_name}' with {count} task(s).", "new_list_id": list_id}), 200
            else:
                print(f"✅ Added {count} task(s) to existing list ID: {list_id}.")
                return jsonify({"message": f"✅ Added {count} task(s) to the list."}), 200
        else:
            return jsonify({"message": f"❌ Invalid action type: {action}."}), 400

    except Exception as e:
        print(f"🔥❌ /upload Error: {str(e)}")
        traceback.print_exc()
        return jsonify({"message": f"❌ Server error during upload: {str(e)}"}), 500

@app.route("/create-task", methods=["POST", "OPTIONS"])
def create_task():
    if request.method == "OPTIONS": return '', 204
    if not db: return jsonify({"message": "❌ Database not initialized."}), 500

    try:
        data = request.get_json()
        if not data: return jsonify({"message": "❌ No JSON data received."}), 400
        
        task_payload = {
            "title": data.get("task", data.get("title", "Untitled Task")),
            "description": data.get("description", ""),
            "assignee": data.get("assignee", ""),
            "due_date": data.get("deadline", data.get("due_date", "")),
            "status": data.get("status", "todo"),
            "deleted": False,
            "created_at": firestore.SERVER_TIMESTAMP
        }

        task_type = data.get("type")
        if task_type == "personal":
            _ , doc_ref = db.collection("personal_tasks").add(task_payload)
            return jsonify({"message": "✅ Personal task created.", "id": doc_ref.id}), 201
        elif task_type == "shared":
            list_id = data.get("list_id")
            if not list_id: return jsonify({"message": "❌ Missing 'list_id' for shared task."}), 400
            list_ref = db.collection("shared_lists").document(list_id)
            if not list_ref.get().exists: return jsonify({"message": f"❌ Shared list '{list_id}' not found."}), 404
            _ , doc_ref = list_ref.collection("tasks").add(task_payload)
            return jsonify({"message": "✅ Shared task created.", "id": doc_ref.id}), 201
        else:
            return jsonify({"message": f"❌ Invalid task type: {task_type}."}), 400

    except Exception as e:
        print(f"🔥❌ /create-task Error: {e}"); traceback.print_exc()
        return jsonify({"error": "Failed to create task.", "details": str(e)}), 500

@app.route("/tasks", methods=["GET", "OPTIONS"])
def get_tasks():
    print("🔥 /tasks route was hit")
    if request.method == "OPTIONS": 
        return '', 204
    
    if db is None: 
        print("❌ Firestore DB is not initialized")
        return jsonify({"error": "Firestore DB not initialized"}), 500

    try:
        personal_tasks_data = []
        p_query = db.collection("personal_tasks").where(filter=firestore.FieldFilter("deleted", "==", False))
        for doc in p_query.stream():
            task = doc.to_dict()
            task["id"] = doc.id
            personal_tasks_data.append(task)
        print(f"✅ Retrieved {len(personal_tasks_data)} personal tasks.")

        shared_lists_data = []
        s_query = db.collection("shared_lists").where(filter=firestore.FieldFilter("deleted", "==", False))
        for list_doc in s_query.stream():
            list_data = list_doc.to_dict()
            list_id = list_doc.id
            list_data["id"] = list_id
            list_data["tasks"] = []

            tasks_query = db.collection("shared_lists").document(list_id).collection("tasks").where(filter=firestore.FieldFilter("deleted", "==", False))
            for task_doc in tasks_query.stream():
                task_data = task_doc.to_dict()
                task_data["id"] = task_doc.id
                list_data["tasks"].append(task_data)
            
            shared_lists_data.append(list_data)
        print(f"✅ Retrieved {len(shared_lists_data)} shared lists.")

        return jsonify({"personal_tasks": personal_tasks_data, "shared_lists": shared_lists_data}), 200

    except Exception as e:
        print(f"🔥 Error inside /tasks route: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/create-list", methods=["POST", "OPTIONS"])
def create_list():
    if request.method == "OPTIONS": return '', 204
    if not db: return jsonify({"message": "❌ Database not initialized."}), 500
    try:
        data = request.get_json()
        if not data or not data.get("name"):
            return jsonify({"message": "❌ List name is required."}), 400
        
        list_name = data["name"]
        payload = {"name": list_name, "created_at": firestore.SERVER_TIMESTAMP, "deleted": False}
        update_time, list_ref = db.collection("shared_lists").add(payload)
        
        created_list_data = payload.copy()
        created_list_data["id"] = list_ref.id
        created_list_data["created_at"] = update_time.isoformat()

        print(f"✅ Shared list '{list_name}' created with ID: {list_ref.id}")
        return jsonify({"message": f"✅ List '{list_name}' created.", "list": created_list_data}), 201

    except Exception as e:
        print(f"🔥❌ /create-list Error: {e}"); traceback.print_exc()
        return jsonify({"error": "Failed to create list.", "details": str(e)}), 500


@app.route("/join-list", methods=["POST", "OPTIONS"])
def join_shared_list():
    if request.method == "OPTIONS": return '', 204
    data = request.get_json()
    list_id = data.get("list_id")
    user_email = data.get("user_email")

    if not all([list_id, user_email]):
        return jsonify({"error": "Missing list_id or user_email"}), 400

    try:
        # Update Firestore to add the user to the list's `members`
        list_ref = db.collection("shared_lists").document(list_id)
        list_ref.update({
            "members": firestore.ArrayUnion([user_email])
        })
        return jsonify({"message": f"✅ {user_email} added to list {list_id}."})
    except Exception as e:
        print("❌ Error joining list:", e)
        return jsonify({"error": str(e)}), 500

def update_task_generic(ref, data):
    updates = {}
    if "title" in data: updates["title"] = data["title"]
    if "description" in data: updates["description"] = data["description"]
    if "due_date" in data: updates["due_date"] = data["due_date"]
    if "status" in data: updates["status"] = data["status"]
    if "assignee" in data: updates["assignee"] = data["assignee"]
    
    if not updates: return jsonify({"message": "No update fields provided"}), 400
    
    updates["updated_at"] = firestore.SERVER_TIMESTAMP
    ref.update(updates)
    return jsonify({"message": f"✅ Task updated."}), 200

@app.route("/update-personal-task/<task_id>", methods=["PUT", "OPTIONS"])
def update_personal_task(task_id):
    if request.method == "OPTIONS": return '', 204
    if not db: return jsonify({"message": "❌ DB not initialized."}), 500
    try:
        ref = db.collection("personal_tasks").document(task_id)
        if not ref.get().exists: return jsonify({"message": "Task not found"}), 404
        return update_task_generic(ref, request.get_json())
    except Exception as e:
        print(f"🔥❌ /update-personal-task Error: {e}"); traceback.print_exc()
        return jsonify({"error": "Failed to update task.", "details": str(e)}), 500

@app.route("/update-shared-task/<list_id>/<task_id>", methods=["PUT", "OPTIONS"])
def update_shared_task(list_id, task_id):
    if request.method == "OPTIONS": return '', 204
    if not db: return jsonify({"message": "❌ DB not initialized."}), 500
    try:
        ref = db.collection("shared_lists").document(list_id).collection("tasks").document(task_id)
        if not ref.get().exists: return jsonify({"message": "Task not found"}), 404
        return update_task_generic(ref, request.get_json())
    except Exception as e:
        print(f"🔥❌ /update-shared-task Error: {e}"); traceback.print_exc()
        return jsonify({"error": "Failed to update task.", "details": str(e)}), 500

def delete_task_generic(ref):
    if not ref.get().exists: return jsonify({"message": "Task not found"}), 404
    ref.update({"deleted": True, "deleted_at": firestore.SERVER_TIMESTAMP})
    return jsonify({"message": f"✅ Task deleted."}), 200

@app.route("/delete-personal-task/<task_id>", methods=["DELETE", "OPTIONS"])
def delete_personal_task(task_id):
    if request.method == "OPTIONS": return '', 204
    if not db: return jsonify({"message": "❌ DB not initialized."}), 500
    try:
        ref = db.collection("personal_tasks").document(task_id)
        return delete_task_generic(ref)
    except Exception as e:
        print(f"🔥❌ /delete-personal-task Error: {e}"); traceback.print_exc()
        return jsonify({"error": "Failed to delete task.", "details": str(e)}), 500

@app.route("/delete-shared-task/<list_id>/<task_id>", methods=["DELETE", "OPTIONS"])
def delete_shared_task(list_id, task_id):
    if request.method == "OPTIONS": return '', 204
    if not db: return jsonify({"message": "❌ DB not initialized."}), 500
    try:
        ref = db.collection("shared_lists").document(list_id).collection("tasks").document(task_id)
        return delete_task_generic(ref)
    except Exception as e:
        print(f"🔥❌ /delete-shared-task Error: {e}"); traceback.print_exc()
        return jsonify({"error": "Failed to delete task.", "details": str(e)}), 500

@app.route("/delete-list/<list_id>", methods=["DELETE", "OPTIONS"])
def delete_list(list_id):
    if request.method == "OPTIONS": return '', 204
    if not db: return jsonify({"message": "❌ DB not initialized."}), 500
    try:
        list_ref = db.collection("shared_lists").document(list_id)
        if not list_ref.get().exists: return jsonify({"message": "List not found"}), 404
        list_ref.update({"deleted": True, "deleted_at": firestore.SERVER_TIMESTAMP})
        return jsonify({"message": f"✅ List deleted."}), 200
    except Exception as e:
        print(f"🔥❌ /delete-list Error: {e}"); traceback.print_exc()
        return jsonify({"error": "Failed to delete list.", "details": str(e)}), 500

# === RUN SERVER ===
if __name__ == "__main__":
    print("🚀 Starting Flask server...")
    # Use 0.0.0.0 to make the server accessible on your local network
    app.run(host="0.0.0.0", port=8080, debug=True)
