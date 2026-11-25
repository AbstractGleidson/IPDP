from moments import rot_invariant_moments
import cv2
from pathlib import Path

if __name__ == "__main__":
    path = Path.home() / "Pictures" / "Esp32" / "dataset" / "13.jpeg"
    
    img = cv2.imread(path, 0)
    
    if img is not None:
        
        method = cv2.THRESH_BINARY
        
        img = cv2.medianBlur(img, 9)
        
        _, binary = cv2.threshold(img, 50, 150, cv2.THRESH_BINARY_INV)
        
        struct = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        
        cv2.imshow("Imagem: ", img)
        cv2.imshow("Binaria: ", binary)
        
        moments = rot_invariant_moments(binary)
        moments_beta = cv2.moments(binary)
        
        momentes_beta_HU = cv2.HuMoments(moments_beta)

        print(f"Momentos alfa: {moments}")
        print()
        print(f"Moments beta: {moments_beta}")
        print(f"Moments invariantes: {momentes_beta_HU}")
    
        cv2.waitKey(0)
        
    cv2.destroyAllWindows()