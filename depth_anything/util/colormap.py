import cv2


def colormap_exists(name: str) -> bool:
    colormap = [key for key in cv2.__dict__.keys() if "_" in key and name.lower() == key.split("_")[1].lower()]
    if len(colormap) > 0:
        return True
    else:
        return False
