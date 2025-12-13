import subprocess
import time
import re
import config

class WiFiMonitor:
    """Класс для мониторинга и управления Wi-Fi подключениями"""
    
    def __init__(self):
        self.connected = False
        self.ssid_available = False
        
    def check_wifi_available(self):
        """Проверяет, доступна ли указанная Wi-Fi сеть в радиусе действия"""
        try:
            # Команда для сканирования доступных сетей
            result = subprocess.run(
                ["netsh", "wlan", "show", "networks"],
                capture_output=True,
                text=True,
                encoding='cp866',  # Кодировка для русского текста в Windows
                timeout=5
            )
            
            if result.returncode == 0:
                networks = result.stdout
                # Проверяем наличие нашей сети в списке
                self.ssid_available = config.WIFI_SSID in networks
                return self.ssid_available
            return False
            
        except subprocess.TimeoutExpired:
            return False
        except Exception as e:
            print(f"Ошибка при сканировании сетей: {e}")
            return False
    
    def get_current_connection(self):
        """Получает информацию о текущем подключении"""
        try:
            result = subprocess.run(
                ["netsh", "wlan", "show", "interfaces"],
                capture_output=True,
                text=True,
                encoding='cp866',
                timeout=3
            )
            
            if result.returncode == 0:
                output = result.stdout
                # Ищем SSID текущего подключения
                ssid_match = re.search(r'SSID\s*:\s*(.+)', output)
                state_match = re.search(r'Состояние\s*:\s*(.+)', output, re.IGNORECASE)
                
                current_ssid = ssid_match.group(1).strip() if ssid_match else None
                is_connected = "подключено" in output.lower() if state_match else False
                
                if current_ssid == config.WIFI_SSID and is_connected:
                    self.connected = True
                    return True
                else:
                    self.connected = False
                    return False
            return False
            
        except Exception as e:
            print(f"Ошибка при получении информации о подключении: {e}")
            return False
    
    def connect_to_wifi(self):
        """Подключается к указанной Wi-Fi сети"""
        max_attempts = config.RECONNECT_ATTEMPTS
        
        for attempt in range(1, max_attempts + 1):
            try:
                # Удаляем старый профиль, если он существует
                subprocess.run(
                    ["netsh", "wlan", "delete", "profile", f"name={config.WIFI_SSID}"],
                    capture_output=True,
                    text=True
                )
                
                # Создаем XML профиль для подключения
                profile_xml = f"""<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
    <name>{config.WIFI_SSID}</name>
    <SSIDConfig>
        <SSID>
            <name>{config.WIFI_SSID}</name>
        </SSID>
    </SSIDConfig>
    <connectionType>ESS</connectionType>
    <connectionMode>auto</connectionMode>
    <MSM>
        <security>
            <authEncryption>
                <authentication>WPA2PSK</authentication>
                <encryption>AES</encryption>
                <useOneX>false</useOneX>
            </authEncryption>
            <sharedKey>
                <keyType>passPhrase</keyType>
                <protected>false</protected>
                <keyMaterial>{config.WIFI_PASSWORD}</keyMaterial>
            </sharedKey>
        </security>
    </MSM>
</WLANProfile>"""
                
                # Временно сохраняем XML в файл
                with open(f"{config.WIFI_SSID}.xml", "w", encoding='utf-8') as f:
                    f.write(profile_xml)
                
                # Добавляем профиль
                add_result = subprocess.run(
                    ["netsh", "wlan", "add", "profile", f"filename={config.WIFI_SSID}.xml"],
                    capture_output=True,
                    text=True
                )
                
                # Подключаемся
                connect_result = subprocess.run(
                    ["netsh", "wlan", "connect", f"name={config.WIFI_SSID}"],
                    capture_output=True,
                    text=True
                )
                
                # Удаляем временный файл
                import os
                if os.path.exists(f"{config.WIFI_SSID}.xml"):
                    os.remove(f"{config.WIFI_SSID}.xml")
                
                # Проверяем результат
                if connect_result.returncode == 0:
                    # Даем время на подключение
                    time.sleep(3)
                    
                    # Проверяем, успешно ли подключились
                    if self.get_current_connection():
                        return True, f"Успешно подключено к {config.WIFI_SSID}"
                    else:
                        return False, f"Попытка {attempt}/{max_attempts}: Не удалось установить соединение"
                else:
                    return False, f"Попытка {attempt}/{max_attempts}: Ошибка команды подключения"
                    
            except Exception as e:
                error_msg = f"Попытка {attempt}/{max_attempts}: Ошибка: {str(e)}"
                return False, error_msg
            
            # Пауза перед следующей попыткой
            if attempt < max_attempts:
                time.sleep(config.RECONNECT_DELAY)
        
        return False, f"Не удалось подключиться после {max_attempts} попыток"
    
    def check_internet(self):
        """Проверяет доступность интернета"""
        import socket
        
        try:
            # Пытаемся подключиться к роутеру
            socket.create_connection((config.ROUTER_IP, 80), timeout=2)
            return True
        except:
            try:
                # Альтернативная проверка через Google DNS
                socket.create_connection(("8.8.8.8", 53), timeout=2)
                return True
            except:
                return False