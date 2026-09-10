"""
Generates visually realistic synthetic Aadhaar cards - tricolor header,
simplified emblem, photo silhouette, bilingual (Hindi/English) fields,
and a real QR code graphic (encoding a dummy string, not a real UIDAI QR
payload). Still entirely synthetic: no real people, clearly watermarked.

Aadhaar numbers are Verhoeff-valid, same as generate_synthetic_aadhar.py.
"""
import json
import os
import random

import qrcode
from faker import Faker
from PIL import Image, ImageDraw, ImageFont

from verhoeff import verhoeff_checksum_digit

fake = Faker("en_IN")
random.seed(11)
Faker.seed(11)

OUT_DIR = "synthetic_aadhar_realistic"
os.makedirs(OUT_DIR, exist_ok=True)

FONT_DIR_DEJAVU = "/usr/share/fonts/truetype/dejavu"
FONT_DEVANAGARI = "/usr/share/fonts/truetype/lohit-devanagari/Lohit-Devanagari.ttf"


def generate_aadhaar_number() -> str:
    first11 = "".join(str(random.randint(0, 9)) for _ in range(11))
    check = verhoeff_checksum_digit(first11)
    return first11 + str(check)


def format_aadhaar(number: str) -> str:
    return f"{number[0:4]}  {number[4:8]}  {number[8:12]}"


def _font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def draw_emblem(draw, cx, cy, r=32):
    """Simplified circular national-emblem-style badge - not an exact
    reproduction, just a recognizable placeholder mark."""
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(20, 20, 90), width=3)
    draw.ellipse([cx - r + 8, cy - r + 8, cx + r - 8, cy + r - 8], outline=(20, 20, 90), width=1)
    for i in range(4):
        draw.line([cx, cy, cx + int(r * 0.6 * [1, 0, -1, 0][i]),
                   cy + int(r * 0.6 * [0, 1, 0, -1][i])], fill=(20, 20, 90), width=2)
    draw.ellipse([cx - 5, cy - 5, cx + 5, cy + 5], fill=(20, 20, 90))


def draw_photo_silhouette(draw, box):
    x0, y0, x1, y1 = box
    draw.rectangle(box, fill=(235, 235, 235), outline=(160, 160, 160), width=2)
    w, h = x1 - x0, y1 - y0
    cx = x0 + w // 2
    head_r = int(w * 0.22)
    head_cy = y0 + int(h * 0.35)
    draw.ellipse([cx - head_r, head_cy - head_r, cx + head_r, head_cy + head_r], fill=(180, 180, 190))
    body_top = head_cy + head_r - 5
    draw.ellipse([x0 + int(w * 0.1), body_top, x1 - int(w * 0.1), y1 + int(h * 0.35)], fill=(180, 180, 190))


def draw_qr(img, box, data):
    qr = qrcode.QRCode(box_size=3, border=1)
    qr.add_data(data)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    size = box[2] - box[0]
    qr_img = qr_img.resize((size, size))
    img.paste(qr_img, (box[0], box[1]))


def make_realistic_card(index: int):
    name = fake.name()
    gender = random.choice(["Male", "Female"])
    dob = fake.date_of_birth(minimum_age=18, maximum_age=65)
    address = fake.address().replace("\n", ", ")
    aadhaar_number = generate_aadhaar_number()

    W, H = 1080, 680
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)

    f_hindi_big = _font(FONT_DEVANAGARI, 34)
    f_hindi_mid = _font(FONT_DEVANAGARI, 22)
    f_eng_bold = _font(f"{FONT_DIR_DEJAVU}/DejaVuSans-Bold.ttf", 22)
    f_eng_big_bold = _font(f"{FONT_DIR_DEJAVU}/DejaVuSans-Bold.ttf", 40)
    f_eng = _font(f"{FONT_DIR_DEJAVU}/DejaVuSans.ttf", 20)
    f_eng_small = _font(f"{FONT_DIR_DEJAVU}/DejaVuSans.ttf", 14)

    draw.rounded_rectangle([4, 4, W - 4, H - 4], radius=18, outline=(180, 180, 180), width=2)

    # --- Header: tricolor brush-stroke style + emblem + bilingual title ---
    draw.rounded_rectangle([30, 20, 780, 55], radius=18, fill=(255, 153, 51))
    draw.rounded_rectangle([30, 60, 720, 95], radius=18, fill=(19, 136, 8))
    draw_emblem(draw, 90, 65)
    draw.text((160, 25), "भारत सरकार", font=f_hindi_big, fill=(20, 20, 20))
    draw.text((160, 65), "GOVERNMENT OF INDIA", font=f_eng_bold, fill=(20, 20, 20))

    draw.text((W - 260, 20), "SYNTHETIC SAMPLE - NOT REAL", font=f_eng_small, fill=(150, 0, 0))

    # --- Photo + fields ---
    photo_box = (36, 130, 226, 380)
    draw_photo_silhouette(draw, photo_box)

    y = 140
    draw.text((250, y), "नाम / Name:", font=f_hindi_mid, fill=(20, 20, 20)); y += 34
    draw.text((250, y), name, font=f_eng_bold, fill=(20, 20, 20)); y += 44

    draw.text((250, y), "जन्म तारीख / DOB:", font=f_hindi_mid, fill=(20, 20, 20)); y += 34
    draw.text((250, y), dob.strftime("%d-%m-%Y"), font=f_eng, fill=(20, 20, 20)); y += 38

    draw.text((250, y), gender, font=f_eng, fill=(20, 20, 20)); y += 44

    draw.text((250, y), "पता / Address:", font=f_hindi_mid, fill=(20, 20, 20)); y += 30
    words = address.split(", ")
    line = ""
    for w in words:
        if len(line) + len(w) > 42:
            draw.text((250, y), line, font=f_eng_small, fill=(60, 60, 60)); y += 22
            line = w
        else:
            line = f"{line}, {w}" if line else w
    if line:
        draw.text((250, y), line, font=f_eng_small, fill=(60, 60, 60)); y += 22

    # --- QR code ---
    qr_payload = f"SYNTHETIC|{aadhaar_number}|{name}"
    draw_qr(img, (830, 130, 1010, 310), qr_payload)

    # --- Aadhaar number + tagline ---
    draw.text((250, 470), format_aadhaar(aadhaar_number), font=f_eng_big_bold, fill=(20, 20, 20))

    draw.line([(30, 560), (W - 30, 560)], fill=(200, 30, 30), width=3)
    draw.text((30, 580), "आधार", font=_font(FONT_DEVANAGARI, 30), fill=(200, 30, 30))
    draw.text((150, 585), "- आम आदमी का अधिकार (SYNTHETIC)", font=_font(FONT_DEVANAGARI, 22), fill=(80, 80, 80))

    img_path = os.path.join(OUT_DIR, f"aadhar_realistic_{index:03d}.png")
    img.save(img_path)

    return {
        "file": img_path,
        "name": name,
        "dob": dob.isoformat(),
        "gender": gender,
        "address": address,
        "aadhaar_number": aadhaar_number,
        "aadhaar_number_formatted": format_aadhaar(aadhaar_number),
        "is_synthetic": True,
    }


if __name__ == "__main__":
    N = 10
    records = [make_realistic_card(i) for i in range(1, N + 1)]
    with open(os.path.join(OUT_DIR, "ground_truth_realistic.json"), "w") as f:
        json.dump(records, f, indent=2)
    print(f"Generated {N} realistic synthetic Aadhaar cards in ./{OUT_DIR}/")
