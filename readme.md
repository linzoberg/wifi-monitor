# Wi-Fi Монитор v0.3 Release

Программа Wi-Fi Монитор v0.3 — это простое desktop-приложение на Python с графическим 
интерфейсом (PyQt5), предназначенное для автоматического мониторинга и поддержания 
подключения к выбранной Wi-Fi сети на Windows.

Wi-Fi Монитор автоматически отслеживает наличие заданной Wi-Fi сети, поддерживает 
стабильное подключение к ней и проверяет доступ в интернет.

Программа особенно полезна в местах с нестабильным Wi-Fi сигналом (например, за городом 
или в зонах слабого покрытия) — она самостоятельно переподключается при разрыве связи.

## Что нового в v0.3

- **Системный трей** — приложение сворачивается в иконку трея вместо закрытия.
  Иконка меняет цвет: 🟢 зелёная — подключено, 🔴 красная — нет соединения.
  В меню трея: «Открыть» и «Выход». Двойной клик по иконке открывает окно.
- **Пинг-монитор** — каждые 5 секунд пингует 8.8.8.8 и показывает задержку 
  прямо в интерфейсе. Цвет пинга меняется в зависимости от качества соединения:
  🟢 < 80 мс — отлично, 🟡 < 200 мс — нормально, 🔴 > 200 мс — плохо.
  Если обнаружен VPN — отображается «VPN is ON».

## Как пользоваться

При первом запуске введите SSID (имя сети) и пароль.
Далее используйте кнопки в интерфейсе для запуска/остановки мониторинга и очистки лога.
Закрытие окна сворачивает приложение в трей — для полного выхода используйте меню трея.

---

# Wi-Fi Monitor v0.3 Release

Wi-Fi Monitor v0.3 is a simple desktop application written in Python with a graphical 
user interface (PyQt5), designed for automatic monitoring and maintaining connection 
to a selected Wi-Fi network on Windows.

Wi-Fi Monitor continuously tracks the availability of the specified Wi-Fi network, 
ensures a stable connection to it, and verifies internet access.

The program is particularly useful in areas with unstable Wi-Fi signals (for example, 
in rural locations or zones with weak coverage) — it automatically attempts to reconnect 
when the connection is lost.

## What's new in v0.3

- **System Tray** — the application minimizes to the tray icon instead of closing.
  The icon changes color: 🟢 green — connected, 🔴 red — no connection.
  Tray menu includes: "Open" and "Exit". Double-click the icon to show the window.
- **Ping Monitor** — pings 8.8.8.8 every 5 seconds and displays the latency 
  directly in the interface. The color changes based on connection quality:
  🟢 < 80 ms — excellent, 🟡 < 200 ms — normal, 🔴 > 200 ms — poor.
  If a VPN is detected — displays "VPN is ON".

## How to Use

On first launch, enter the SSID (network name) and password.
Then use the buttons in the interface to start/stop monitoring and clear the event log.
Closing the window minimizes the application to the tray — use the tray menu to exit completely.