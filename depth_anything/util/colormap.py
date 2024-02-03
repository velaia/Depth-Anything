import cv2


def get_colormap(input: str) -> int:
    colormap = cv2.COLORMAP_INFERNO  # default
    if colormap_exists(input):
        colormap = name_to_colormap(input)
    return colormap


def colormap_exists(name: str) -> bool:
    colormap = [key for key in cv2.__dict__.keys() if "_" in key and name.lower() == key.split("_")[1].lower()]
    if len(colormap) > 0:
        return True
    else:
        return False


def name_to_colormap(name: str) -> int:
    return getattr(cv2, "COLORMAP_" + name.upper())
