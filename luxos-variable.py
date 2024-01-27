import nmap
import schedule
import time
import luxor  # Asegúrate de que luxor.py esté en el mismo directorio o en el path de Python
import logging  # Importa el módulo de logging
import socket

# Configura el logging para escribir en un archivo de debug
logging.basicConfig(filename='debug.log', level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Rango de IP de los mineros en la red
start_ip = 101
end_ip = 120
base_ip = '192.168.1.'

def detect_luxor_os(minero_ip):
    try:
        response = luxor.send_cgminer_simple_command(minero_ip, 4028, "profiles", 5, False)
        if response and "PROFILES" in response:
            return True
    except Exception as e:
        logging.debug(f"No se pudo verificar LuxOS en {minero_ip}: {e}")
    return False

def scan_network():
    logging.debug("Iniciando el escaneo de la red.")
    nm = nmap.PortScanner()
    mineros_con_luxor = []
    print("Escaneando la red para detectar mineros con LuxOS...")
    for ip_end in range(start_ip, end_ip + 1):
        ip = f'{base_ip}{ip_end}'
        result = nm.scan(hosts=ip, arguments='-p 4028')  # Puerto común para APIs de minería
        if result['scan'] and ip in result['scan'] and 'tcp' in result['scan'][ip] and 4028 in result['scan'][ip]['tcp']:
            if detect_luxor_os(ip):
                mineros_con_luxor.append(ip)
                print(f"Minero con Luxor OS detectado: {ip}")
                logging.debug(f"Minero con LuxOS detectado: {ip}")
            else:
                print(f"Dispositivo detectado sin LuxOS: {ip}")
    logging.debug("Escaneo de la red completado.")
    return mineros_con_luxor

def select_mineros(mineros):
    logging.debug("Seleccionando mineros...")
    respuesta = input("¿Deseas aplicar la configuración a todos los mineros detectados? (s/n): ")
    if respuesta.lower() == 's':
        logging.debug("Todos los mineros.")
        return mineros
    else:
        mineros_seleccionados = []
        for minero in mineros:
            seleccion = input(f"¿Aplicar configuración al minero {minero}? (s/n): ")
            if seleccion.lower() == 's':
                mineros_seleccionados.append(minero)
        logging.debug(f"Mineros parciales: {mineros_seleccionados}")
        return mineros_seleccionados

def list_and_select_profiles(mineros):
    perfiles_por_minero = {}
    for minero_ip in mineros:
        print(f"Obteniendo perfiles para el minero: {minero_ip}")
        perfiles = list_available_profiles(minero_ip)
        selected_profile = select_profile(minero_ip, perfiles)
        if selected_profile:
            perfiles_por_minero[minero_ip] = selected_profile
    return perfiles_por_minero

def list_available_profiles(minero_ip):
    port = 4028  # Puerto para la API de Luxor OS
    response = luxor.send_cgminer_simple_command(minero_ip, port, "profiles", 5, True)  # Asumimos un timeout de 5 segundos y verbose=True
    perfiles = [perfil["Profile Name"] for perfil in response.get("PROFILES", [])]
    print(f"Perfiles disponibles para {minero_ip}: {', '.join(perfiles)}")
    return perfiles

def select_profile(minero_ip, perfiles):
    print("Perfiles disponibles:", ", ".join(perfiles))
    overclock_profile = input("Selecciona el perfil de overclocking: ")
    downclock_profile = input("Selecciona el perfil de underclocking: ")
    if overclock_profile not in perfiles or downclock_profile not in perfiles:
        print("Selección inválida. Asegúrate de elegir perfiles de la lista.")
        return None, None
    logging.debug(f"Seleccionando perfil. Overclock: {overclock_profile}. Underclock: {downclock_profile}")
    return overclock_profile, downclock_profile

# Función para obtener el perfil actual del minero y devolver el nombre del perfil
def get_current_profile(host):
    port = 4028
    comando = json.dumps({"command": "profileget"})
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect((host, port))
        sock.sendall(comando.encode('utf-8'))
        respuesta = sock.recv(1024).decode('utf-8')
        # Parsear la respuesta para extraer el nombre del perfil actual
        # Asumiendo que la respuesta incluye una clave 'PROFILE' que contiene el nombre del perfil
        perfil_actual = json.loads(respuesta).get('PROFILE', [{}])[0].get('Name', '')
        print(f'Perfil actual de {host}: {perfil_actual}')
        return perfil_actual

def apply_profile(minero_ip, perfil_deseado, board_id):
    # Asume que board_id es 0 para simplificar. Si necesitas manejar múltiples board_id, deberás ajustar esta lógica.
    board_id = 0
    try:
        # Obtener el session_id llamando a la función logon
        session_id = luxor.logon(minero_ip, 4028, 5, True)  # Asume que 4028 es el puerto y 5 segundos es el timeout
        # Formatea los parámetros incluyendo el session_id, board_id y perfil_deseado
        parametros = f"{session_id},{board_id},{perfil_deseado}"
        # Envía el comando 'profileset' con los parámetros formateados
        response = luxor.send_cgminer_command(minero_ip, 4028, "profileset", parametros, 5, True)
        logging.info(f'Respuesta al aplicar perfil {perfil_deseado} con board_id {board_id} en {minero_ip}: {response}')
    except Exception as e:
        logging.error(f"Error al aplicar el perfil en {minero_ip}: {e}")

def set_overclocking(mineros, profile):
    for minero in mineros:
        print("Overclocking...")
        for board_id in [0]:  # Itera sobre los posibles board_id
            apply_profile(minero, profile, board_id)
        logging.debug("Overclocking...")

def set_downclocking(mineros, profile):
    for minero in mineros:
        print("Underclocking...")
        for board_id in [0]:  # Itera sobre los posibles board_id
            apply_profile(minero, profile, board_id)
        logging.debug("Underclocking...")

def schedule_changes_with_selection():
    mineros = scan_network()
    if not mineros:
        print("No se detectaron mineros con LuxOS. Finalizando el script.")
        return

    mineros_seleccionados = select_mineros(mineros)
    for minero_ip in mineros_seleccionados:
        # Obtener la lista de perfiles disponibles para el minero
        perfiles = list_available_profiles(minero_ip)

        # Si no hay perfiles disponibles, continuar con el siguiente minero
        if not perfiles:
            print(f"No se encontraron perfiles para el minero {minero_ip}. Saltando este minero.")
            continue

        # Lista y selecciona perfiles para el minero seleccionado
        overclock_profile, downclock_profile = select_profile(minero_ip, perfiles)
        if not overclock_profile or not downclock_profile:
            print(f"No se seleccionaron perfiles adecuadamente para el minero {minero_ip}. Saltando este minero.")
            continue

        # Programa las tareas para aplicar los perfiles
        schedule.every().day.at("22:00").do(set_overclocking, [minero_ip], overclock_profile)
        schedule.every().day.at("18:00").do(set_downclocking, [minero_ip], downclock_profile)


    print("Los perfiles seleccionados serán aplicados según el horario establecido. Presiona Ctrl+C para detener.")
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == '__main__':
    logging.debug("Iniciando el script.")
    schedule_changes_with_selection()
    logging.debug("Script finalizado.")
