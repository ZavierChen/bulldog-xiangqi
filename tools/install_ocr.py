"""Download the separately licensed, pinned Chinese recognition model."""
import hashlib,os,tempfile,urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
URL='https://huggingface.co/spaces/RapidAI/RapidOCR/resolve/ad05aa73dc29dbf3d2a4f3d8af303244cdf91634/models/text_rec/ch_PP-OCRv4_rec_infer.onnx'
SHA256='48fc40f24f6d2a207a2b1091d3437eb3cc3eb6b676dc3ef9c37384005483683b'


def digest(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    target=ROOT/'connector/models/ch_PP-OCRv4_rec.onnx';target.parent.mkdir(exist_ok=True)
    if target.exists() and digest(target)==SHA256:print('Chinese OCR model verified.');return
    fd,name=tempfile.mkstemp(prefix='ocr-',suffix='.download',dir=target.parent);os.close(fd)
    temp=Path(name)
    try:
        urllib.request.urlretrieve(URL,temp)
        if digest(temp)!=SHA256:raise RuntimeError('Chinese OCR SHA256 mismatch')
        os.replace(temp,target);print('Chinese OCR model downloaded and verified.')
    finally:
        if temp.exists():temp.unlink()


if __name__=='__main__':main()
