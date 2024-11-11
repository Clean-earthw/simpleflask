
import os
import base64
import json
import pathlib
from flask import Flask, request, Response, abort, render_template, jsonify,send_file,session,redirect
from flask_cors import CORS
from google_auth_oauthlib.flow import Flow
from google.oauth2 import id_token
import google.auth.transport.requests
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from pip._vendor import cachecontrol
import requests
import google.generativeai as genai
from dotenv import load_dotenv

GENAI_SCOPE = ['https://www.googleapis.com/auth/generative-language.retriever']

#if os.path.exists('token.json'):
        #creds = Credentials.from_authorized_user_file('token.json', GENAI_SCOPE)

load_dotenv()
GOOGLE_CLIENT_ID = os.environ.get('CLIENT_ID')

os.environ["GEMINI_API_KEY"] = "AIzaSyDP-WGwWX4SY2uLTaKAivWwuXzX0LqSui0"

genai.configure(
    api_key=os.getenv("GEMINI_API_KEY"),
    transport="rest",
    #client_options=creds
    )

app = Flask(__name__)
app.secret_key = 'XT5PUdwqegbndhgfsbdvH5m79D'
CORS(app, resources=r'/*', headers='Content-Type')
app.config['DEBUG'] = os.environ.get('FLASK_DEBUG')

os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
client_secret_file = os.path.join(pathlib.Path(__file__).parent,'client_secret.json')
token_file_path = 'google_access_token.json'

config = {
  'temperature': 0,
  'top_k': 20,
  'top_p': 0.9,
  'max_output_tokens': 500
}
safety_settings = [
  {
    "category": "HARM_CATEGORY_HARASSMENT",
    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
  },
  {
    "category": "HARM_CATEGORY_HATE_SPEECH",
    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
  },
  {
    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
  },
  {
    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
  }
]

model = genai.GenerativeModel(model_name="gemini-pro-vision",
                              generation_config=config,
                              safety_settings=safety_settings)

MOD_SCOPE = ['https://www.googleapis.com/auth/gmail.modify'] 

flow = Flow.from_client_secrets_file(
    client_secrets_file=client_secret_file,
    scopes=["https://www.googleapis.com/auth/userinfo.profile", "https://www.googleapis.com/auth/userinfo.email", 
            "https://www.googleapis.com/auth/gmail.modify", "https://mail.google.com/","openid"],
    redirect_uri="https://simpleflask-389293639960.us-central1.run.app/callback"
                                     )


def login_is_required(function):
    def wrapper(*args, **kwargs):
        if "google_id" not in session:
            return abort(401)  # Authorization required
        else:
            return function()

    return wrapper

@app.route("/")
def hello_world():
    """Example Hello World route."""
    name = os.environ.get("NAME", "World")
    return f"Hello {name}!"


@app.route("/login", methods=['GET', 'POST'])
def login():
    authorization_url, state = flow.authorization_url()
    session["state"] = state
    return redirect(authorization_url) # redirects to Google's OAuth 2.0 server

@app.route('/test')
def test_api_request():
    if 'credentials' not in session:
        return redirect('login')

    # Load credentials from the session.
    credentials = google.oauth2.credentials.Credentials(
        **session['credentials'])
    
    service = build('gmail', 'v1', credentials=credentials)
    result = service.users().messages().list(userId='me').execute()
    messages = result.get('messages')

    # TODO: Parse all email messages for proper display
           
    # Save credentials back to session in case access token was refreshed.
    # ACTION ITEM: In a production app, you likely want to save these
    #              credentials in a persistent database instead.
    session['credentials'] = credentials_to_dict(credentials)

    return jsonify(messages) 

def credentials_to_dict(credentials):
  return {'token': credentials.token,
          'refresh_token': credentials.refresh_token,
          'token_uri': credentials.token_uri,
          'client_id': credentials.client_id,
          'client_secret': credentials.client_secret,
          'scopes': credentials.scopes}

@app.route("/callback", methods=['GET', 'POST'])
def callback():
    flow.fetch_token(authorization_response=request.url)
    
    if not session["state"] == request.args["state"]:
        abort(500) # state doesn't match
    
    credentials = flow.credentials
    session["credentials"] = {
    'token': credentials.token,
    'refresh_token': credentials.refresh_token,
    'token_uri': credentials.token_uri,
    'client_id': credentials.client_id,
    'client_secret': credentials.client_secret,
    'scopes': credentials.scopes}
    request_session = requests.session()
    cached_session = cachecontrol.CacheControl(request_session)
    token_request = google.auth.transport.requests.Request(session=cached_session)

    with open(token_file_path, 'w') as file:
        json.dump(
            {"credentials_token": str(credentials.token),
             "credentials_id": str(credentials._id_token)
            }, file, indent=2)
    
    id_info = id_token.verify_oauth2_token(
        id_token=credentials._id_token,
        request=token_request,
        audience=GOOGLE_CLIENT_ID
    )
    
    session["google_id"] = id_info.get("sub")
    session["name"] = id_info.get("name")
    return redirect('https://gprotect-frontend.vercel.app/dashboard')


@app.route("/logout", methods=['GET', 'POST'])
def logout():
    session.clear()
    os.remove(token_file_path)
    return redirect("http://localhost:3000")

@app.route("/protected_area")
@login_is_required
def protected_area():
    return f"Hello {session['name']}! <br/> Info: {session} <br/> <a href='/logout'><button>Logout</button></a>"


# for testing flask and react connection
@app.route("/testing", methods=['GET'])
def testing():
    return jsonify(
        {"testing1": "abc", "testing2": "def"}
    )

@app.route("/google_token", methods=['GET'])
def google_token():
    file_path = os.path.join(os.path.dirname(__file__), "google_access_token.json")
    if os.path.exists(file_path):
        return send_file(file_path, mimetype='application/json')
    else:
        return jsonify({"error": "No token file found"})
    
@app.route("/tuned_gemini_query",methods=['POST'])
def tuned_gemini_query():
    data = request.get_json()
    query = data.get('query')

    model = genai.GenerativeModel(
        model_name="tunedModels/phish-ei0qk5k69u5o",
        system_instruction="You are a phishing email detection model. You are given the following email and asked to determine if it is a 'Phishing' or a 'Safe' email. Please only give a one word response. The email is as follows:",
    )

    response = model.generate_content(
        query,
        generation_config={
            "max_output_tokens":2048,
            "temperature":0.9,
            "top_p":1
         },
         stream=True
    )

    # for response in responses:
    #     output = response.candidates[0].content.parts[0].text

    return jsonify({'response':response})
    
@app.route("/gemini_query",methods=['POST'])
def gemini_query():
    data = request.get_json()
    query = data.get('query')

    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        system_instruction="You are a phishing email detection model. You are given the following email and asked to determine if it is a 'Phishing' or a 'Safe' email. Please only give a one word response. The email is as follows:",
    )

    responses = model.generate_content(
        query,
        generation_config={
            "max_output_tokens":2048,
            "temperature":0.9,
            "top_p":1
         },
         stream=True
    )

    for response in responses:
        output = response.candidates[0].content.parts[0].text

    return jsonify({"response":output})


def base64_to_bytes(base64_string):
    bin_string = base64.urlsafe_b64decode(base64_string)
    return bytearray(bin_string)

def bytes_to_base64(byte_array):
    bin_string = bytes(byte_array).decode('utf-8')
    return base64.urlsafe_b64encode(bin_string.encode('utf-8')).decode('utf-8')


@app.route("/decode", methods=['POST'])
def decode():
    data = request.get_json()
    query = data.get('query')
    decoded_bytes = base64_to_bytes(query)
    decoded_data = bytes(decoded_bytes).decode('utf-8')
    return jsonify({'decoded_data': decoded_data})

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

