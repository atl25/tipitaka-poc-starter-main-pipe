# clean_text.py
import os

def clean_text(input_path, output_path):
    print(f"Cleaning file: {input_path}")

    with open(input_path, "r", encoding="utf-8-sig") as f:
        lines = f.readlines()

    cleaned = [line.strip() for line in lines if line.strip()]
    text = "\n".join(cleaned)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(text)

    print(f"✅ Cleaned text saved to: {output_path}")


def clean_text_all_files(input_folder, output_folder, suffix="_cleaned.txt"):
    """
    Clean all .txt files in input_folder.
    Skip files that already have cleaned output in output_folder.
    """
    os.makedirs(output_folder, exist_ok=True)

    for filename in os.listdir(input_folder):
        if not filename.endswith(".txt"):
            continue

        base_name = os.path.splitext(filename)[0]
        output_filename = f"{base_name}{suffix}"
        output_path = os.path.join(output_folder, output_filename)

        if os.path.exists(output_path):
            print(f"⏭️ Skipping {filename} (already cleaned)")
            continue  # Don't re-clean

        input_path = os.path.join(input_folder, filename)
        clean_text(input_path, output_path)


if __name__ == "__main__":
    input_folder = "data/raw"
    output_folder = "data/outputs" 

    for filename in os.listdir(input_folder):
        ...
