from base64 import b64decode
from io import BytesIO
from typing import Any, Dict, Union

import numpy as np
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS, IFD

from .commons.distance import find_cosine, find_euclidean
from .commons import functions as F
from .commons.folder_utils import initialize_folder
from .commons.face_processor import FaceProcessor
from .commons.package_utils import Model

initialize_folder()

def analyze(img: Union[str, np.ndarray], 
            actions: Dict[str, bool] = {"age": True, "emotion": True, "gender": True, "race": True},
            align: bool = True, enforce_detection: bool = True) -> Dict[str, Any]:
    try:
        img_objs = F.extract_faces(img, (224, 224), False, enforce_detection, align)
    except ValueError:
        return {}
    
    models: Dict[str, Model] = {a: F.build_model(a.capitalize()) for a, s in actions.items() if s}
    resp_objects = []
    
    # TODO: Make it parallel
    for img, region, confidence in img_objs:
        if img.shape[0] <= 0 or img.shape[1] <= 0: 
            continue
        
        obj = {"region": region, "face_confidence": confidence}
        
        for action, model in models.items():
            try:
                obj.update(getattr(FaceProcessor, action)(model.predict(img)))
            except Exception:
                continue

        resp_objects.append(obj)

    return resp_objects


def verify(img1: Union[str, np.ndarray], img2: Union[str, np.ndarray], 
           model_name: str = "VGG-Face", distance_metric: str = "cosine", 
           enforce_detection: bool = True, align: bool = True, 
           normalization: str = "base") -> Dict[str, Any]:
    target_size = F.find_size(model_name)

    distances, regions = [], []
    for c1, r1, _ in F.extract_faces(img1, target_size, False, enforce_detection, align):
        for c2, r2, _ in F.extract_faces(img2, target_size, False, enforce_detection, align):
            repr1 = F.represent(c1, model_name, enforce_detection, "skip", 
                              align, normalization)[0]["embedding"]
            repr2 = F.represent(c2, model_name, enforce_detection, "skip", 
                              align, normalization)[0]["embedding"]

            if distance_metric == "cosine":
                dst = find_cosine(repr1, repr2)
            elif distance_metric == "euclidean":
                dst = find_euclidean(repr1, repr2)
            else:
                dst = find_euclidean(dst.l2_normalize(repr1), dst.l2_normalize(repr2))

            distances.append(dst)
            regions.append((r1, r2))

    threshold = F.find_threshold(model_name, distance_metric)
    distance = min(distances)
    facial_areas = regions[np.argmin(distances)]
    
    return {
        "verified": True if distance <= threshold else False,
        "distance": distance,
        "threshold": threshold,
        "model": model_name,
        "similarity_metric": distance_metric,
        "facial_areas": {"img1": facial_areas[0], "img2": facial_areas[1]}
    }


def get_image_metadata(image: bytes) -> Dict[str, Any]:
    i = Image.open(BytesIO(image))
    
    exif = i.getexif()

    data = {
        "Summary": {
            "ImageSize": str(i.size),
            "FileType": str(i.format),
            "FormatDescription": i.format_description,
            "Mode": i.mode,
            "MIME": str(Image.MIME.get(i.format, None)),
            "BandNames": str(i.getbands()),
            "BBox": str(i.getbbox()),
            "Megapixels": str(round(i.size[0] * i.size[1] / 1000000, 2)),
            "Extrema": str(i.getextrema()),
            "HasTransparency": str(i.has_transparency_data),
            "Readonly": str(i.readonly),
            "Palette": str(i.palette),
        }
    }

    i.close()

    for k, v in exif.items():
        try:
            k = TAGS[k]
        except KeyError:
            pass
        finally:
            data["Summary"][str(k)] = str(v)
    
    for ifd_id in IFD:
        data[ifd_id.name] = {}
        try:
            ifd = exif.get_ifd(ifd_id)
        except KeyError:
            continue

        resolve = GPSTAGS if ifd_id == IFD.GPSInfo else TAGS

        for k, v in ifd.items():
            try:
                k = resolve[k]
            except KeyError:
                pass
            finally:
                data[ifd_id.name][str(k)] = str(v)

    return data
