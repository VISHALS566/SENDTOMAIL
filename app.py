import os
import smtplib
from flask import Flask, request, jsonify, render_template_string
from flask_socketio import SocketIO, emit, join_room
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import qrcode
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

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

@socketio.on('send_via_gmail')
def send_via_brevo(data):
    target_email = data['target_email']
    text_content = data['text']

    print(f"Sending to {target_email} via Brevo Port 2525...")

    try:
        msg = MIMEMultipart()
        msg['From'] = os.getenv("MAIL_SENDER")
        msg['To'] = target_email
        msg['Subject'] = "Public PC Transfer"

        body = f"""
        <div style="font-family: sans-serif; padding: 20px; border: 1px solid #ddd;">
            <h2>Transfer Successful</h2>
            <pre style="background:#eee; padding:10px;">{text_content}</pre>
        </div>
        """
        msg.attach(MIMEText(body, 'html'))

        # CONNECT TO BREVO ON PORT 2525
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        
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
        textarea { width: 100%; height: 150px; margin: 1rem 0; padding: 10px; border: 1px solid #ccc; border-radius: 5px; }
        button { background-color: #10b981; color: white; padding: 12px; border: none; border-radius: 5px; cursor: pointer; width: 100%; font-size: 16px; font-weight: bold; }
        input { width: 100%; padding: 12px; margin-bottom: 1rem; border: 1px solid #ccc; border-radius: 5px; }
        .hidden { display: none; }
    </style>
</head>
<body>
    {% if view_type == 'desktop' %}
    <div id="app">
        <div id="locked" class="card">
            <h2>Scan to Login</h2>
            <img id="qr" src="" />
            <p style="color:gray">Session: <span id="sess"></span></p>
        </div>
        <div id="unlocked" class="card hidden">
            <h2 style="color:green">Connected</h2>
            <p>User: <b id="user-display"></b></p>
            <textarea id="txt" placeholder="Paste text here..."></textarea>
            <button onclick="send()">Send via Brevo</button>
        </div>
    </div>
    <script>
        const socket = io();
        const id = Math.random().toString(36).substring(2, 8);
        document.getElementById('sess').innerText = id;
        const link = `{{ base_url }}/mobile/${id}`;
        // USE PUBLIC API FOR QR CODE (Fixes broken image)
        document.getElementById('qr').src = `https://api.qrserver.com/v1/create-qr-code/?size=250x250&data=${encodeURIComponent(link)}`;

        socket.on('connect', () => socket.emit('join', { room: id }));
        
        let email = "";
        socket.on('unlock_terminal', (data) => {
            email = data.email;
            document.getElementById('user-display').innerText = email;
            document.getElementById('locked').classList.add('hidden');
            document.getElementById('unlocked').classList.remove('hidden');
        });

        function send() {
            const txt = document.getElementById('txt').value;
            socket.emit('send_via_gmail', { target_email: email, text: txt });
        }

        socket.on('email_status', (d) => {
            if(d.success) { alert('Sent!'); location.reload(); }
            else { alert('Failed: ' + d.error); }
        });
    </script>
    {% endif %}

    {% if view_type == 'mobile' %}
    <div class="card">
        <h2>Remote Access</h2>
        <p>Enter the student's email:</p>
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