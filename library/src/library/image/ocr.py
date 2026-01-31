from PIL import Image
import pytesseract

def recognize_letter(path):
    return pytesseract.image_to_string(
        Image.open(path),
        config=(
            " --psm 10"
            " --oem 1"
            " -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
            " -c load_system_dawg=0"
            " -c load_freq_dawg=0"
        )
    ).strip()