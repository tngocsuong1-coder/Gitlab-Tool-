import traceback
from flask import Flask, request, jsonify
import requests
from flask_cors import CORS
import os
import time

app = Flask(__name__)
CORS(app)

LOG_FILE = "upload.log"
ERROR_LOG_FILE = "error.log"

def log_error(msg):
    with open(ERROR_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

@app.errorhandler(Exception)
def handle_exception(e):
    # Log stacktrace
    error_msg = f"Exception: {str(e)}\n{traceback.format_exc()}"
    log_error(error_msg)
    # Trả JSON lỗi
    return jsonify({"error": "Internal server error", "details": str(e)}), 500

@app.route("/")
def home():
    return "✅ GitLab Uploader Backend is running."

@app.route("/upload", methods=["POST"])
def upload_files():
    try:
        token = request.form.get("token")
        group_id_str = request.form.get("group_id")
        files = request.files.getlist("files")

        if not token or not group_id_str or not files:
            return jsonify({"error": "Thiếu token, group_id hoặc file upload"}), 400

        try:
            group_id = int(group_id_str)
        except ValueError:
            return jsonify({"error": "group_id phải là số nguyên"}), 400

        # Reset log mỗi lần upload mới
        open(LOG_FILE, "w", encoding="utf-8").close()

        files_sorted = sorted(files, key=lambda f: f.filename)
        created_urls = []
        created_projects = set()

        for index, file in enumerate(files_sorted, start=1):
            original_filename = os.path.basename(file.filename)
            project_name = original_filename.rsplit(".", 1)[0]

            if project_name in created_projects:
                continue
            created_projects.add(project_name)

            project_slug = str(index)

            try:
                content = file.read().decode("utf-8")
            except Exception as e:
                log_error(f"File read error for {project_name}: {e}")
                continue

            create_url = "https://gitlab.com/api/v4/projects"
            headers = {"PRIVATE-TOKEN": token}
            payload = {
                "name": project_name,
                "path": project_slug,
                "namespace_id": group_id,
                "initialize_with_readme": True,
                "visibility": "public"
            }

            try:
                r = requests.post(create_url, headers=headers, json=payload, timeout=15)
                r.raise_for_status()  # Raise HTTPError nếu status code >= 400
                r_json = r.json()
            except requests.RequestException as e:
                log_error(f"GitLab project create failed for {project_name}: {e} - Response: {getattr(e.response, 'text', '')}")
                continue

            project_id = r_json.get("id")
            web_url = r_json.get("web_url")
            if not project_id or not web_url:
                log_error(f"Invalid GitLab response for {project_name}: {r_json}")
                continue

            created_urls.append(web_url)

            with open(LOG_FILE, "a", encoding="utf-8") as logf:
                logf.write(f"{web_url}\n")

            update_url = f"https://gitlab.com/api/v4/projects/{project_id}/repository/files/README.md"
            update_payload = {
                "branch": "main",
                "content": content,
                "commit_message": "Update README.md from uploaded file"
            }

            try:
                r2 = requests.put(update_url, headers=headers, json=update_payload, timeout=15)
                r2.raise_for_status()
            except requests.RequestException as e:
                log_error(f"Update README.md failed for {project_name}: {e} - Response: {getattr(e.response, 'text', '')}")
                continue

        return jsonify(created_urls)

    except Exception as e:
        # Ghi log nếu có lỗi bên ngoài vòng lặp
        error_msg = f"Unhandled exception in upload_files: {str(e)}\n{traceback.format_exc()}"
        log_error(error_msg)
        return jsonify({"error": "Internal server error", "details": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("🚀 Starting Flask server...")
    app.run(debug=False, host="0.0.0.0", port=port)
