import os
import json
import logging
from datetime import datetime
from flask import Flask, request, jsonify
from google.cloud import documentai_v1 as documentai
from google.cloud import storage

# --- CONFIGURATION ---
PROJECT_ID = "591592795300"
LOCATION = "us"
PROCESSOR_ID = "cac498c673d829cf"
BUCKET_NAME = "invoice-project-data"
STATE_FILE = "retrain_status.json"

#Flask app
app = Flask(__name__)

def get_state():
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(STATE_FILE)
        return json.loads(blob.download_as_text())
    except Exception:
        return {"status": "IDLE"}

def save_state(state_dict):
    storage_client = storage.Client()
    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(STATE_FILE)
    blob.upload_from_string(json.dumps(state_dict))

@app.route("/", defaults={'path': ''}, methods=["POST", "GET"])
@app.route("/<path:path>", methods=["POST", "GET"])
def handle_retraining(path):
    #  rout to Cloud Run
    path = path.strip("/")
    client = documentai.DocumentProcessorServiceClient()
    processor_parent = f"projects/{PROJECT_ID}/locations/{LOCATION}/processors/{PROCESSOR_ID}"

    # TRIGGER 
    if path == "trigger":
        state = get_state()
        if state.get("status") == "TRAINING":
            return "Skip: Already training.", 200
        
        ts = datetime.now().strftime("%Y%m%d-%H%M")
        ver_name = f"auto-v-{ts}"
        
        train_req = documentai.TrainProcessorVersionRequest(
            parent=processor_parent,
            processor_version=documentai.ProcessorVersion(display_name=ver_name)
        )
        
        client.train_processor_version(request=train_req)
        save_state({"status": "TRAINING", "version_display_name": ver_name})
        return f"Training started: {ver_name}", 200

    #  CHECK-DEPLOY PATH
    elif path == "check-deploy":
        state = get_state()
        if state.get("status") not in ["TRAINING", "DEPLOYING"]:
            return "No active training or deployment found in GCS.", 200

        for v in client.list_processor_versions(parent=processor_parent):
            if v.display_name == state.get("version_display_name"):
                
                # undeplo
                if v.state == documentai.ProcessorVersion.State.UNDEPLOYED:
                    logging.info(f"Starting deployment for {v.display_name}")
                    client.deploy_processor_version(name=v.name)
                    save_state({"status": "DEPLOYING", "version_display_name": v.display_name})
                    return f"Deployment initiated for {v.display_name}.", 200

                # If deplo,set
                elif v.state == documentai.ProcessorVersion.State.DEPLOYED:
                    logging.info(f"Setting {v.display_name} as default.")
                    
                    #  SetDefaultProcessorVersionRequest 
                    set_default_req = documentai.SetDefaultProcessorVersionRequest(
                        processor=processor_parent,
                        default_processor_version=v.name
                    )
                    client.set_default_processor_version(request=set_default_req)
                    
                    save_state({"status": "COMPLETED", "version_name": v.name})
                    return f"SUCCESS: {v.display_name} is now DEPLOYED and DEFAULT.", 200

                elif v.state == documentai.ProcessorVersion.State.TRAINING:
                    return f"Still training {v.display_name}...", 200

                elif v.state == documentai.ProcessorVersion.State.DEPLOYING:
                    return f"Still deploying {v.display_name}...", 200

        return "Version state transition in progress...", 200

    return "Invalid path. Use /trigger or /check-deploy", 404

if __name__ == "__main__":
    #cr
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))