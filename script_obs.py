import obspython as obs
import socket
import select
import re
import time

# Configuración inicial
bad_words = ["palabrota1", "palabrota2"]  # Personaliza tu lista
warnings = {}
irc_socket = None
connected = False
reconnect_attempts = 0
max_reconnect_attempts = 5

# Configura tus credenciales aquí
config = {
    "channel": "#tucanal",
    "bot_oauth": "oauth:tu_token",
    "bot_username": "tu_bot",
    "check_interval": 1000  # Intervalo de verificación en ms
}

def connect_to_twitch():
    global irc_socket, connected, reconnect_attempts
    try:
        irc_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server = "irc.chat.twitch.tv"
        port = 6667
        irc_socket.connect((server, port))
        
        irc_socket.send(f"PASS {config['bot_oauth']}\r\n".encode("utf-8"))
        irc_socket.send(f"NICK {config['bot_username']}\r\n".encode("utf-8"))
        irc_socket.send(f"JOIN {config['channel']}\r\n".encode("utf-8"))
        
        connected = True
        reconnect_attempts = 0
        obs.script_log(obs.LOG_INFO, "Conexión exitosa a Twitch IRC")
    except Exception as e:
        obs.script_log(obs.LOG_ERROR, f"Error de conexión: {str(e)}")
        handle_disconnection()

def process_message(data):
    if "PRIVMSG" not in data:
        return

    try:
        parts = data.split(":", 2)
        username = parts[1].split("!")[0]
        message = parts[2].strip().lower()
        
        if any(re.search(rf'\b{word}\b', message) for word in bad_words):
            handle_offense(username)
    except Exception as e:
        obs.script_log(obs.LOG_WARNING, f"Error procesando mensaje: {str(e)}")

def handle_offense(username):
    count = warnings.get(username, 0) + 1
    warnings[username] = count
    
    if count == 1:
        send_warning(username)
    elif count == 2:
        timeout_user(username, 300)  # 5 minutos
    else:
        ban_user(username)  # 5 días

def send_warning(username):
    send_irc_message(f"@{username}, ¡Primera advertencia! Por favor, mantén el respeto.")
    obs.script_log(obs.LOG_INFO, f"Advertencia a {username}")

def timeout_user(username, seconds):
    send_irc_command(f"PRIVMSG {config['channel']} :/timeout {username} {seconds}")
    obs.script_log(obs.LOG_INFO, f"Usuario {username} silenciado por 5 minutos")

def ban_user(username):
    send_irc_command(f"PRIVMSG {config['channel']} :/ban {username}")
    obs.script_log(obs.LOG_INFO, f"Usuario {username} baneado por 5 días")
    del warnings[username]

def send_irc_command(command):
    try:
        if connected:
            irc_socket.send(f"{command}\r\n".encode("utf-8"))
    except Exception as e:
        obs.script_log(obs.LOG_ERROR, f"Error enviando comando: {str(e)}")
        handle_disconnection()

def send_irc_message(message):
    send_irc_command(f"PRIVMSG {config['channel']} :{message}")

def check_messages():
    global connected
    if not connected:
        return True
    
    try:
        ready, _, _ = select.select([irc_socket], [], [], 0)
        if ready:
            data = irc_socket.recv(2048).decode("utf-8", errors="ignore")
            if not data:
                raise ConnectionError("Conexión cerrada por el servidor") # Crea exepcion 
                
            if data.startswith("PING"):
                irc_socket.send("PONG :tmi.twitch.tv\r\n".encode("utf-8"))
            else:
                for line in filter(None, data.split("\r\n")):
                    process_message(line)
    except Exception as e:
        obs.script_log(obs.LOG_ERROR, f"Error en recepción: {str(e)}")
        handle_disconnection()
    
    return True

def handle_disconnection():
    global connected, reconnect_attempts
    connected = False
    reconnect_attempts += 1
    
    if irc_socket:
        try:
            irc_socket.close()
        except:
            pass
    
    if reconnect_attempts <= max_reconnect_attempts:
        obs.script_log(obs.LOG_INFO, f"Intentando reconexión ({reconnect_attempts}/{max_reconnect_attempts})")
        time.sleep(min(2 ** reconnect_attempts, 30))  # Backoff exponencial
        connect_to_twitch()
    else:
        obs.script_log(obs.LOG_ERROR, "Máximos intentos de reconexión alcanzados")

def script_load(settings):
    obs.script_log(obs.LOG_INFO, "Iniciando bot de moderación...")
    connect_to_twitch()
    obs.timer_add(check_messages, config["check_interval"])

def script_unload():
    obs.script_log(obs.LOG_INFO, "Deteniendo bot de moderación...")
    obs.timer_remove(check_messages)
    if irc_socket:
        try:
            irc_socket.close()
        except:
            pass

def script_properties():
    props = obs.obs_properties_create()
    obs.obs_properties_add_text(props, "channel", "Canal", obs.OBS_TEXT_DEFAULT)
    obs.obs_properties_add_text(props, "bot_oauth", "OAuth Token", obs.OBS_TEXT_PASSWORD)
    obs.obs_properties_add_text(props, "bot_username", "Nombre del Bot", obs.OBS_TEXT_DEFAULT)
    return props

def script_update(settings):
    config["channel"] = obs.obs_data_get_string(settings, "channel")
    config["bot_oauth"] = obs.obs_data_get_string(settings, "bot_oauth")
    config["bot_username"] = obs.obs_data_get_string(settings, "bot_username")
    
