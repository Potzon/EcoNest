import cv2
import time
import sys

# Returns a frame taken by the camera, given its device
# as a file and the resolution of the camera
def screenshot(device, width, height):
    camera = cv2.VideoCapture(device, cv2.CAP_V4L2)

    if not camera.isOpened():
        print("ERROR: Cannot open webcam:", device)
        return None

    # Request native camera resolution
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

    # Capture a frame
    success, frame = camera.read()
    if not success:
        print("ERROR: Cannot take screenshot")
        return None

    camera.release()
    return frame
    