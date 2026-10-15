import os
import logging
import requests
import google.auth
import google.auth.transport.requests
from datetime import datetime, timezone
from flask import Flask, jsonify, request
from google.cloud import storage

# Configuration
PROJECT_ID = "gci-techss-gcp-pjnp-01nl165115"
LOCATION = "us"
PROCESSOR_ID = "cac498c673d829cf" 
ERROR_BUCKET = "invoice-processing-errors"

app = Flask(__name__)
storage_client = storage.Client()

def get_session():
    creds, _ = google.auth.default()
    auth_req = google.auth.transport.requests.Request()
    creds.refresh(auth_req)
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {creds.token}", 
        "Content-Type": "application/json"
    })
    return session

def _move_to_safe_folder(bucket_name, blob_name):
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    if not blob.exists():
        return None
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    new_name = f"workbench_imports/{ts}_{blob_name.split('/')[-1]}"
    bucket.copy_blob(blob, storage_client.bucket(ERROR_BUCKET), new_name)
    blob.delete() 
    return f"gs://{ERROR_BUCKET}/{new_name}"

@app.route("/", methods=["POST"])
def handle_reprocessor():
    body = request.get_json(silent=True) or {}
    data = body.get("data", body) 
    bucket_name = data.get("bucket")
    blob_name = data.get("name")

    if not blob_name or "workbench_imports" in blob_name:
        return jsonify({"status": "SKIP"}), 200

    try:
        review_uri = _move_to_safe_folder(bucket_name, blob_name)
        if not review_uri:
            return jsonify({"status": "MISSING"}), 200
        
        url = f"https://{LOCATION}-documentai.googleapis.com/v1beta3/projects/{PROJECT_ID}/locations/{LOCATION}/processors/{PROCESSOR_ID}/dataset:importDocuments"
        
        # SCHEMA: Targeted specifically for Classifier Workbench Training
        payload = {
            "batch_documents_import_configs": [
                {
                    "dataset_split": "DATASET_SPLIT_TRAIN", # Explicitly move to training
                    "batch_input_config": {
                        "gcs_documents": {
                            "documents": [{"gcs_uri": review_uri, "mime_type": "application/pdf"}]
                        }
                    }
                }
            ]
        }

        session = get_session()
        response = session.post(url, json=payload)
        
        # Forced logging for Cloud Run console visibility
        print(f"IMPORT_ATTEMPT: {blob_name} | STATUS: {response.status_code} | RESPONSE: {response.text}")
        
        return jsonify({"status": "PROCESSED", "api_code": response.status_code}), 200

    except Exception as e:
        print(f"ERROR: {str(e)}")
        return jsonify({"status": "ERROR"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))