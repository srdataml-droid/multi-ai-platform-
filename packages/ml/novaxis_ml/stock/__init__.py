"""Stock counting from a photo (docs/ml.md, "Stock counting").

Training needs PyTorch, which is not a workspace dependency (several GB). Install it where
you train: `pip install -r packages/ml/stock-requirements.txt` (laptop, Colab or CI's
vision job). The API serves the exported ONNX file with ONNX Runtime instead.
"""
