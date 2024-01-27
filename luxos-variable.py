import nmap
import schedule
import time
import luxor  # Make sure luxor.py is in the same directory or in the Python path
import logging  # Import the logging module
import socket

# Configure logging to write to a debug file
logging.basicConfig(filename='debug.log', level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# IP range of the miners on the network
start_ip = 101
end_ip = 120
base_ip = '192.168.1.'

def detect_luxor_os(minero_ip):
    try:
        response = luxor.send_cgminer_simple_command(minero_ip, 4028, "profiles", 5, False)
        if response and "PROFILES" in response:
            return True
    except Exception as e:
        logging.debug(f"Could not verify LuxOS at {minero_ip}: {e}")
    return False

def scan_network():
    logging.debug("Starting network scan.")
    nm = nmap.PortScanner()
    mineros_con_luxor = []
    print("Scanning the network for miners with LuxOS...")
    for ip_end in range(start_ip, end_ip + 1):
        ip = f'{base_ip}{ip_end}'
        result = nm.scan(hosts=ip, arguments='-p 4028')  # Common port for mining APIs
        if result['scan'] and ip in result['scan'] and 'tcp' in result['scan'][ip] and 4028 in result['scan'][ip]['tcp']:
            if detect_luxor_os(ip):
                mineros_con_luxor.append(ip)
                print(f"Miner with LuxOS detected: {ip}")
                logging.debug(f"Miner with LuxOS detected: {ip}")
            else:
                print(f"Device detected without LuxOS: {ip}")
    logging.debug("Network scan completed.")
    return mineros_con_luxor

def select_mineros(mineros):
    logging.debug("Selecting miners...")
    respuesta = input("Do you want to apply the configuration to all detected miners? (y/n): ")
    if respuesta.lower() == 'y':
        logging.debug("All miners.")
        return mineros
    else:
        mineros_seleccionados = []
        for minero in mineros:
            seleccion = input(f"Apply configuration to miner {minero}? (y/n): ")
            if seleccion.lower() == 'y':
                mineros_seleccionados.append(minero)
        logging.debug(f"Partial miners: {mineros_seleccionados}")
        return mineros_seleccionados

def list_and_select_profiles(mineros):
    perfiles_por_minero = {}
    for minero_ip in mineros:
        print(f"Getting profiles for miner: {minero_ip}")
        perfiles = list_available_profiles(minero_ip)
        selected_profile = select_profile(minero_ip, perfiles)
        if selected_profile:
            perfiles_por_minero[minero_ip] = selected_profile
    return perfiles_por_minero

def list_available_profiles(minero_ip):
    port = 4028  # Port for Luxor OS API
    response = luxor.send_cgminer_simple_command(minero_ip, port, "profiles", 5, True)  # Assuming a timeout of 5 seconds and verbose=True
    perfiles = [perfil["Profile Name"] for perfil in response.get("PROFILES", [])]
    print(f"Available profiles for {minero_ip}: {', '.join(perfiles)}")
    return perfiles

def select_profile(minero_ip, perfiles):
    print("Available profiles:", ", ".join(perfiles))
    overclock_profile = input("Select the overclocking profile: ")
    downclock_profile = input("Select the underclocking profile: ")
    if overclock_profile not in perfiles or downclock_profile not in perfiles:
        print("Invalid selection. Please choose profiles from the list.")
        return None, None
    logging.debug(f"Selecting profile. Overclock: {overclock_profile}. Underclock: {downclock_profile}")
    return overclock_profile, downclock_profile

# Function to obtain the current profile of the miner and return the profile name
def get_current_profile(host):
    port = 4028
    comando = json.dumps({"command": "profileget"})
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect((host, port))
        sock.sendall(comando.encode('utf-8'))
        respuesta = sock.recv(1024).decode('utf-8')
        # Parse the response to extract the name of the current profile
        # Assuming the response includes a 'PROFILE' key containing the profile name
        perfil_actual = json.loads(respuesta).get('PROFILE', [{}])[0].get('Name', '')
        print(f'Current profile of {host}: {perfil_actual}')
        return perfil_actual

def apply_profile(minero_ip, perfil_deseado, board_id):
    # Assumes board_id is 0 for simplicity. Adjust this logic if you need to handle multiple board_id.
    board_id = 0
    try:
        # Get the session_id by calling the logon function
        session_id = luxor.logon(minero_ip, 4028, 5, True)  # Assumes 4028 is the port and 5 seconds is the timeout
        # Format the parameters including the session_id, board_id, and desired_profile
        parametros = f"{session_id},{board_id},{perfil_deseado}"
        # Send the 'profileset' command with the formatted parameters
        response = luxor.send_cgminer_command(minero_ip, 4028, "profileset", parametros, 5, True)
        logging.info(f'Response to applying profile {perfil_deseado} with board_id {board_id} at {minero_ip}: {response}')
    except Exception as e:
        logging.error(f"Error applying profile at {minero_ip}: {e}")

def set_overclocking(mineros, profile):
    for minero in mineros:
        print("Overclocking...")
        for board_id in [0]:  # Iterate over possible board_id
            apply_profile(minero, profile, board_id)
        logging.debug("Overclocking...")

def set_downclocking(mineros, profile):
    for minero in mineros:
        print("Underclocking...")
        for board_id in [0]:  # Iterate over possible board_id
            apply_profile(minero, profile, board_id)
        logging.debug("Underclocking...")

def schedule_changes_with_selection():
    mineros = scan_network()
    if not mineros:
        print("No miners with LuxOS detected. Ending script.")
        return

    mineros_seleccionados = select_mineros(mineros)
    for minero_ip in mineros_seleccionados:
        # Get the list of available profiles for the miner
        perfiles = list_available_profiles(minero_ip)

        # If no profiles are available, continue with the next miner
        if not perfiles:
            print(f"No profiles found for miner {minero_ip}. Skipping this miner.")
            continue

        # List and select profiles for the selected miner
        overclock_profile, downclock_profile = select_profile(minero_ip, perfiles)
        if not overclock_profile or not downclock_profile:
            print(f"Profiles not properly selected for miner {minero_ip}. Skipping this miner.")
            continue

        # Schedule tasks to apply the profiles
        schedule.every().day.at("22:00").do(set_overclocking, [minero_ip], overclock_profile)
        schedule.every().day.at("18:00").do(set_downclocking, [minero_ip], downclock_profile)

    print("Selected profiles will be applied according to the established schedule. Press Ctrl+C to stop.")
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == '__main__':
    logging.debug("Starting the script.")
    schedule_changes_with_selection()
    logging.debug("Script finished.")
