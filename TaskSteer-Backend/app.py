import os
import datetime
import json
import re
import traceback # For detailed error logging

from flask import Flask, request, jsonify
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
# IMPORTANT: It's best practice to load secrets from environment variables, not hardcode them.
# Example: GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
GOOGLE_API_KEY = "" # <--- REPLACE THIS or load from environment
if GOOGLE_API_KEY == "YOUR_GOOGLE_API_KEY":
    print("⚠️ WARNING: Please replace 'YOUR_GOOGLE_API_KEY' with your actual Google API Key for Gemini.")

try:
    genai.configure(api_key=GOOGLE_API_KEY)
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
    # Ensure 'ServiceAccountKey.json' is in the same directory as this script.
    base_path = os.path.dirname(os.path.abspath(__file__))
    key_path = os.path.join(base_path, "ServiceAccountKey.json")
    print(f"🔑 Trying to load service account key from: {key_path}")
    if os.path.exists(key_path):
        cred = credentials.Certificate(key_path)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("✅ Firebase Admin SDK initialized successfully and Firestore client obtained.")
    else:
        print(f"❌ ServiceAccountKey.json not found at path: {key_path}")
        db = None
except Exception as e:
    print(f"❌ Firebase Admin SDK Initialization Error: {e}")
    traceback.print_exc() # Print the full traceback for detailed debugging
    db = None

# === INITIALIZE FLASK APP ===
app = Flask(__name__)
# This CORS configuration allows requests from both Vite and Live Server.
CORS(app, resources={r"/*": {"origins": [
    "http://localhost:5173",   # Vite dev server
    "http://127.0.0.1:5500"    # Live Server
]}}, supports_credentials=True)
print("✅ Flask App initialized with CORS for all routes.")


# === AUTHENTICATION DECORATOR (NEW AND IMPORTANT!) ===
from functools import wraps

def check_token(f):
    @wraps(f)
    def wrap(*args,**kwargs):
        # Allow OPTIONS requests to pass through for CORS preflight
        if request.method == "OPTIONS":
            return jsonify({'message': 'CORS preflight successful'}), 204

        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'message': 'Missing or invalid authorization token'}), 401
        
        id_token = auth_header.split('Bearer ')[1]
        try:
            decoded_token = auth.verify_id_token(id_token)
            # Add user info to the request context for use in the endpoint
            request.user = decoded_token
        except auth.InvalidIdTokenError:
            return jsonify({'message': 'Invalid ID token'}), 401
        except Exception as e:
            print(f"🔥❌ Token verification error: {e}")
            return jsonify({'message': 'Could not verify token'}), 401
        
        return f(*args, **kwargs)
    return wrap

# === GEMINI TASK EXTRACTOR (UPDATED) ===
def extract_tasks_with_gemini(transcript_text_value: str, meeting_date_value: str):
    if not model:
        print("❌ Gemini model not initialized. Cannot extract tasks.")
        return []
    
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

---
**Transcript to Analyze:**
{transcript_text_value}
"""
    try:
        response = model.generate_content(prompt)
        # Convert the response to a dictionary to handle the new parsing logic
        gemini_response = json.loads(response.text)
        
        # ✅ FIX: Use the new, more robust parsing function.
        parsed_tasks = []
        for item in gemini_response.get("candidates", []):
            try:
                content = item["content"]["parts"][0]["text"]
                # Clean up the content string before parsing
                clean_content = content.strip().replace('```json', '').replace('```', '')
                task_list = json.loads(clean_content) if isinstance(clean_content, str) else clean_content
            except Exception as e:
                print("❌ Failed to parse Gemini content:", e)
                continue

            for task in task_list:
                parsed_tasks.append({
                    "title": task.get("task") or task.get("title") or "Untitled Task",
                    "description": task.get("description") or "No description provided.",
                    "due_date": task.get("deadline") or task.get("due_date") or None,
                    "assignee": task.get("assignee") or None,
                    "status": task.get("status", "To Do") # Keep status parsing
                })
        
        return parsed_tasks

    except json.JSONDecodeError as je:
        print(f"❌ Gemini JSON Decode Error: {je}. Attempted to parse: {response.text}")
        return []
    except Exception as e:
        print(f"❌ Gemini General Error in extract_tasks_with_gemini: {e}")
        traceback.print_exc()
        return []

# === API ENDPOINTS (NOW SECURED) ===

@app.route("/")
def index():
    return jsonify({"message": "🚀 TaskSteer backend is running."}), 200

# This route handles CORS preflight for the login flow.
@app.route('/login', methods=['POST', 'OPTIONS'])
def login():
    if request.method == 'OPTIONS':
        return jsonify({'message': 'CORS preflight successful'}), 200
    
    return jsonify({
        "message": "Login endpoint reached. Please use Firebase Auth on the frontend to get an ID token and send it as a 'Bearer' token to other API routes."
    }), 200


@app.route("/suggest-status", methods=["POST", "OPTIONS"])
@check_token
def suggest_status():
    if not model:
        return jsonify({"error": "AI model not initialized"}), 500

    try:
        data = request.get_json()
        if not data or "title" not in data:
            return jsonify({"error": "Task title is required."}), 400
        
        task_title = data.get("title")
        task_description = data.get("description", "")

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

        valid_statuses = ['High Priority', 'To Do', 'In Progress', 'Review', 'Completed']
        if suggested_status not in valid_statuses:
            print(f"⚠️ AI returned an invalid status: '{suggested_status}'. Defaulting to 'To Do'.")
            suggested_status = 'To Do'

        print(f"✅ AI suggested status for user {request.user['uid']}: {suggested_status}")
        return jsonify({"suggested_status": suggested_status})

    except Exception as e:
        print(f"🔥❌ /suggest-status Error: {e}"); traceback.print_exc()
        return jsonify({"error": f"Failed to get AI suggestion: {str(e)}"}), 500

# === HELPER FUNCTION FOR UPLOAD ROUTE ===
def normalize_assignee(raw_assignee, current_user_email):
    """
    More robustly matches a raw assignee name to the current user's email.
    If the raw name is a part of the user's email prefix (or vice versa),
    it returns the full email.
    """
    if not raw_assignee or not current_user_email:
        return raw_assignee

    assignee_lower = raw_assignee.strip().lower()
    user_name_part = current_user_email.split("@")[0].lower()

    if user_name_part in assignee_lower or assignee_lower in user_name_part:
        return current_user_email

    return raw_assignee

@app.route("/upload", methods=["POST", "OPTIONS"])
@check_token
def upload_transcript():
    print(f"🔥 /upload endpoint hit by user: {request.user['uid']}")
    if not db:
        return jsonify({"message": "❌ Database not initialized. Cannot process upload."}), 500

    if 'file' not in request.files:
        return jsonify({"message": "No file part in the request."}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"message": "No selected file."}), 400

    try:
        content = ""
        filename = secure_filename(file.filename).lower()

        if filename.endswith('.pdf'):
            pdf_reader = PyPDF2.PdfReader(file.stream)
            for page in pdf_reader.pages: content += page.extract_text() or ''
        elif filename.endswith('.docx'):
            doc = docx.Document(file.stream)
            for para in doc.paragraphs: content += para.text + "\n"
        elif filename.endswith('.txt'):
            content = file.read().decode("utf-8")
        else:
            return jsonify({"message": f"Unsupported file type: {filename}."}), 400
        
        if not content.strip():
            return jsonify({"message": "File is empty or text could not be extracted."}), 400
            
        meeting_date = request.form.get("meeting_date", datetime.date.today().isoformat())
        
        print("🧠 Sending to Gemini for task extraction...")
        tasks_from_gemini = extract_tasks_with_gemini(content, meeting_date)

        if not tasks_from_gemini:
            return jsonify({"message": "No valid tasks were extracted from the document."}), 200
        else:
            print(f"✅ Extracted {len(tasks_from_gemini)} tasks:", tasks_from_gemini)

        action = request.form.get('action')
        if not action: return jsonify({"message": "❌ Missing 'action' in form data."}), 400

        timestamp = firestore.SERVER_TIMESTAMP
        user_id = request.user["uid"]
        user_email = request.user.get("email", user_id)

        def format_status(status_str):
            return status_str.lower().replace(" ", "")

        if action == 'personalTasks':
            batch = db.batch()
            user_tasks_collection = db.collection("users").document(user_id).collection("personal_tasks")
            for t_gemini in tasks_from_gemini:
                doc_ref = user_tasks_collection.document()
                batch.set(doc_ref, {
                    "title": t_gemini.get("title", "Untitled Task"),
                    "description": t_gemini.get("description", ""),
                    "assignee": user_email, # Personal tasks are always assigned to the current user
                    "due_date": t_gemini.get("due_date", ""),
                    "status": format_status(t_gemini.get("status", "To Do")),
                    "deleted": False,
                    "created_at": timestamp,
                    "source": "transcript"
                })
            batch.commit()
            print(f"✅ Added {len(tasks_from_gemini)} task(s) to personal tasks for user {user_id}.")
            return jsonify({"message": f"✅ Added {len(tasks_from_gemini)} task(s) to your personal tasks."}), 200

        elif action == 'newList' or action == 'existingList':
            list_ref = None
            list_id = None
            list_name = None

            if action == 'newList':
                list_name = request.form.get('new_list_name', f"Tasks from {filename}")
                list_ref = db.collection("shared_lists").document()
                list_ref.set({
                    "name": list_name, 
                    "created_at": timestamp, 
                    "deleted": False,
                    "owner_id": user_id,
                    "members": [user_email], 
                    "pending_invites": []
                })
                list_id = list_ref.id
            else: # existingList
                list_id = request.form.get("list_id")
                if not list_id: return jsonify({"message": "❌ Missing 'list_id' for existing list."}), 400
                list_ref = db.collection("shared_lists").document(list_id)
                list_doc = list_ref.get()
                if not list_doc.exists: return jsonify({"message": f"❌ List with ID '{list_id}' not found."}), 404
                list_data = list_doc.to_dict()
                list_name = list_data.get("name", "Untitled List")
                if user_email not in list_data.get("members", []):
                    return jsonify({"message": "You are not a member of this list."}), 403
            
            batch = db.batch()
            for t_gemini in tasks_from_gemini:
                task_doc_ref = list_ref.collection("tasks").document()
                
                normalized_assignee = normalize_assignee(t_gemini.get("assignee", ""), user_email)
                
                batch.set(task_doc_ref, {
                    "title": t_gemini.get("title", "Untitled Task"),
                    "description": t_gemini.get("description", ""),
                    "assignee": normalized_assignee, 
                    "due_date": t_gemini.get("due_date", ""),
                    "status": format_status(t_gemini.get("status", "To Do")),
                    "deleted": False,
                    "created_at": timestamp,
                    "source": "transcript",
                    "list_id": list_id,
                    "list_name": list_name
                })
            batch.commit()
            
            count = len(tasks_from_gemini)
            if action == 'newList':
                print(f"✅ User {user_id} created new list '{list_name}' ({list_id}) with {count} task(s).")
                return jsonify({"message": f"✅ Created new list '{list_name}' with {count} task(s).", "new_list_id": list_id}), 200
            else:
                print(f"✅ User {user_id} added {count} task(s) to existing list ID: {list_id}.")
                return jsonify({"message": f"✅ Added {count} task(s) to the list."}), 200
        else:
            return jsonify({"message": f"❌ Invalid action type: {action}."}), 400

    except Exception as e:
        print(f"🔥❌ /upload Error: {str(e)}"); traceback.print_exc()
        return jsonify({"message": f"❌ Server error during upload: {str(e)}"}), 500

@app.route("/tasks", methods=["GET", "OPTIONS"])
@check_token
def get_tasks():
    if not db: return jsonify({"error": "Database not initialized"}), 500
    
    try:
        user_id = request.user["uid"]
        user_email = request.user.get("email", user_id)
        print(f"Fetching tasks for user_id: {user_id}, email: {user_email}")

        # Fetch personal tasks (implicitly assigned to the user)
        personal_tasks_query = db.collection("users").document(user_id).collection("personal_tasks").where("deleted", "==", False)
        personal_tasks_list = [doc.to_dict() | {"id": doc.id} for doc in personal_tasks_query.stream()]

        # Fetch shared lists where the user is a member
        shared_lists_query = db.collection("shared_lists").where("members", "array_contains", user_email).where("deleted", "==", False)
        shared_tasks_list = []

        for list_doc in shared_lists_query.stream():
            list_id = list_doc.id
            
            # Query for tasks within that list assigned to the user
            tasks_ref = db.collection('shared_lists').document(list_id).collection('tasks')
            # Note: Firestore field for assignee is 'assignee', not 'assignedTo'
            assigned_tasks_query = tasks_ref.where('assignee', '==', user_email).where("deleted", "==", False)

            for task_doc in assigned_tasks_query.stream():
                task_data = task_doc.to_dict()
                task_data['id'] = task_doc.id
                shared_tasks_list.append(task_data)

        # Combine personal and assigned shared tasks into a single flat list
        all_tasks = personal_tasks_list + shared_tasks_list
        
        # Return a raw list as requested by the user's snippet
        return jsonify(all_tasks)

    except Exception as e:
        print(f"🔥❌ Error inside /tasks route: {e}"); traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/create-list", methods=["POST", "OPTIONS"])
@check_token
def create_list():
    if not db: return jsonify({"message": "❌ Database not initialized."}), 500
    try:
        data = request.get_json()
        if not data or not data.get("name"):
            return jsonify({"message": "❌ List name is required."}), 400
        
        user_id = request.user["uid"]
        user_email = request.user.get("email", user_id)
        list_name = data["name"]

        payload = {
            "name": list_name, 
            "created_at": firestore.SERVER_TIMESTAMP, 
            "deleted": False,
            "owner_id": user_id,
            "members": [user_email],
            "pending_invites": []
        }
        update_time, list_ref = db.collection("shared_lists").add(payload)
        
        created_list_data = payload.copy()
        created_list_data["id"] = list_ref.id
        created_list_data["created_at"] = update_time.isoformat()

        print(f"✅ User {user_id} created shared list '{list_name}' with ID: {list_ref.id}")
        return jsonify({"message": f"✅ List '{list_name}' created.", "list": created_list_data}), 201

    except Exception as e:
        print(f"🔥❌ /create-list Error: {e}"); traceback.print_exc()
        return jsonify({"error": "Failed to create list.", "details": str(e)}), 500

@app.route("/invite", methods=["POST", "OPTIONS"])
@check_token
def invite_user_to_list():
    if not db: return jsonify({"error": "Database not initialized"}), 500
    
    data = request.get_json()
    list_id = data.get("listId")
    invitee_email = data.get("email", "").strip().lower()

    if not list_id or not invitee_email:
        return jsonify({"error": "listId and email are required"}), 400

    user_email = request.user.get("email")

    list_ref = db.collection("shared_lists").document(list_id)
    list_doc = list_ref.get()

    if not list_doc.exists:
        return jsonify({"error": "List not found"}), 404

    list_data = list_doc.to_dict()
    members = list_data.get("members", [])
    
    if user_email not in members:
        return jsonify({"error": "You must be a member of this list to invite others."}), 403

    if invitee_email in members:
        return jsonify({"message": "User is already a member of this list."}), 200

    list_ref.update({"pending_invites": firestore.ArrayUnion([invitee_email])})

    return jsonify({"message": f"Successfully sent an invitation to {invitee_email} for list '{list_data.get('name', list_id)}'"}), 200

@app.route("/invites", methods=["GET", "OPTIONS"])
@check_token
def get_invites():
    if not db: return jsonify({"error": "Database not initialized"}), 500
    
    user_email = request.user.get("email")
    if not user_email:
        return jsonify({"error": "User email not found in token."}), 400

    invites = []
    query = db.collection("shared_lists").where("pending_invites", "array_contains", user_email).where("deleted", "==", False)
    
    try:
        docs = query.stream()
        for doc in docs:
            data = doc.to_dict()
            invites.append({
                "list_id": doc.id,
                "name": data.get("name", "Untitled List"),
                "owner_id": data.get("owner_id")
            })
        return jsonify({"invites": invites}), 200
    except Exception as e:
        print(f"🔥❌ /invites Error: {e}"); traceback.print_exc()
        return jsonify({"error": "Failed to retrieve invitations.", "details": str(e)}), 500


@app.route('/accept-invite', methods=['POST', 'OPTIONS'])
@check_token
def accept_invite():
    if not db: return jsonify({"error": "Database not initialized"}), 500
    
    data = request.get_json()
    list_id = data.get('listId')
    user_email = request.user.get('email')

    if not list_id or not user_email:
        return jsonify({'error': 'Missing listId or user email from token'}), 400

    list_ref = db.collection('shared_lists').document(list_id)
    list_doc = list_ref.get()

    if not list_doc.exists:
        return jsonify({'error': 'List not found'}), 404
    
    list_data = list_doc.to_dict()
    if user_email not in list_data.get("pending_invites", []):
        return jsonify({"error": "No pending invitation found for this list."}), 403

    list_ref.update({
        "pending_invites": firestore.ArrayRemove([user_email]),
        "members": firestore.ArrayUnion([user_email])
    })

    return jsonify({'message': 'Successfully joined the shared list'}), 200

@app.route("/create-task", methods=["POST", "OPTIONS"])
@check_token
def create_task():
    if not db: return jsonify({"message": "❌ Database not initialized."}), 500

    try:
        data = request.get_json()
        if not data: return jsonify({"message": "❌ No JSON data received."}), 400
        
        user_id = request.user["uid"]
        user_email = request.user.get("email", user_id)

        task_payload = {
            "title": data.get("title", "Untitled Task"),
            "description": data.get("description", ""),
            "assignee": data.get("assignee", ""),
            "due_date": data.get("due_date", ""),
            "status": data.get("status", "todo"),
            "deleted": False,
            "created_at": firestore.SERVER_TIMESTAMP
        }

        task_type = data.get("type")
        if task_type == "personal":
            ref = db.collection("users").document(user_id).collection("personal_tasks")
            _ , doc_ref = ref.add(task_payload)
            return jsonify({"message": "✅ Personal task created.", "id": doc_ref.id}), 201
        
        elif task_type == "shared":
            list_id = data.get("list_id")
            if not list_id: return jsonify({"message": "❌ Missing 'list_id' for shared task."}), 400
            
            list_ref = db.collection("shared_lists").document(list_id)
            list_doc = list_ref.get()
            if not list_doc.exists: return jsonify({"message": f"❌ Shared list '{list_id}' not found."}), 404
            
            if user_email not in list_doc.to_dict().get("members", []):
                return jsonify({"message": "You are not authorized to add tasks to this list."}), 403

            _ , doc_ref = list_ref.collection("tasks").add(task_payload)
            return jsonify({"message": "✅ Shared task created.", "id": doc_ref.id}), 201
        else:
            return jsonify({"message": f"❌ Invalid task type: {task_type}."}), 400

    except Exception as e:
        print(f"🔥❌ /create-task Error: {e}"); traceback.print_exc()
        return jsonify({"error": "Failed to create task.", "details": str(e)}), 500

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
@check_token
def update_personal_task(task_id):
    if not db: return jsonify({"message": "❌ DB not initialized."}), 500
    try:
        user_id = request.user["uid"]
        ref = db.collection("users").document(user_id).collection("personal_tasks").document(task_id)
        if not ref.get().exists: return jsonify({"message": "Task not found"}), 404
        return update_task_generic(ref, request.get_json())
    except Exception as e:
        print(f"🔥❌ /update-personal-task Error: {e}"); traceback.print_exc()
        return jsonify({"error": "Failed to update task.", "details": str(e)}), 500

@app.route("/update-shared-task/<list_id>/<task_id>", methods=["PUT", "OPTIONS"])
@check_token
def update_shared_task(list_id, task_id):
    if not db: return jsonify({"message": "❌ DB not initialized."}), 500
    try:
        user_email = request.user.get("email")
        list_ref = db.collection("shared_lists").document(list_id)
        list_doc = list_ref.get()

        if not list_doc.exists: return jsonify({"message": "List not found"}), 404
        if user_email not in list_doc.to_dict().get("members", []):
            return jsonify({"message": "You are not authorized to modify tasks in this list."}), 403

        ref = list_ref.collection("tasks").document(task_id)
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
@check_token
def delete_personal_task(task_id):
    if not db: return jsonify({"message": "❌ DB not initialized."}), 500
    try:
        user_id = request.user["uid"]
        ref = db.collection("users").document(user_id).collection("personal_tasks").document(task_id)
        return delete_task_generic(ref)
    except Exception as e:
        print(f"🔥❌ /delete-personal-task Error: {e}"); traceback.print_exc()
        return jsonify({"error": "Failed to delete task.", "details": str(e)}), 500

@app.route("/delete-shared-task/<list_id>/<task_id>", methods=["DELETE", "OPTIONS"])
@check_token
def delete_shared_task(list_id, task_id):
    if not db: return jsonify({"message": "❌ DB not initialized."}), 500
    try:
        user_email = request.user.get("email")
        list_ref = db.collection("shared_lists").document(list_id)
        list_doc = list_ref.get()

        if not list_doc.exists: return jsonify({"message": "List not found"}), 404
        if user_email not in list_doc.to_dict().get("members", []):
            return jsonify({"message": "You are not authorized to delete tasks in this list."}), 403
        
        ref = list_ref.collection("tasks").document(task_id)
        return delete_task_generic(ref)
    except Exception as e:
        print(f"🔥❌ /delete-shared-task Error: {e}"); traceback.print_exc()
        return jsonify({"error": "Failed to delete task.", "details": str(e)}), 500

@app.route("/delete-list/<list_id>", methods=["DELETE", "OPTIONS"])
@check_token
def delete_list(list_id):
    if not db: return jsonify({"message": "❌ DB not initialized."}), 500
    try:
        user_id = request.user["uid"]
        list_ref = db.collection("shared_lists").document(list_id)
        list_doc = list_ref.get()
        if not list_doc.exists: return jsonify({"message": "List not found"}), 404
        
        if list_doc.to_dict().get("owner_id") != user_id:
            return jsonify({"message": "Only the list owner can delete this list."}), 403

        list_ref.update({"deleted": True, "deleted_at": firestore.SERVER_TIMESTAMP})
        return jsonify({"message": f"✅ List deleted."}), 200
    except Exception as e:
        print(f"🔥❌ /delete-list Error: {e}"); traceback.print_exc()
        return jsonify({"error": "Failed to delete list.", "details": str(e)}), 500

# === RUN SERVER ===
if __name__ == "__main__":
    print("🚀 Starting Flask server...")
    # Use 0.0.0.0 to make the server accessible on your local network
    # Set debug=False for production
    app.run(host="0.0.0.0", port=8080, debug=True)
