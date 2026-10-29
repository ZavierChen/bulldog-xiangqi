# Third-party components

- **Pikafish 2026-09-06** — the Pikafish developers, GPL-3.0. Downloaded separately from the official release by `tools/install_engine.py`. License: `engine/Copying.txt`; NNUE terms: `engine/NNUE-License.md`. Matching source: https://github.com/official-pikafish/Pikafish/tree/Pikafish-2026-09-06
- **PieceNet / xiangqi-bot** — Copyright (c) 2026 Ying Wang, MIT. The converted `connector/bridge/pieces.onnx` is derived from this model. Full notice: `connector/bridge/MODEL-LICENSE.txt`. Source: https://github.com/yingwang/xiangqi-bot
- **ONNX Runtime / DirectML** — Microsoft, MIT; installed separately through pip.
- **PP-OCRv4 Chinese recognition / RapidOCR ONNX conversion** — PaddlePaddle/PaddleOCR and RapidAI/RapidOCR, Apache-2.0. Model downloaded separately by `tools/install_ocr.py`; full license: `connector/bridge/OCR-LICENSE.txt`. Source: https://github.com/PaddlePaddle/PaddleOCR and https://github.com/RapidAI/RapidOCR . The tiny `appearance.onnx` matcher is this project's own two-operation graph, reproducible with `tools/build_appearance_model.py`.
- **OpenCV**, **NumPy**, **Pillow**, **py7zr** — retain their respective distribution licenses; installed separately through pip.
- **UI recognition templates** — small interface/board crops used to recognize compatible third-party game interfaces; their original artwork belongs to the relevant owners. They do not include full personal screenshots or account records.
- **Bulldog icon** — generated specifically for this project using the built-in image generation tool. The flat collegiate mascot drawing style was a visual reference; the icon uses an original scholarly/chess composition, without institutional emblems, names or letters. Prompt: `assets/bulldog.prompt.txt`.
