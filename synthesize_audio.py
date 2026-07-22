"""
Synthèse audio standalone — appelé en subprocess depuis l'endpoint API.
Isolé du process uvicorn principal pour éviter tout risque mémoire
(même principe que translate-standalone.py).
"""
import sys
import subprocess


def synthesize(text: str, output_path: str, voice_model_path: str):
    subprocess.run(
        ["piper", "--model", voice_model_path, "--output_file", output_path],
        input=text.encode("utf-8"),
        check=True,
    )


if __name__ == "__main__":
    text, output_path, voice_model_path = sys.argv[1], sys.argv[2], sys.argv[3]
    synthesize(text, output_path, voice_model_path)
