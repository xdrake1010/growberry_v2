import cv2
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("CameraTest")

def test_camera():
    for backend in [None, cv2.CAP_V4L2, cv2.CAP_ANY]:
        logger.info(f"Testing backend: {backend}")
        for i in range(2):
            logger.info(f"Trying index {i} with backend {backend}")
            if backend is not None:
                cap = cv2.VideoCapture(i, backend)
            else:
                cap = cv2.VideoCapture(i)
                
            if cap.isOpened():
                logger.info(f"Success! Camera {i} opened with backend {backend}")
                ret, frame = cap.read()
                if ret:
                    logger.info("Successfully read a frame.")
                else:
                    logger.info("Failed to read a frame.")
                cap.release()
            else:
                logger.info(f"Failed to open camera {i} with backend {backend}")

if __name__ == "__main__":
    test_camera()
