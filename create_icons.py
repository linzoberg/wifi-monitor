from PIL import Image, ImageDraw


def create_icon(color: str, filename: str):
    size = 64
    img  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Фоновый круг
    margin = 4
    draw.ellipse(
        [margin, margin, size - margin, size - margin],
        fill=color,
        outline="white",
        width=2
    )

    # Волны WiFi
    cx = size // 2
    for r in [10, 18, 26]:
        draw.arc(
            [cx - r, size // 2 - r, cx + r, size // 2 + r],
            start=200, end=340,
            fill="white",
            width=2
        )

    # Точка
    draw.ellipse([cx - 3, cx + 12, cx + 3, cx + 18], fill="white")

    img.save(filename)
    print(f"Создана иконка: {filename}")


if __name__ == "__main__":
    create_icon("#2ecc71", "icon_green.png")
    create_icon("#e74c3c", "icon_red.png")