import os
import smtplib
import base64
from flask import Flask, request, jsonify, render_template_string
from flask_socketio import SocketIO, emit, join_room
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent', max_http_buffer_size=5 * 1024 * 1024) 
SMTP_USER = os.getenv("SMTP_EMAIL") 

SMTP_PASSWORD = os.getenv("SMTP_PASSWORD") 

SMTP_SERVER = "smtp-relay.brevo.com"
SMTP_PORT = 2525  

@app.route('/')
def desktop_view():
    base_url = request.headers.get('X-Forwarded-Proto', 'http') + "://" + request.host
    return render_template_string(HTML_TEMPLATE, view_type="desktop", base_url=base_url)

@app.route('/mobile/<session_id>')
def mobile_view(session_id):
    return render_template_string(HTML_TEMPLATE, view_type="mobile", session_id=session_id)

@app.route('/api/mobile-unlock', methods=['POST'])
def mobile_unlock():
    data = request.json
    socketio.emit('unlock_terminal', {'email': data.get('email')}, room=data.get('session_id'))
    return jsonify({"status": "success"})

@socketio.on('join')
def on_join(data):
    join_room(data['room'])

@socketio.on('send_package')
def send_package(data):
    if not SMTP_USER or not SMTP_PASSWORD:
        print("CRITICAL ERROR: Render Environment Variables are MISSING!")
        emit('email_status', {'success': False, 'error': "Server Error: API Keys Missing on Render."})
        return

    target_email = data['target_email']
    text_content = data.get('text', '')
    file_data = data.get('file_data') 
    file_name = data.get('file_name')
    
    SENDER_EMAIL = os.getenv("MAIL_SENDER")

    print(f"Sending file to {target_email}...")

    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = target_email
        msg['Subject'] = "Public PC Transfer"

        body_html = f"""
        <div style="font-family: sans-serif; padding: 20px; border: 1px solid #ddd;">
            <h2>Transfer Successful</h2>
            <p><b>Note:</b> {text_content if text_content else "File Only"}</p>
        </div>
        """
        msg.attach(MIMEText(body_html, 'html'))

        if file_data and file_name:
            if "," in file_data:
                header, encoded = file_data.split(",", 1)
            else:
                encoded = file_data
            
            binary_data = base64.b64decode(encoded)

            part = MIMEBase('application', "octet-stream")
            part.set_payload(binary_data)
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f'attachment; filename="{file_name}"')
            msg.attach(part)

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SENDER_EMAIL, target_email, msg.as_string())
        
        emit('email_status', {'success': True})
    except Exception as e:
        print(f"SMTP Error: {e}")
        emit('email_status', {'success': False, 'error': str(e)})

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Secure Transfer</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
    <style>
        body { font-family: sans-serif; background: #f0f2f5; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .card { background: white; padding: 2rem; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); width: 90%; max-width: 400px; text-align: center; }
        textarea { width: 100%; height: 100px; margin: 1rem 0; padding: 10px; border: 1px solid #ccc; border-radius: 5px; }
        button { background-color: #007bff; color: white; padding: 12px; border: none; border-radius: 5px; cursor: pointer; width: 100%; font-size: 16px; margin-top:10px; }
        input[type="email"] { width: 100%; padding: 12px; margin-bottom: 1rem; border: 1px solid #ccc; border-radius: 5px; }
        .file-box { border: 2px dashed #ccc; padding: 20px; margin: 10px 0; border-radius: 5px; text-align: center; }
        .hidden { display: none; }
        .loader { display: none; color: blue; font-weight: bold; margin-top: 10px; }
    </style>
</head>
<body>
    {% if view_type == 'desktop' %}
    <div id="app">
        <div id="locked" class="card">
            <h2>Scan to Login</h2>
            <img id="qr" src="" />
            <p style="color:gray; font-size: 12px;">Session: <span id="sess"></span></p>
        </div>
        <div id="unlocked" class="card hidden">
            <h2 style="color:green">Connected</h2>
            <p>User: <b id="user-display"></b></p>
            
            <textarea id="txt" placeholder="Optional text..."></textarea>
            
            <div class="file-box">
                <input type="file" id="fileInput" />
            </div>

            <p id="loading" class="loader">Sending File (Please Wait)...</p>
            <button id="sendBtn" onclick="processAndSend()">Send Email</button>
        </div>
    </div>
    <script>
        const socket = io();
        const id = Math.random().toString(36).substring(2, 8);
        document.getElementById('sess').innerText = id;
        const link = `{{ base_url }}/mobile/${id}`;
        document.getElementById('qr').src = `https://api.qrserver.com/v1/create-qr-code/?size=250x250&data=${encodeURIComponent(link)}`;

        socket.on('connect', () => socket.emit('join', { room: id }));
        
        let email = "";
        socket.on('unlock_terminal', (data) => {
            email = data.email;
            document.getElementById('user-display').innerText = email;
            document.getElementById('locked').classList.add('hidden');
            document.getElementById('unlocked').classList.remove('hidden');
        });

        function processAndSend() {
            const txt = document.getElementById('txt').value;
            const fileInput = document.getElementById('fileInput');
            const file = fileInput.files[0];

            document.getElementById('sendBtn').disabled = true;
            document.getElementById('loading').style.display = 'block';

            if (file) {
                if(file.size > 5 * 1024 * 1024) {
                    alert("File too large! Max 5MB.");
                    document.getElementById('loading').style.display = 'none';
                    document.getElementById('sendBtn').disabled = false;
                    return;
                }
                const reader = new FileReader();
                reader.readAsDataURL(file);
                reader.onload = function () {
                    socket.emit('send_package', { 
                        target_email: email, 
                        text: txt,
                        file_data: reader.result,
                        file_name: file.name
                    });
                };
            } else {
                socket.emit('send_package', { 
                    target_email: email, 
                    text: txt,
                    file_data: null, 
                    file_name: null 
                });
            }
        }

        socket.on('email_status', (d) => {
            if(d.success) { alert('Sent!'); location.reload(); }
            else { 
                alert('Failed: ' + d.error); 
                document.getElementById('sendBtn').disabled = false;
                document.getElementById('loading').style.display = 'none';
            }
        });
    </script>
    {% endif %}

    {% if view_type == 'mobile' %}
    <div class="card">
        <h2>Remote Access</h2>
        <p>Enter Student Email:</p>
        <input type="email" id="email" placeholder="student@college.edu" />
        <button onclick="unlock()">Unlock Terminal</button>
    </div>
    <script>
        function unlock() {
            const em = document.getElementById('email').value;
            if(!em) return alert("Enter email");
            fetch('/api/mobile-unlock', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ session_id: "{{ session_id }}", email: em })
            })
            .then(r => r.json())
            .then(() => {
                document.body.innerHTML = "<h2 style='text-align:center; color:green'>Unlocked! Check PC.</h2>";
            });
        }
    </script>
    {% endif %}
</body>
</html>
"""

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)