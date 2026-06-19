import os
import shutil
import sys


def _find_upx() -> str | None:
    """Ищет upx.exe в PATH или в подпапке ./upx/. Возвращает путь к директории или None."""
    upx_exe = shutil.which("upx")
    if upx_exe:
        return os.path.dirname(upx_exe)

    local_upx_dir = os.path.join(os.path.dirname(__file__), "upx")
    if os.path.exists(os.path.join(local_upx_dir, "upx.exe")):
        return local_upx_dir

    return None


def build_exe():
    """Автоматическая сборка EXE-файла с помощью PyInstaller"""

    script_name = "main.py"
    exe_name = "WiFi_Monitor"
    args = [
        "--onefile",   # Один файл
        "--windowed",  # Без консольного окна (GUI)
        "--name", exe_name,
    ]

    # UPX-сжатие, если найден
    upx_dir = _find_upx()
    if upx_dir:
        print(f"UPX найден: {upx_dir} — включаем сжатие")
        args += ["--upx-dir", upx_dir]
    else:
        print("UPX не найден — собираем без сжатия")
        print("  (положи upx.exe в PATH или в ./upx/ для уменьшения exe ~в 2-3 раза)")

    args.append(script_name)

    print("\nЗапуск сборки EXE-файла...")
    print(f"Параметры: pyinstaller {' '.join(args)}\n")

    # Очистка предыдущих сборок
    folders_to_clean = ["build", "dist", "__pycache__"]
    files_to_clean = [f"{exe_name}.spec"]

    for folder in folders_to_clean:
        if os.path.exists(folder):
            print(f"Удаление папки: {folder}")
            shutil.rmtree(folder)

    for file in files_to_clean:
        if os.path.exists(file):
            print(f"Удаление файла: {file}")
            os.remove(file)

    # Запуск PyInstaller через его Python API
    try:
        import PyInstaller.__main__
        PyInstaller.__main__.run(args)

        exe_path = os.path.join("dist", f"{exe_name}.exe")
        if os.path.exists(exe_path):
            size_mb = os.path.getsize(exe_path) / (1024 * 1024)
            print(f"\nСборка успешно завершена!")
            print(f"Готовый файл: {exe_path} ({size_mb:.1f} МБ)")
        else:
            print("\nСборка завершена, но exe не найден в dist/")
        print("Можете распространять его без Python!")

    except ImportError:
        print("Ошибка: PyInstaller не установлен в этом окружении.")
        print("Установите: pip install pyinstaller")
        sys.exit(1)

    except Exception as e:
        print(f"\nОшибка во время сборки: {e}")
        sys.exit(1)


if __name__ == "__main__":
    build_exe()
