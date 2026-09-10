"""
Generates fully synthetic Aadhaar-style card images (no real people) plus a
matching ground-truth JSON per card, for testing the Aadhar Verification
Agent's OCR/extraction and guardrail logic without any real PII.

Aadhaar numbers are generated with a real, VALID Verhoeff checksum digit,
so they correctly pass your guardrail's checksum validation - same as a
genuine Aadhaar number would - while being entirely fake.
"""
import json
import os
import random
from datetime import date, timedelta

from faker import Faker
from PIL import Image, ImageDraw, ImageFont

fake = Faker("en_IN")
random.seed(7)
Faker.seed(7)

OUT_DIR = "synthetic_aadhar"
os.makedirs(OUT_DIR, exist_ok=True)

# --- Verhoeff checksum (the real algorithm UIDAI uses for Aadhaar numbers) ---
_D = [
    [0,1,2,3,4,5,6,7,8,9],[1,2,3,4,0,6,7,8,9,5],[2,3,4,0,1,7,8,9,5,6],
    [3,4,0,1,2,8,9,5,6,7],[4,0,1,2,3,9,5,6,7,8],[5,9,8,7,6,0,4,3,2,1],
    [6,5,9,8,7,1,0,4,3,2],[7,6,5,9,8,2,1,0,4,3],[8,7,6,5,9,3,2,1,0,4],
    [9,8,7,6,5,4,3,2,1,0],
]
_P = [
    [0,1,2,3,4,5,6,7,8,9],[1,5,7,6,2,8,3,0,9,4],[5,8,0,3,7,9,6,1,4,2],
    [8,9,1,6,0,4,3,5,2,7],[9,4,5,3,1,2,6,8,7,0],[4,2,8,6,5,7,3,9,0,1],
    [2,7,9,3,8,0,6,4,1,5],[7,0,4,6,9,1,3,2,5,8],
]

def verhoeff_checksum_digit(number_str: str) -> int:
    """Given the first 11 digits, compute the valid 12th (checksum) digit."""
    c = 0
    digits = [int(d) for d in reversed(number_str)]
    for i, d in enumerate(digits):
        c = _D[c][_P[(i + 1) % 8][d]]
    # find the digit that makes the checksum come out to 0
    for candidate in range(10):
        c2 = c
        c2 = _D[c2][_P[0][candidate]]
        if c2 == 0:
            return candidate
    return 0

def generate_aadhaar_number() -> str:
    first11 = "".join(str(random.randint(0, 9)) for _ in range(11))
    check = verhoeff_checksum_digit(first11)
    return first11 + str(check)

def format_aadhaar(number: str) -> str:
    return f"{number[0:4]} {number[4:8]} {number[8:12]}"


def make_card(index: int, out_dir: str = OUT_DIR, name=None, dob=None, gender=None,
              address=None, aadhaar_number=None, note: str = "SYNTHETIC SAMPLE - not a real document"):
    """Draws one Aadhaar-style card. Any field can be overridden (used by the
    bad-examples generator to deliberately inject invalid data); unset fields
    are randomly generated as usual."""
    os.makedirs(out_dir, exist_ok=True)
    name = name or fake.name()
    gender = gender or random.choice(["Male", "Female"])
    dob = dob or fake.date_of_birth(minimum_age=18, maximum_age=65)
    address = address or fake.address().replace("\n", ", ")
    aadhaar_number = aadhaar_number or generate_aadhaar_number()

    W, H = 900, 550
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)

    try:
        font_big = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 26)
        font_mid = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
    except OSError:
        font_big = font_mid = font_small = ImageFont.load_default()

    draw.rectangle([0, 0, W - 1, H - 1], outline="black", width=3)
    draw.rectangle([0, 0, W - 1, 70], fill=(255, 153, 51))  # saffron header band
    draw.text((20, 20), "Government of India (SYNTHETIC SAMPLE - NOT REAL)", fill="black", font=font_mid)

    draw.rectangle([30, 100, 230, 300], outline="gray", width=2)  # photo placeholder
    draw.text((70, 190), "PHOTO", fill="gray", font=font_mid)

    y = 110
    draw.text((260, y), f"Name: {name}", fill="black", font=font_big); y += 45
    draw.text((260, y), f"DOB: {dob.strftime('%d/%m/%Y')}", fill="black", font=font_mid); y += 35
    draw.text((260, y), f"Gender: {gender}", fill="black", font=font_mid); y += 35
    draw.text((260, y), "Address:", fill="black", font=font_mid); y += 28
    # wrap address
    words = address.split(", ")
    line = ""
    for w in words:
        if len(line) + len(w) > 45:
            draw.text((260, y), line, fill="black", font=font_small); y += 24
            line = w
        else:
            line = f"{line}, {w}" if line else w
    if line:
        draw.text((260, y), line, fill="black", font=font_small); y += 24

    draw.text((260, 420), format_aadhaar(aadhaar_number), fill="black", font=font_big)
    draw.text((260, 460), note, fill="gray", font=font_small)

    img_path = os.path.join(out_dir, f"aadhar_{index:03d}.png")
    img.save(img_path)

    ground_truth = {
        "file": img_path,
        "name": name,
        "dob": dob.isoformat(),
        "gender": gender,
        "address": address,
        "aadhaar_number": aadhaar_number,
        "aadhaar_number_formatted": format_aadhaar(aadhaar_number),
        "is_synthetic": True,
    }
    return ground_truth


if __name__ == "__main__":
    N = 10
    records = [make_card(i) for i in range(1, N + 1)]
    with open(os.path.join(OUT_DIR, "ground_truth.json"), "w") as f:
        json.dump(records, f, indent=2)
    print(f"Generated {N} synthetic Aadhaar cards in ./{OUT_DIR}/")
    print(f"Ground truth saved to ./{OUT_DIR}/ground_truth.json")
