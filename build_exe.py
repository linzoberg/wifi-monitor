import os
import shutil
import sys
from subprocess import run, CalledProcessError


def build_exe():
    """Автоматическая сборка EXE-файла с помощью PyInstaller"""

    # Параметры сборки (точно как вы просили)
    script_name = "main_gui.py"
    exe_name = "WiFi_Monitor"
    args = [
        "--onefile",  # Один файл
        "--windowed",  # Без консольного окна (для GUI)
        "--name", exe_name,
        script_name
    ]

    print("Запуск сборки EXE-файла...")
    print(f"Параметры: pyinstaller {' '.join(args)}")

    # Очистка предыдущих сборок (опционально, но рекомендуется)
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

    # Запуск PyInstaller через его Python API (надёжнее, чем subprocess)
    try:
        import PyInstaller.__main__
        PyInstaller.__main__.run(args)
        print("\nСборка успешно завершена!")
        print(f"Готовый файл: dist/{exe_name}.exe")
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